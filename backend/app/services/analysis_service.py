"""
Repository analysis orchestration service.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import git
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzers.base import BaseParser, FileAnalysis
from app.analyzers.javascript import JavaScriptParser
from app.analyzers.python import PythonParser
from app.analyzers.typescript import TypeScriptParser
from app.models.database import (
    Analysis,
    AnalysisStatus,
    GraphEdgeDB,
    GraphNodeDB,
    Repository,
    RepositoryFile,
    Symbol,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__",
    ".venv", "venv", "dist", "build", "target", "out",
    "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".idea", ".vscode", ".next", ".cache",
}

SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".cpp",
    ".h", ".hpp", ".go", ".rs", ".rb",
}

LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
}


class RepositoryAnalyzer:
    """Orchestrates the full repository analysis pipeline."""

    def __init__(self):
        self._parsers: dict[str, BaseParser] = {
            ".js": JavaScriptParser(),
            ".jsx": JavaScriptParser(),
            ".ts": TypeScriptParser(),
            ".tsx": TypeScriptParser(),
            ".py": PythonParser(),
        }

    def parse_url(self, url: str) -> tuple[str, str]:
        """Extract owner and repo name from GitHub URL."""
        url = url.rstrip("/").rstrip(".git")
        parts = url.split("github.com/")[-1].split("/")
        if len(parts) < 2:
            raise ValueError("Invalid GitHub URL")
        return parts[0], parts[1]

    async def clone_repository(self, url: str, db: AsyncSession) -> Repository:
        """Clone a repository and create the database record."""
        owner, name = self.parse_url(url)
        workspace = settings.REPOSITORIES_DIR / name

        if workspace.exists():
            shutil.rmtree(workspace)

        settings.REPOSITORIES_DIR.mkdir(parents=True, exist_ok=True)

        repo = Repository(
            url=url,
            name=name,
            owner=owner,
            status=AnalysisStatus.CLONING,
        )
        db.add(repo)
        await db.flush()

        try:
            proc = await self._run_command(
                ["git", "clone", "--depth", "1", url, str(workspace)]
            )
            if proc.returncode != 0:
                repo.status = AnalysisStatus.FAILED
                repo.error_message = proc.stderr
                await db.commit()
                raise RuntimeError(f"Clone failed: {proc.stderr}")

            # Get commit SHA
            result = await self._run_command(
                ["git", "-C", str(workspace), "rev-parse", "HEAD"]
            )
            repo.commit_sha = result.stdout.strip()[:8]

            # Detect default branch
            result = await self._run_command(
                ["git", "-C", str(workspace), "branch", "--show-current"]
            )
            repo.branch = result.stdout.strip()

            repo.workspace_path = str(workspace)
            repo.status = AnalysisStatus.SCANNING
            await db.commit()

            return repo

        except Exception as e:
            repo.status = AnalysisStatus.FAILED
            repo.error_message = str(e)
            await db.commit()
            raise

    async def analyze_repository(self, repo_id: int, db: AsyncSession):
        """Full analysis pipeline for a repository."""
        result = await db.execute(select(Repository).where(Repository.id == repo_id))
        repo = result.scalar_one_or_none()
        if not repo:
            return

        workspace = Path(repo.workspace_path)
        if not workspace.exists():
            repo.status = AnalysisStatus.FAILED
            repo.error_message = "Workspace not found"
            await db.commit()
            return

        try:
            # Step 1: Scan files
            repo.status = AnalysisStatus.SCANNING
            await db.commit()

            file_analyses = self._scan_and_parse(workspace)

            # Step 2: Store files
            repo.status = AnalysisStatus.PARSING
            await db.commit()

            for fa in file_analyses:
                rf = RepositoryFile(
                    repository_id=repo.id,
                    path=str(fa.file_path),
                    language=fa.language,
                    size_bytes=len(fa.source.encode("utf-8")) if hasattr(fa, 'source') else 0,
                    category="source",
                    has_syntax_errors=1 if fa.has_syntax_errors else 0,
                    entity_count=len(fa.entities),
                    import_count=len(fa.imports),
                    export_count=len(fa.exports),
                    call_count=len(fa.calls),
                )
                db.add(rf)
                await db.flush()

                for ent in fa.entities:
                    sym = Symbol(
                        repository_id=repo.id,
                        file_id=rf.id,
                        name=ent.name,
                        qualified_name=f"{ent.parent}.{ent.name}" if ent.parent else ent.name,
                        symbol_type=ent.entity_type,
                        file_path=str(fa.file_path),
                        start_line=ent.start_line,
                        end_line=ent.end_line,
                        parameters=ent.parameters,
                        metadata={"is_async": ent.is_async},
                    )
                    db.add(sym)

            # Step 3: Build graph
            repo.status = AnalysisStatus.BUILDING_GRAPH
            await db.commit()

            graph_data = self._build_graph(file_analyses)

            for node in graph_data["nodes"]:
                gn = GraphNodeDB(
                    repository_id=repo.id,
                    node_id=node["id"],
                    node_type=node["type"],
                    name=node["name"],
                    file_path=node.get("file_path"),
                    qualified_name=node.get("qualified_name"),
                    metadata=node.get("metadata", {}),
                )
                db.add(gn)

            for edge in graph_data["edges"]:
                ge = GraphEdgeDB(
                    repository_id=repo.id,
                    source_id=edge["source"],
                    target_id=edge["target"],
                    edge_type=edge["type"],
                    metadata=edge.get("metadata", {}),
                )
                db.add(ge)

            # Step 4: Create analysis record
            repo.status = AnalysisStatus.ANALYZING
            await db.commit()

            languages = {}
            total_entities = 0
            total_imports = 0
            total_exports = 0
            total_calls = 0
            total_classes = 0
            total_functions = 0

            for fa in file_analyses:
                lang = fa.language
                languages[lang] = languages.get(lang, 0) + 1
                total_entities += len(fa.entities)
                total_imports += len(fa.imports)
                total_exports += len(fa.exports)
                total_calls += len(fa.calls)
                for ent in fa.entities:
                    if ent.entity_type == "class":
                        total_classes += 1
                    elif ent.entity_type in ("function", "method"):
                        total_functions += 1

            frameworks = self._detect_frameworks(workspace, file_analyses)
            architecture = self._detect_architecture(workspace, file_analyses)
            tech_stack = self._detect_tech_stack(workspace)

            analysis = Analysis(
                repository_id=repo.id,
                total_files=len(file_analyses),
                total_source_files=len(file_analyses),
                total_functions=total_functions,
                total_classes=total_classes,
                total_imports=total_imports,
                total_exports=total_exports,
                total_calls=total_calls,
                languages=languages,
                frameworks=frameworks,
                architecture=architecture,
                tech_stack=tech_stack,
            )
            db.add(analysis)

            # Generate three-level analysis
            analysis.beginner_analysis = self._generate_beginner_analysis(repo, file_analyses, architecture, tech_stack)
            analysis.intermediate_analysis = self._generate_intermediate_analysis(repo, file_analyses, graph_data, architecture)
            analysis.advanced_analysis = self._generate_advanced_analysis(repo, file_analyses, graph_data, architecture)

            repo.status = AnalysisStatus.COMPLETED
            repo.updated_at = datetime.utcnow()
            await db.commit()

        except Exception as e:
            logger.exception("Analysis failed for repo %d", repo.id)
            repo.status = AnalysisStatus.FAILED
            repo.error_message = str(e)
            await db.commit()

    def _scan_and_parse(self, workspace: Path) -> list[FileAnalysis]:
        """Scan repository and parse all source files."""
        analyses = []

        for file_path in self._iter_source_files(workspace):
            ext = file_path.suffix.lower()
            parser = self._parsers.get(ext)
            if not parser:
                continue

            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
                if len(source) > settings.MAX_FILE_SIZE_KB * 1024:
                    continue

                relative = file_path.relative_to(workspace)
                fa = parser.analyze(source, relative)
                fa.source = source
                analyses.append(fa)
            except Exception as e:
                logger.warning("Failed to parse %s: %s", file_path, e)

        return sorted(analyses, key=lambda a: str(a.file_path))

    def _iter_source_files(self, workspace: Path):
        """Iterate source files, skipping ignored directories."""
        stack = [workspace]
        while stack:
            directory = stack.pop()
            try:
                entries = sorted(directory.iterdir(), key=lambda p: p.name, reverse=True)
            except OSError:
                continue
            for entry in entries:
                if entry.is_dir():
                    if entry.name not in IGNORED_DIRS:
                        stack.append(entry)
                elif entry.is_file() and entry.suffix.lower() in SOURCE_EXTENSIONS:
                    yield entry

    def _build_graph(self, analyses: list[FileAnalysis]) -> dict:
        """Build a code graph from file analyses."""
        nodes = []
        edges = []
        node_ids = set()

        def add_node(nid, ntype, name, **kwargs):
            if nid not in node_ids:
                node_ids.add(nid)
                nodes.append({"id": nid, "type": ntype, "name": name, **kwargs})

        for fa in analyses:
            file_id = f"file:{fa.file_path}"
            add_node(file_id, "file", fa.file_path.name,
                     file_path=str(fa.file_path))

            for ent in fa.entities:
                ent_id = f"{ent.entity_type}:{fa.file_path}:{ent.name}:{ent.start_line}"
                add_node(ent_id, ent.entity_type, ent.name,
                         file_path=str(fa.file_path),
                         qualified_name=f"{ent.parent}.{ent.name}" if ent.parent else ent.name,
                         metadata={"start_line": ent.start_line, "end_line": ent.end_line,
                                   "parameters": ent.parameters})
                edges.append({"source": file_id, "target": ent_id, "type": "contains"})

            for imp in fa.imports:
                ext_id = f"external:{imp.source}"
                add_node(ext_id, "external_module", imp.source)
                edges.append({"source": file_id, "target": ext_id, "type": "imports",
                              "metadata": {"imported_names": imp.imported_names}})

            for call in fa.calls:
                caller_id = None
                for ent in fa.entities:
                    if ent.name == call.caller:
                        caller_id = f"{ent.entity_type}:{fa.file_path}:{ent.name}:{ent.start_line}"
                        break
                if not caller_id:
                    caller_id = file_id

                callee_id = f"unresolved:{call.callee}"
                add_node(callee_id, "variable", call.callee, metadata={"resolved": False})
                edges.append({"source": caller_id, "target": callee_id, "type": "calls",
                              "metadata": {"line": call.start_line, "resolved": False}})

        # Try to resolve cross-file calls
        entity_map = {}
        for n in nodes:
            if n["type"] in ("function", "method", "class"):
                entity_map[n["name"]] = n["id"]

        for edge in edges:
            if edge["type"] == "calls" and edge["target"].startswith("unresolved:"):
                callee_name = edge["target"].replace("unresolved:", "")
                if callee_name in entity_map:
                    edge["target"] = entity_map[callee_name]
                    edge["metadata"]["resolved"] = True

        return {"nodes": nodes, "edges": edges}

    def _detect_frameworks(self, workspace: Path, analyses: list[FileAnalysis]) -> list[str]:
        """Detect frameworks used in the repository."""
        frameworks = set()

        # Check package.json
        pkg_json = workspace / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                framework_hints = {
                    "react": "React", "next": "Next.js", "vue": "Vue",
                    "angular": "Angular", "svelte": "Svelte",
                    "express": "Express", "fastify": "Fastify",
                    "nestjs": "NestJS", "fastapi": "FastAPI",
                    "django": "Django", "flask": "Flask",
                }
                for dep in deps:
                    if dep in framework_hints:
                        frameworks.add(framework_hints[dep])
            except (json.JSONDecodeError, OSError):
                pass

        # Check requirements.txt / pyproject.toml
        for req_file in ["requirements.txt", "pyproject.toml"]:
            p = workspace / req_file
            if p.exists():
                try:
                    content = p.read_text()
                    if "fastapi" in content:
                        frameworks.add("FastAPI")
                    if "django" in content:
                        frameworks.add("Django")
                    if "flask" in content:
                        frameworks.add("Flask")
                except OSError:
                    pass

        return sorted(frameworks)

    def _detect_architecture(self, workspace: Path, analyses: list[FileAnalysis]) -> dict:
        """Detect architecture patterns."""
        dirs = set()
        for fa in analyses:
            parts = str(fa.file_path).split("/")
            if len(parts) > 1:
                dirs.add(parts[0])
                if len(parts) > 2:
                    dirs.add(f"{parts[0]}/{parts[1]}")

        patterns = []

        mvc_indicators = {"controllers", "models", "views", "routes", "services"}
        found_mvc = sum(1 for d in dirs if d.lower() in mvc_indicators or d.split("/")[-1].lower() in mvc_indicators)
        if found_mvc >= 2:
            patterns.append({"name": "MVC", "confidence": min(0.5 + found_mvc * 0.15, 0.95),
                           "evidence": [d for d in dirs if d.lower() in mvc_indicators]})

        layered_indicators = {"src", "lib", "app", "core", "utils", "services", "handlers"}
        found_layered = sum(1 for d in dirs if d.lower() in layered_indicators or d.split("/")[-1].lower() in layered_indicators)
        if found_layered >= 2:
            patterns.append({"name": "Layered Architecture", "confidence": min(0.4 + found_layered * 0.12, 0.9),
                           "evidence": [d for d in dirs if d.lower() in layered_indicators]})

        api_indicators = {"api", "routes", "endpoints", "controllers"}
        found_api = sum(1 for d in dirs if d.lower() in api_indicators or d.split("/")[-1].lower() in api_indicators)
        if found_api >= 1:
            patterns.append({"name": "REST API", "confidence": min(0.5 + found_api * 0.2, 0.9),
                           "evidence": [d for d in dirs if d.lower() in api_indicators]})

        component_indicators = {"components", "pages", "views"}
        found_components = sum(1 for d in dirs if d.lower() in component_indicators or d.split("/")[-1].lower() in component_indicators)
        if found_components >= 2:
            patterns.append({"name": "Component-based Frontend", "confidence": min(0.5 + found_components * 0.15, 0.9),
                           "evidence": [d for d in dirs if d.lower() in component_indicators]})

        if not patterns:
            patterns.append({"name": "Monolithic", "confidence": 0.6, "evidence": ["Default assumption"]})

        return {"patterns": patterns}

    def _detect_tech_stack(self, workspace: Path) -> dict:
        """Detect technology stack."""
        stack = {"frontend": [], "backend": [], "database": [], "infrastructure": []}

        pkg_json = workspace / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                frontend_libs = {"react", "vue", "angular", "svelte", "next", "nuxt", "remix", "solid-js"}
                backend_libs = {"express", "fastify", "hono", "nestjs", "koa"}
                db_libs = {"mongoose", "sequelize", "prisma", "typeorm", "knex", "pg", "mysql2", "better-sqlite3"}

                for dep in deps:
                    if dep in frontend_libs:
                        stack["frontend"].append(dep)
                    elif dep in backend_libs:
                        stack["backend"].append(dep)
                    elif dep in db_libs:
                        stack["database"].append(dep)
            except (json.JSONDecodeError, OSError):
                pass

        # Check for Docker
        if (workspace / "Dockerfile").exists():
            stack["infrastructure"].append("Docker")
        if (workspace / "docker-compose.yml").exists() or (workspace / "docker-compose.yaml").exists():
            stack["infrastructure"].append("Docker Compose")
        if (workspace / ".github" / "workflows").exists():
            stack["infrastructure"].append("GitHub Actions")

        return stack

    def _generate_beginner_analysis(self, repo, analyses, architecture, tech_stack) -> dict:
        """Generate beginner-level analysis."""
        languages = {}
        total_functions = 0
        total_classes = 0
        for fa in analyses:
            lang = fa.language
            languages[lang] = languages.get(lang, 0) + 1
            for ent in fa.entities:
                if ent.entity_type in ("function", "method"):
                    total_functions += 1
                elif ent.entity_type == "class":
                    total_classes += 1

        lang_list = ", ".join(languages.keys()) if languages else "unknown"
        framework_list = ", ".join(tech_stack.get("frontend", []) + tech_stack.get("backend", [])) if any(tech_stack.values()) else "not detected"

        structure_lines = []
        top_dirs = set()
        for fa in analyses:
            parts = str(fa.file_path).split("/")
            if len(parts) > 1:
                top_dirs.add(parts[0])
        for d in sorted(top_dirs):
            structure_lines.append(f"- `{d}/`")

        return {
            "project_overview": f"This is a {repo.name} repository owned by {repo.owner}. It contains {len(analyses)} source files written in {lang_list}.",
            "technology_explanation": f"The project uses {lang_list} as its primary language(s). {f'Frameworks detected: {framework_list}.' if framework_list != 'not detected' else 'No major frameworks were detected.'}",
            "repository_structure": "\n".join(structure_lines) if structure_lines else "Repository structure could not be determined.",
            "basic_flow": f"The application contains {total_functions} functions and {total_classes} classes across {len(analyses)} files.",
            "learning_path": f"Start by exploring the main source files, then look at the {', '.join(sorted(top_dirs)[:3]) if top_dirs else 'source'} directories to understand the application flow.",
        }

    def _generate_intermediate_analysis(self, repo, analyses, graph_data, architecture) -> dict:
        """Generate intermediate-level analysis."""
        patterns = architecture.get("patterns", [])
        arch_desc = "\n".join(
            f"- **{p['name']}** (confidence: {p.get('confidence', 0):.0%}): {', '.join(p.get('evidence', []))}"
            for p in patterns
        ) if patterns else "No specific architecture pattern detected."

        modules = []
        top_dirs = {}
        for fa in analyses:
            parts = str(fa.file_path).split("/")
            if len(parts) > 1:
                top = parts[0]
                if top not in top_dirs:
                    top_dirs[top] = {"files": 0, "functions": 0, "classes": 0}
                top_dirs[top]["files"] += 1
                for ent in fa.entities:
                    if ent.entity_type in ("function", "method"):
                        top_dirs[top]["functions"] += 1
                    elif ent.entity_type == "class":
                        top_dirs[top]["classes"] += 1

        for d, stats in sorted(top_dirs.items()):
            modules.append(f"- `{d}/`: {stats['files']} files, {stats['functions']} functions, {stats['classes']} classes")

        return {
            "architecture": arch_desc,
            "modules": "\n".join(modules) if modules else "No module structure detected.",
            "data_flow": f"Graph contains {len(graph_data.get('nodes', []))} nodes and {len(graph_data.get('edges', []))} edges.",
            "dependencies": f"Total imports: {sum(fa.imports.__len__() for fa in analyses)}. Total calls: {sum(fa.calls.__len__() for fa in analyses)}.",
        }

    def _generate_advanced_analysis(self, repo, analyses, graph_data, architecture) -> dict:
        """Generate advanced-level analysis."""
        # Complexity analysis
        func_complexities = []
        for fa in analyses:
            for ent in fa.entities:
                if ent.entity_type in ("function", "method"):
                    # Simple heuristic: count control structures
                    src = getattr(ent, 'source', '')
                    complexity = 1
                    for keyword in ["if ", "else ", "for ", "while ", "switch ", "catch ", "try ", "&&", "||"]:
                        complexity += src.lower().count(keyword)
                    func_complexities.append({"name": ent.name, "file": str(fa.file_path), "complexity": complexity})

        func_complexities.sort(key=lambda x: x["complexity"], reverse=True)

        # Find circular dependencies
        file_imports = {}
        for fa in analyses:
            file_str = str(fa.file_path)
            file_imports[file_str] = [imp.source for imp in fa.imports if imp.source.startswith(".")]

        circular = []
        for f, imports in file_imports.items():
            for imp in imports:
                # Simple check
                for f2, imports2 in file_imports.items():
                    if imp in f2 and f in imports2:
                        circular.append({"from": f, "to": f2})

        return {
            "complexity": json.dumps(func_complexities[:20], indent=2) if func_complexities else "No complexity data.",
            "security": "Security analysis requires deeper semantic analysis. Review authentication, input validation, and dependency vulnerabilities manually.",
            "call_graph_summary": f"Total call relationships: {len(graph_data.get('edges', []))}",
            "circular_dependencies": json.dumps(circular[:10], indent=2) if circular else "No circular dependencies detected.",
        }

    async def _run_command(self, cmd: list[str]):
        """Run a shell command asynchronously."""
        import asyncio
        from dataclasses import dataclass

        @dataclass
        class CmdResult:
            returncode: int
            stdout: str
            stderr: str

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return CmdResult(
            returncode=proc.returncode or 0,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )
