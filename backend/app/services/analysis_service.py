"""
Repository analysis orchestration service.

Multi-pass analysis pipeline:
  URL → Clone → Scan → Parse → Extract → Graph → Resolve →
  Detect Frameworks → Detect APIs → Detect DB → Architecture →
  Evidence → Three-Level Analysis → Store
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

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
from app.services.framework_analyzer import FrameworkAnalyzer, APIEndpoint, DatabaseModel
from app.services.evidence import EvidenceStore, Confidence

logger = logging.getLogger(__name__)

IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__",
    ".venv", "venv", "dist", "build", "target", "out",
    "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".idea", ".vscode", ".next", ".cache", "tmp", "temp",
}

SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".cpp",
    ".h", ".hpp", ".go", ".rs", ".rb",
}

CONFIG_FILES = {
    "package.json", "pyproject.toml", "requirements.txt", "setup.py",
    "Cargo.toml", "go.mod", "Gemfile", "pom.xml", "build.gradle",
    "docker-compose.yml", "docker-compose.yaml", "Dockerfile",
    "Makefile", "CMakeLists.txt", ".env.example",
    "tsconfig.json", "vite.config.ts", "vite.config.js",
    "next.config.js", "next.config.mjs", "webpack.config.js",
    ".eslintrc.js", ".prettierrc", "tailwind.config.js",
    "jest.config.js", "vitest.config.ts",
}

DOC_FILES = {"README.md", "README.rst", "README.txt", "CHANGELOG.md", "LICENSE", "CONTRIBUTING.md"}

TEST_PATTERNS = {"test", "tests", "__tests__", "spec", "specs"}
TEST_SUFFIXES = {"_test.py", "_test.js", "_test.ts", ".test.js", ".test.ts", ".test.tsx", ".test.jsx",
                 "_spec.js", "_spec.ts", ".spec.js", ".spec.ts"}


class RepositoryAnalyzer:
    """Multi-pass repository analysis engine."""

    def __init__(self):
        self._parsers: dict[str, BaseParser] = {
            ".js": JavaScriptParser(),
            ".jsx": JavaScriptParser(),
            ".ts": TypeScriptParser(),
            ".tsx": TypeScriptParser(),
            ".py": PythonParser(),
        }
        self._framework_analyzer = FrameworkAnalyzer()

    def parse_url(self, url: str) -> tuple[str, str]:
        url = url.rstrip("/").rstrip(".git")
        parts = url.split("github.com/")[-1].split("/")
        if len(parts) < 2:
            raise ValueError("Invalid GitHub URL")
        return parts[0], parts[1]

    async def clone_repository(self, url: str, db: AsyncSession) -> Repository:
        owner, name = self.parse_url(url)
        workspace = settings.REPOSITORIES_DIR / name

        if workspace.exists():
            shutil.rmtree(workspace)

        settings.REPOSITORIES_DIR.mkdir(parents=True, exist_ok=True)

        repo = Repository(
            url=url, name=name, owner=owner,
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

            result = await self._run_command(
                ["git", "-C", str(workspace), "rev-parse", "HEAD"]
            )
            repo.commit_sha = result.stdout.strip()[:8]

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
        """Full multi-pass analysis pipeline."""
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

        evidence = EvidenceStore()

        try:
            # === PASS 1: Scan and Parse ===
            repo.status = AnalysisStatus.SCANNING
            await db.commit()

            file_analyses = self._scan_and_parse(workspace)
            evidence.metrics.files_analyzed = len(file_analyses)
            evidence.metrics.files_with_errors = sum(1 for fa in file_analyses if fa.has_syntax_errors)
            if file_analyses:
                evidence.metrics.parse_success_rate = 1.0 - (evidence.metrics.files_with_errors / len(file_analyses))

            # === PASS 2: Store Files and Symbols ===
            repo.status = AnalysisStatus.PARSING
            await db.commit()

            file_ids = {}
            for fa in file_analyses:
                rf = RepositoryFile(
                    repository_id=repo.id,
                    path=str(fa.file_path),
                    language=fa.language,
                    size_bytes=len(fa.source.encode("utf-8")) if fa.source else 0,
                    category=self._classify_file(fa, workspace),
                    content=fa.source if fa.source and len(fa.source) < 500000 else None,
                    has_syntax_errors=1 if fa.has_syntax_errors else 0,
                    entity_count=len(fa.entities),
                    import_count=len(fa.imports),
                    export_count=len(fa.exports),
                    call_count=len(fa.calls),
                )
                db.add(rf)
                await db.flush()
                file_ids[str(fa.file_path)] = rf.id

                for ent in fa.entities:
                    sym = Symbol(
                        repository_id=repo.id,
                        file_id=rf.id,
                        name=ent.name,
                        qualified_name=f"{ent.parent_class}.{ent.name}" if ent.parent_class else ent.name,
                        symbol_type=ent.entity_type,
                        file_path=str(fa.file_path),
                        start_line=ent.start_line,
                        end_line=ent.end_line,
                        parameters=ent.parameters,
                        extra_metadata={
                            "is_async": ent.is_async,
                            "return_type": ent.return_type,
                            "decorators": ent.decorators,
                            "parent_class": ent.parent_class,
                            "docstring": ent.docstring[:200] if ent.docstring else None,
                        },
                    )
                    db.add(sym)
                    evidence.metrics.total_symbols += 1
                    if ent.entity_type == "function":
                        evidence.metrics.total_functions += 1
                    elif ent.entity_type == "class":
                        evidence.metrics.total_classes += 1
                    elif ent.entity_type == "method":
                        evidence.metrics.total_methods += 1

            # === PASS 3: Build Graph ===
            repo.status = AnalysisStatus.BUILDING_GRAPH
            await db.commit()

            graph_data = self._build_graph(file_analyses, file_ids)
            evidence.metrics.imports_resolved = graph_data.get("imports_resolved", 0)
            evidence.metrics.imports_unresolved = graph_data.get("imports_unresolved", 0)
            evidence.metrics.calls_resolved = graph_data.get("calls_resolved", 0)
            evidence.metrics.calls_unresolved = graph_data.get("calls_unresolved", 0)
            evidence.metrics.cross_file_references = graph_data.get("cross_file_refs", 0)
            evidence.metrics.total_imports = sum(fa.imports.__len__() for fa in file_analyses)
            evidence.metrics.total_exports = sum(fa.exports.__len__() for fa in file_analyses)
            evidence.metrics.total_calls = sum(fa.calls.__len__() for fa in file_analyses)

            for node in graph_data["nodes"]:
                db.add(GraphNodeDB(
                    repository_id=repo.id,
                    node_id=node["id"],
                    node_type=node["type"],
                    name=node["name"],
                    file_path=node.get("file_path"),
                    qualified_name=node.get("qualified_name"),
                    extra_metadata=node.get("metadata", {}),
                ))

            for edge in graph_data["edges"]:
                db.add(GraphEdgeDB(
                    repository_id=repo.id,
                    source_id=edge["source"],
                    target_id=edge["target"],
                    edge_type=edge["type"],
                    extra_metadata=edge.get("metadata", {}),
                ))

            # === PASS 4: Framework & API Detection ===
            repo.status = AnalysisStatus.ANALYZING
            await db.commit()

            frameworks = self._framework_analyzer.detect_frameworks(workspace, file_analyses)
            api_endpoints = self._framework_analyzer.detect_api_endpoints(file_analyses)
            db_models = self._framework_analyzer.detect_database_models(file_analyses)

            # Record framework evidence
            for fw in frameworks:
                evidence.add_high(
                    f"Detected framework: {fw.name}",
                    fw.evidence,
                    category="framework",
                )
                evidence.metrics.framework_confidence = max(evidence.metrics.framework_confidence, fw.confidence)

            # Record API endpoint evidence
            for ep in api_endpoints:
                evidence.add_high(
                    f"API endpoint: {ep.method} {ep.path}",
                    [f"{ep.file}:{ep.line}"],
                    category="api",
                )

            # Record DB model evidence
            for model in db_models:
                evidence.add_high(
                    f"Database model: {model.name} ({model.orm or 'unknown'} ORM)",
                    [f"{model.file}:{model.line}"],
                    category="database",
                )

            # === PASS 5: Architecture Detection ===
            architecture = self._detect_architecture(workspace, file_analyses, graph_data, evidence)

            # === PASS 6: Language Statistics ===
            languages = {}
            for fa in file_analyses:
                languages[fa.language] = languages.get(fa.language, 0) + 1
            evidence.metrics.languages_detected = languages

            # === PASS 7: Generate Analysis ===
            analysis = Analysis(
                repository_id=repo.id,
                total_files=len(file_analyses),
                total_source_files=len(file_analyses),
                total_functions=evidence.metrics.total_functions,
                total_classes=evidence.metrics.total_classes,
                total_imports=evidence.metrics.total_imports,
                total_exports=evidence.metrics.total_exports,
                total_calls=evidence.metrics.total_calls,
                languages=languages,
                frameworks=[fw.name for fw in frameworks],
                architecture=architecture,
                tech_stack=self._build_tech_stack(frameworks),
            )
            db.add(analysis)

            # Generate three-level analysis with evidence
            analysis.beginner_analysis = self._generate_beginner(
                repo, file_analyses, frameworks, api_endpoints, db_models, architecture, evidence
            )
            analysis.intermediate_analysis = self._generate_intermediate(
                repo, file_analyses, graph_data, frameworks, api_endpoints, db_models, architecture, evidence
            )
            analysis.advanced_analysis = self._generate_advanced(
                repo, file_analyses, graph_data, api_endpoints, db_models, architecture, evidence
            )

            repo.status = AnalysisStatus.COMPLETED
            repo.updated_at = datetime.utcnow()
            await db.commit()

        except Exception as e:
            logger.exception("Analysis failed for repo %d", repo.id)
            repo.status = AnalysisStatus.FAILED
            repo.error_message = str(e)
            await db.commit()

    # ==================================================================
    # PASS 1: Scan and Parse
    # ==================================================================

    def _scan_and_parse(self, workspace: Path) -> list[FileAnalysis]:
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
                analyses.append(fa)
            except Exception as e:
                logger.warning("Failed to parse %s: %s", file_path, e)

        return sorted(analyses, key=lambda a: str(a.file_path))

    def _iter_source_files(self, workspace: Path):
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
                elif entry.is_file():
                    ext = entry.suffix.lower()
                    if ext in SOURCE_EXTENSIONS:
                        yield entry

    # ==================================================================
    # PASS 3: Graph Building with Cross-File Resolution
    # ==================================================================

    def _build_graph(self, analyses: list[FileAnalysis], file_ids: dict[str, int]) -> dict:
        """Build code graph with import-based cross-file resolution."""
        nodes = []
        edges = []
        node_ids = set()
        imports_resolved = 0
        imports_unresolved = 0
        calls_resolved = 0
        calls_unresolved = 0
        cross_file_refs = 0

        def add_node(nid, ntype, name, **kwargs):
            if nid not in node_ids:
                node_ids.add(nid)
                nodes.append({"id": nid, "type": ntype, "name": name, **kwargs})

        # Build file path -> file_id mapping
        file_path_map = {str(fa.file_path): fa for fa in analyses}

        # Build symbol index: name -> list of (file_path, entity_type, node_id)
        symbol_index: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

        # Build export index: file_path -> {exported_name -> entity_info}
        export_index: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)

        # === First pass: Create all nodes ===
        for fa in analyses:
            file_id = f"file:{fa.file_path}"
            add_node(file_id, "file", fa.file_path.name,
                     file_path=str(fa.file_path))

            for ent in fa.entities:
                ent_id = f"{ent.entity_type}:{fa.file_path}:{ent.name}:{ent.start_line}"
                add_node(ent_id, ent.entity_type, ent.name,
                         file_path=str(fa.file_path),
                         qualified_name=f"{ent.parent_class}.{ent.name}" if ent.parent_class else ent.name,
                         metadata={
                             "start_line": ent.start_line,
                             "end_line": ent.end_line,
                             "parameters": ent.parameters,
                             "return_type": ent.return_type,
                             "is_async": ent.is_async,
                             "decorators": ent.decorators,
                             "parent_class": ent.parent_class,
                             "docstring": ent.docstring[:200] if ent.docstring else None,
                         })
                edges.append({"source": file_id, "target": ent_id, "type": "contains"})

                # Register in symbol index
                symbol_index[ent.name].append((str(fa.file_path), ent.entity_type, ent_id))
                if ent.parent_class:
                    qualified = f"{ent.parent_class}.{ent.name}"
                    symbol_index[qualified].append((str(fa.file_path), ent.entity_type, ent_id))

            # Register exports
            for exp in fa.exports:
                for name in exp.exported_names:
                    export_index[str(fa.file_path)][name] = ("export", "")

        # === Second pass: Create import and call edges with resolution ===
        for fa in analyses:
            file_id = f"file:{fa.file_path}"

            for imp in fa.imports:
                source = imp.source

                # Try to resolve local imports
                if source.startswith("."):
                    resolved_file = self._resolve_import_path(source, fa.file_path, file_path_map)
                    if resolved_file:
                        target_file_id = f"file:{resolved_file}"
                        imports_resolved += 1

                        # File-level import
                        edges.append({
                            "source": file_id,
                            "target": target_file_id,
                            "type": "imports",
                            "metadata": {"source": source, "line": imp.start_line, "resolved": True},
                        })
                        cross_file_refs += 1

                        # Symbol-level import: try to resolve each imported name
                        for name in imp.imported_names:
                            if name == "*":
                                continue
                            # Look up in the target file's exports first, then symbols
                            target_symbols = symbol_index.get(name, [])
                            for (tfile, ttype, tid) in target_symbols:
                                if tfile == str(resolved_file):
                                    edges.append({
                                        "source": file_id,
                                        "target": tid,
                                        "type": "imports",
                                        "metadata": {
                                            "source": source,
                                            "symbol": name,
                                            "line": imp.start_line,
                                            "resolved": True,
                                        },
                                    })
                                    break
                    else:
                        imports_unresolved += 1
                        ext_id = f"external:{source}"
                        add_node(ext_id, "external_module", source)
                        edges.append({
                            "source": file_id,
                            "target": ext_id,
                            "type": "imports",
                            "metadata": {"source": source, "line": imp.start_line, "resolved": False},
                        })
                else:
                    # External package import
                    ext_id = f"external:{source}"
                    add_node(ext_id, "external_module", source)
                    edges.append({
                        "source": file_id,
                        "target": ext_id,
                        "type": "imports",
                        "metadata": {"source": source, "line": imp.start_line, "imported_names": imp.imported_names},
                    })

            # Create call edges
            for call in fa.calls:
                caller_id = None
                # Find enclosing function
                for ent in fa.entities:
                    if ent.entity_type in ("function", "method"):
                        if ent.start_line <= call.start_line <= ent.end_line:
                            caller_id = f"{ent.entity_type}:{fa.file_path}:{ent.name}:{ent.start_line}"
                            break
                if not caller_id:
                    caller_id = file_id

                # Try to resolve callee
                callee_name = call.callee.split(".")[-1]  # Strip method chain prefix
                resolved = False
                target_id = None

                # Strategy 1: Same-file symbol
                candidates = symbol_index.get(callee_name, [])
                same_file = [(t, ty, tid) for (t, ty, tid) in candidates if t == str(fa.file_path)]
                if len(same_file) == 1:
                    target_id = same_file[0][2]
                    resolved = True
                elif len(same_file) > 1:
                    # Multiple in same file - use first (could be more sophisticated)
                    target_id = same_file[0][2]
                    resolved = True

                # Strategy 2: Import-resolved symbol
                if not resolved:
                    # Check imports in this file
                    for imp in fa.imports:
                        if callee_name in imp.imported_names:
                            resolved_file = self._resolve_import_path(imp.source, fa.file_path, file_path_map)
                            if resolved_file:
                                for (tfile, ttype, tid) in symbol_index.get(callee_name, []):
                                    if tfile == str(resolved_file):
                                        target_id = tid
                                        resolved = True
                                        break
                        if resolved:
                            break

                # Strategy 3: Repository-wide unique symbol
                if not resolved and len(candidates) == 1:
                    target_id = candidates[0][2]
                    resolved = True

                if resolved and target_id:
                    calls_resolved += 1
                    edges.append({
                        "source": caller_id,
                        "target": target_id,
                        "type": "calls",
                        "metadata": {
                            "line": call.start_line,
                            "resolved": True,
                            "callee": call.callee,
                        },
                    })
                    if caller_id.startswith("file:") or target_id.startswith("file:"):
                        cross_file_refs += 1
                else:
                    calls_unresolved += 1
                    unresolved_id = f"unresolved:{call.callee}"
                    add_node(unresolved_id, "variable", call.callee,
                             metadata={"resolved": False, "reason": "No matching definition found"})
                    edges.append({
                        "source": caller_id,
                        "target": unresolved_id,
                        "type": "calls",
                        "metadata": {
                            "line": call.start_line,
                            "resolved": False,
                            "callee": call.callee,
                        },
                    })

        return {
            "nodes": nodes,
            "edges": edges,
            "imports_resolved": imports_resolved,
            "imports_unresolved": imports_unresolved,
            "calls_resolved": calls_resolved,
            "calls_unresolved": calls_unresolved,
            "cross_file_refs": cross_file_refs,
        }

    def _resolve_import_path(self, source: str, current_file: Path, file_path_map: dict) -> str | None:
        """Resolve a relative import to an actual file path."""
        parent = current_file.parent
        candidates = [
            parent / source,
            parent / (source + ".js"),
            parent / (source + ".jsx"),
            parent / (source + ".ts"),
            parent / (source + ".tsx"),
            parent / (source + ".py"),
            parent / (source + ".mjs"),
            parent / source / "index.js",
            parent / source / "index.jsx",
            parent / source / "index.ts",
            parent / source / "index.tsx",
            parent / source / "index.py",
            parent / source / "__init__.py",
        ]

        for candidate in candidates:
            # Normalize path
            try:
                normalized = str(Path(os.path.normpath(str(candidate))))
            except (ValueError, OSError):
                continue
            if normalized in file_path_map:
                return normalized

        return None

    # ==================================================================
    # PASS 5: Architecture Detection
    # ==================================================================

    def _detect_architecture(self, workspace: Path, analyses: list[FileAnalysis],
                              graph_data: dict, evidence: EvidenceStore) -> dict:
        """Detect architecture patterns with evidence."""
        patterns = []

        # Analyze actual import relationships, not just folder names
        file_imports = defaultdict(set)
        file_by_path = {}
        for fa in analyses:
            fp = str(fa.file_path)
            file_by_path[fp] = fa
            for imp in fa.imports:
                if imp.source.startswith("."):
                    file_imports[fp].add(imp.source)

        # Analyze directory structure
        dir_files = defaultdict(list)
        for fa in analyses:
            parts = str(fa.file_path).split("/")
            if len(parts) > 1:
                dir_files[parts[0]].append(fa)

        # Detect MVC/Layered by analyzing call flow
        controller_like = set()
        service_like = set()
        model_like = set()
        route_like = set()

        for fa in analyses:
            fp = str(fa.file_path).lower()
            for ent in fa.entities:
                ename = ent.name.lower()
                eparent = (ent.parent_class or "").lower()
                decorators_lower = [d.lower() for d in ent.decorators]

                # Controller detection
                if any(d in fp for d in ["controller", "handler"]):
                    controller_like.add(str(fa.file_path))
                if any(d in ename for d in ["controller", "handler"]):
                    controller_like.add(str(fa.file_path))

                # Service detection
                if any(d in fp for d in ["service", "usecase", "interactor"]):
                    service_like.add(str(fa.file_path))
                if any(d in ename for d in ["service", "usecase"]):
                    service_like.add(str(fa.file_path))

                # Model detection
                if any(d in fp for d in ["model", "entity", "schema"]):
                    model_like.add(str(fa.file_path))

                # Route detection
                if any(d in fp for d in ["route", "router"]):
                    route_like.add(str(fa.file_path))

        # MVC pattern
        if controller_like and (service_like or model_like):
            evidence.add_high(
                "MVC/Layered architecture detected",
                [f"Controllers: {len(controller_like)} files", f"Services: {len(service_like)} files",
                 f"Models: {len(model_like)} files"],
                category="architecture",
            )
            patterns.append({
                "name": "MVC / Layered Architecture",
                "confidence": min(0.5 + (len(controller_like) + len(service_like) + len(model_like)) * 0.05, 0.9),
                "evidence": list(controller_like | service_like | model_like)[:10],
            })

        # API-first pattern
        api_dirs = {d for d in dir_files if any(k in d.lower() for k in ["api", "routes", "endpoints"])}
        if api_dirs:
            patterns.append({
                "name": "API-First Architecture",
                "confidence": min(0.5 + len(api_dirs) * 0.15, 0.85),
                "evidence": list(api_dirs),
            })

        # Component-based frontend
        component_dirs = {d for d in dir_files if any(k in d.lower() for k in ["component", "view", "page"])}
        if component_dirs and len(component_dirs) >= 2:
            patterns.append({
                "name": "Component-Based Frontend",
                "confidence": min(0.5 + len(component_dirs) * 0.1, 0.9),
                "evidence": list(component_dirs),
            })

        # Module/package pattern
        if len(dir_files) > 3:
            avg_files = sum(len(v) for v in dir_files.values()) / len(dir_files)
            if avg_files < 10:
                patterns.append({
                    "name": "Modular Architecture",
                    "confidence": 0.6,
                    "evidence": [f"{len(dir_files)} top-level modules"],
                })

        if not patterns:
            patterns.append({
                "name": "Standard Repository Structure",
                "confidence": 0.5,
                "evidence": ["Default based on directory structure"],
            })

        # Compute architecture confidence
        max_confidence = max(p["confidence"] for p in patterns) if patterns else 0.0
        evidence.metrics.architecture_confidence = max_confidence

        return {"patterns": patterns}

    # ==================================================================
    # PASS 7: Three-Level Analysis Generation
    # ==================================================================

    def _generate_beginner(self, repo, analyses, frameworks, api_endpoints, db_models,
                           architecture, evidence: EvidenceStore) -> dict:
        """Generate beginner-level analysis grounded in evidence."""

        # Collect key files
        entry_points = self._find_entry_points(analyses)
        languages = {}
        for fa in analyses:
            languages[fa.language] = languages.get(fa.language, 0) + 1

        lang_list = ", ".join(sorted(languages.keys())) if languages else "unknown"
        fw_names = [fw.name for fw in frameworks if fw.category in ("frontend", "backend", "fullstack")]
        fw_str = ", ".join(fw_names) if fw_names else "no specific framework detected"

        # Build structure description
        dir_structure = self._describe_directory_structure(analyses)

        # Build what-the-project-does description from entry points and exports
        project_purpose = self._infer_project_purpose(analyses, frameworks, api_endpoints)

        # Build data flow description
        flow_desc = self._describe_basic_flow(analyses, api_endpoints, entry_points)

        return {
            "project_overview": project_purpose,
            "technology_explanation": f"This project is written in {lang_list} and uses {fw_str}.",
            "repository_structure": dir_structure,
            "basic_flow": flow_desc,
            "learning_path": self._suggest_learning_path(analyses, entry_points),
            "entry_points": [str(ep) for ep in entry_points[:5]],
        }

    def _generate_intermediate(self, repo, analyses, graph_data, frameworks, api_endpoints,
                                db_models, architecture, evidence: EvidenceStore) -> dict:
        """Generate intermediate-level analysis grounded in evidence."""

        # Module analysis
        modules = self._analyze_modules(analyses)

        # Architecture description
        arch_desc = self._describe_architecture(architecture, evidence)

        # Dependency direction analysis
        dep_analysis = self._analyze_dependency_direction(analyses)

        # API surface
        api_desc = self._describe_api_surface(api_endpoints)

        # Data flow
        data_flow = self._describe_data_flow(analyses, api_endpoints, db_models)

        # Important functions
        important = self._find_important_functions(analyses, graph_data)

        return {
            "architecture": arch_desc,
            "modules": modules,
            "data_flow": data_flow,
            "dependencies": dep_analysis,
            "api_surface": api_desc,
            "important_functions": important,
        }

    def _generate_advanced(self, repo, analyses, graph_data, api_endpoints,
                            db_models, architecture, evidence: EvidenceStore) -> dict:
        """Generate advanced-level analysis grounded in evidence."""

        # Real complexity analysis
        complexity = self._compute_complexity(analyses)

        # Call graph analysis
        call_analysis = self._analyze_call_graph(graph_data)

        # Coupling analysis
        coupling = self._analyze_coupling(analyses, graph_data)

        # Dead code detection
        dead_code = self._detect_dead_code(analyses, graph_data)

        # Security observations
        security = self._analyze_security(analyses)

        # Circular dependencies
        circular = self._detect_circular_dependencies(analyses)

        return {
            "complexity": complexity,
            "call_graph_summary": call_analysis,
            "coupling_analysis": coupling,
            "dead_code_candidates": dead_code,
            "security_observations": security,
            "circular_dependencies": circular,
        }

    # ==================================================================
    # Helper Methods for Analysis Generation
    # ==================================================================

    def _find_entry_points(self, analyses: list[FileAnalysis]) -> list[str]:
        """Find likely application entry points."""
        entry_points = []
        entry_names = {"main", "index", "app", "server", "manage", "__main__",
                       "Application", "App", "create_app", "factory"}
        for fa in analyses:
            fp = str(fa.file_path)
            # Check filename
            stem = fa.file_path.stem.lower()
            if stem in ("main", "index", "app", "server", "manage", "__main__"):
                entry_points.append(fp)
            # Check for main function
            for ent in fa.entities:
                if ent.name in entry_names or ent.name.startswith("main"):
                    entry_points.append(fp)
                    break
            # Check package.json scripts
            if fa.file_path.name == "package.json":
                entry_points.append(fp)
        return entry_points

    def _infer_project_purpose(self, analyses, frameworks, api_endpoints) -> str:
        """Infer what the project does from its structure and code."""
        parts = []

        fw_names = [fw.name for fw in frameworks]
        if "React" in fw_names or "Next.js" in fw_names or "Vue.js" in fw_names:
            parts.append("This is a web application")
        elif "Express" in fw_names or "Fastify" in fw_names or "FastAPI" in fw_names:
            parts.append("This is a backend API service")
        elif "Django" in fw_names:
            parts.append("This is a full-stack web application")
        else:
            parts.append("This is a software project")

        if api_endpoints:
            parts.append(f"that exposes {len(api_endpoints)} API endpoint(s)")

        db_count = sum(1 for fa in analyses for ent in fa.entities
                      if ent.entity_type == "class" and ent.parent_class
                      and any(p in (ent.parent_class or "") for p in ["Base", "Model", "Document"]))

        if db_count > 0:
            parts.append(f"with {db_count} database model(s)")

        lang_set = set(fa.language for fa in analyses)
        if lang_set:
            parts.append(f"written in {', '.join(sorted(lang_set))}")

        return ". ".join(parts) + "." if parts else "A software project."

    def _describe_directory_structure(self, analyses: list[FileAnalysis]) -> str:
        """Describe the top-level directory structure."""
        dir_stats = defaultdict(lambda: {"files": 0, "languages": set(), "key_files": []})
        for fa in analyses:
            parts = str(fa.file_path).split("/")
            top = parts[0] if len(parts) > 1 else "."
            dir_stats[top]["files"] += 1
            dir_stats[top]["languages"].add(fa.language)
            if len(parts) <= 2:
                dir_stats[top]["key_files"].append(parts[-1])

        lines = []
        for d, stats in sorted(dir_stats.items(), key=lambda x: -x[1]["files"]):
            langs = ", ".join(sorted(stats["languages"]))
            lines.append(f"- **`{d}/`** — {stats['files']} file(s), languages: {langs}")

        return "\n".join(lines) if lines else "Flat repository structure."

    def _describe_basic_flow(self, analyses, api_endpoints, entry_points) -> str:
        """Describe the basic application flow."""
        parts = []

        if entry_points:
            parts.append(f"The application starts from {', '.join(f'`{ep}`' for ep in entry_points[:3])}.")

        if api_endpoints:
            methods = defaultdict(int)
            for ep in api_endpoints:
                methods[ep.method] += 1
            method_str = ", ".join(f"{m}: {c}" for m, c in sorted(methods.items()))
            parts.append(f"It exposes {len(api_endpoints)} API endpoint(s) ({method_str}).")

        # Describe import flow
        file_count = len(analyses)
        if file_count > 1:
            parts.append(f"The codebase consists of {file_count} source files with inter-module dependencies.")

        return " ".join(parts) if parts else "Application flow analysis requires more entry points."

    def _suggest_learning_path(self, analyses, entry_points) -> str:
        """Suggest what to read first."""
        parts = ["Start by reading the entry point(s):"]
        for ep in entry_points[:3]:
            parts.append(f"  1. `{ep}`")

        # Find the most-imported files (key modules)
        import_counts = defaultdict(int)
        for fa in analyses:
            for imp in fa.imports:
                if imp.source.startswith("."):
                    import_counts[imp.source] += 1

        if import_counts:
            top_imports = sorted(import_counts.items(), key=lambda x: -x[1])[:5]
            parts.append("\nThen explore the most-imported modules:")
            for imp, count in top_imports:
                parts.append(f"  - `{imp}` (imported {count} time(s))")

        return "\n".join(parts)

    def _analyze_modules(self, analyses: list[FileAnalysis]) -> str:
        """Analyze module responsibilities."""
        modules = defaultdict(lambda: {"files": 0, "functions": 0, "classes": 0, "imports": 0})
        for fa in analyses:
            parts = str(fa.file_path).split("/")
            top = parts[0] if len(parts) > 1 else "."
            modules[top]["files"] += 1
            for ent in fa.entities:
                if ent.entity_type in ("function", "method"):
                    modules[top]["functions"] += 1
                elif ent.entity_type == "class":
                    modules[top]["classes"] += 1
            modules[top]["imports"] += len(fa.imports)

        lines = []
        for mod, stats in sorted(modules.items(), key=lambda x: -x[1]["files"]):
            lines.append(f"- **`{mod}/`**: {stats['files']} files, {stats['functions']} functions, "
                        f"{stats['classes']} classes, {stats['imports']} imports")

        return "\n".join(lines) if lines else "No module structure detected."

    def _describe_architecture(self, architecture: dict, evidence: EvidenceStore) -> str:
        """Describe architecture with confidence."""
        patterns = architecture.get("patterns", [])
        lines = []
        for p in patterns:
            conf = p.get("confidence", 0)
            conf_label = "high" if conf > 0.7 else "medium" if conf > 0.4 else "low"
            lines.append(f"**{p['name']}** (confidence: {conf:.0%}, {conf_label})")
            if p.get("evidence"):
                for ev in p["evidence"][:5]:
                    lines.append(f"  - `{ev}`")
        return "\n".join(lines) if lines else "Architecture could not be determined."

    def _analyze_dependency_direction(self, analyses: list[FileAnalysis]) -> str:
        """Analyze dependency direction between modules."""
        dir_imports = defaultdict(lambda: defaultdict(int))
        for fa in analyses:
            parts = str(fa.file_path).split("/")
            source_dir = parts[0] if len(parts) > 1 else "."
            for imp in fa.imports:
                if imp.source.startswith("."):
                    # Determine target directory
                    target_path = str(fa.file_path.parent / imp.source)
                    target_parts = target_path.split("/")
                    target_dir = target_parts[0] if len(target_parts) > 1 else "."
                    if source_dir != target_dir:
                        dir_imports[source_dir][target_dir] += 1

        if not dir_imports:
            return "All imports are within the same module."

        lines = ["Cross-module dependencies:"]
        for source, targets in sorted(dir_imports.items()):
            for target, count in sorted(targets.items(), key=lambda x: -x[1]):
                lines.append(f"  - `{source}/` → `{target}/` ({count} import(s))")

        return "\n".join(lines)

    def _describe_api_surface(self, api_endpoints: list[APIEndpoint]) -> str:
        """Describe the API surface."""
        if not api_endpoints:
            return "No API endpoints detected."

        by_method = defaultdict(list)
        for ep in api_endpoints:
            by_method[ep.method].append(ep)

        lines = [f"Total endpoints: {len(api_endpoints)}"]
        for method, eps in sorted(by_method.items()):
            lines.append(f"\n**{method}** ({len(eps)}):")
            for ep in eps[:10]:
                lines.append(f"  - `{ep.path}` → `{ep.file}:{ep.line}`")

        return "\n".join(lines)

    def _describe_data_flow(self, analyses, api_endpoints, db_models) -> str:
        """Describe data flow through the application."""
        parts = []

        if api_endpoints:
            parts.append(f"Data enters through {len(api_endpoints)} API endpoint(s).")

        if db_models:
            parts.append(f"Data is stored in {len(db_models)} database model(s):")
            for m in db_models[:5]:
                fields_str = ", ".join(m.fields[:5]) if m.fields else "schema not analyzed"
                parts.append(f"  - `{m.name}` ({m.orm or 'unknown'}): {fields_str}")

        # Describe call flow
        call_chains = self._find_call_chains(analyses)
        if call_chains:
            parts.append("\nKey data flow paths:")
            for chain in call_chains[:3]:
                parts.append(f"  {' → '.join(chain)}")

        return "\n".join(parts) if parts else "Data flow analysis requires more context."

    def _find_call_chains(self, analyses: list[FileAnalysis]) -> list[list[str]]:
        """Find notable call chains."""
        chains = []
        for fa in analyses:
            for ent in fa.entities:
                if ent.entity_type in ("function", "method"):
                    # Find what this function calls
                    calls_in_func = [c for c in fa.calls if c.caller == ent.name]
                    if calls_in_func:
                        chain = [ent.name]
                        for call in calls_in_func[:2]:
                            chain.append(call.callee.split(".")[-1])
                        chains.append(chain)
        return chains[:5]

    def _find_important_functions(self, analyses: list[FileAnalysis], graph_data: dict) -> str:
        """Find the most important functions based on call count."""
        # Count callers for each function
        caller_counts = defaultdict(int)
        for edge in graph_data["edges"]:
            if edge["type"] == "calls" and edge.get("metadata", {}).get("resolved"):
                caller_counts[edge["target"]] += 1

        # Find top functions
        top_functions = sorted(caller_counts.items(), key=lambda x: -x[1])[:10]

        if not top_functions:
            return "No function importance data available."

        lines = ["Most-called functions (by number of callers):"]
        for func_id, count in top_functions:
            # Extract name from ID
            parts = func_id.split(":")
            if len(parts) >= 3:
                name = parts[2]
                filepath = parts[1] if len(parts) > 1 else "unknown"
                lines.append(f"- `{name}` in `{filepath}` — called by {count} other(s)")

        return "\n".join(lines)

    def _compute_complexity(self, analyses: list[FileAnalysis]) -> str:
        """Compute cyclomatic complexity for functions."""
        results = []
        for fa in analyses:
            for ent in fa.entities:
                if ent.entity_type in ("function", "method") and ent.source:
                    complexity = self._cyclomatic_complexity(ent.source)
                    if complexity > 1:
                        results.append({
                            "name": ent.name,
                            "file": str(fa.file_path),
                            "line": ent.start_line,
                            "complexity": complexity,
                            "rating": "simple" if complexity <= 5 else "moderate" if complexity <= 10 else "complex",
                        })

        results.sort(key=lambda x: -x["complexity"])

        if not results:
            return "No complexity data available."

        lines = ["Function complexity analysis (cyclomatic complexity):"]
        for r in results[:15]:
            lines.append(f"- `{r['name']}` ({r['file']}:{r['line']}): "
                        f"complexity={r['complexity']}, rating={r['rating']}")

        avg = sum(r["complexity"] for r in results) / len(results) if results else 0
        lines.append(f"\nAverage complexity: {avg:.1f}")
        lines.append(f"Functions analyzed: {len(results)}")

        return "\n".join(lines)

    def _cyclomatic_complexity(self, source: str) -> int:
        """Calculate cyclomatic complexity from source code."""
        complexity = 1  # Base complexity
        # Count decision points
        decision_keywords = [
            r'\bif\b', r'\belse\s+if\b', r'\belif\b',
            r'\bfor\b', r'\bwhile\b', r'\bswitch\b',
            r'\bcase\b', r'\bcatch\b', r'\bexcept\b',
            r'\b&&\b', r'\b\|\|\b', r'\b\?\b',
            r'\band\b', r'\bor\b',
            r'\btry\b',
        ]
        for pattern in decision_keywords:
            complexity += len(re.findall(pattern, source))
        return complexity

    def _analyze_call_graph(self, graph_data: dict) -> str:
        """Analyze the call graph structure."""
        total_edges = len(graph_data["edges"])
        call_edges = [e for e in graph_data["edges"] if e["type"] == "calls"]
        resolved = sum(1 for e in call_edges if e.get("metadata", {}).get("resolved"))

        lines = [
            f"Total graph edges: {total_edges}",
            f"Call edges: {len(call_edges)}",
            f"Resolved calls: {resolved}/{len(call_edges)} ({resolved/len(call_edges)*100:.0f}%)" if call_edges else "No calls",
            f"Unresolved calls: {len(call_edges) - resolved}",
        ]

        return "\n".join(lines)

    def _analyze_coupling(self, analyses: list[FileAnalysis], graph_data: dict) -> str:
        """Analyze module coupling."""
        file_deps = defaultdict(set)
        for edge in graph_data["edges"]:
            if edge["type"] == "imports":
                source_file = edge["source"].replace("file:", "")
                target_file = edge["target"].replace("file:", "")
                if source_file != target_file:
                    file_deps[source_file].add(target_file)

        if not file_deps:
            return "No cross-file dependencies detected."

        # Find most coupled files
        coupled = sorted(file_deps.items(), key=lambda x: -len(x[1]))[:10]

        lines = ["Most coupled files (highest fan-out):"]
        for fp, deps in coupled:
            lines.append(f"- `{fp}` depends on {len(deps)} other file(s)")

        # Find files with most dependents (highest fan-in)
        dependents = defaultdict(set)
        for fp, deps in file_deps.items():
            for d in deps:
                dependents[d].add(fp)

        most_depended = sorted(dependents.items(), key=lambda x: -len(x[1]))[:5]
        if most_depended:
            lines.append("\nMost depended-upon files (highest fan-in):")
            for fp, deps in most_depended:
                lines.append(f"- `{fp}` used by {len(deps)} other file(s)")

        return "\n".join(lines)

    def _detect_dead_code(self, analyses: list[FileAnalysis], graph_data: dict) -> str:
        """Detect potentially dead (unreferenced) functions."""
        # Find all functions
        all_functions = {}
        for fa in analyses:
            for ent in fa.entities:
                if ent.entity_type == "function":
                    fid = f"{ent.entity_type}:{fa.file_path}:{ent.name}:{ent.start_line}"
                    all_functions[fid] = ent

        # Find all call targets
        called = set()
        imported = set()
        for edge in graph_data["edges"]:
            if edge["type"] == "calls":
                called.add(edge["target"])
            if edge["type"] == "imports" and not edge["target"].startswith("file:"):
                imported.add(edge["target"])

        # Find functions that are neither called nor exported
        dead = []
        for fid, ent in all_functions.items():
            if fid not in called and ent.name not in ("main", "index", "__init__", "App", "app"):
                # Check if it's exported
                is_exported = any(
                    e["type"] == "exports" and e["source"] == fid
                    for e in graph_data["edges"]
                )
                if not is_exported:
                    dead.append(ent)

        if not dead:
            return "No obvious dead code detected."

        lines = [f"Potentially unreferenced functions ({len(dead)} found):"]
        for ent in dead[:10]:
            lines.append(f"- `{ent.name}` at line {ent.start_line}")

        if len(dead) > 10:
            lines.append(f"  ... and {len(dead) - 10} more")

        lines.append("\nNote: These functions may be referenced dynamically, used as callbacks, or called via reflection. Manual verification is recommended.")

        return "\n".join(lines)

    def _analyze_security(self, analyses: list[FileAnalysis]) -> str:
        """Analyze security-sensitive code patterns."""
        observations = []
        for fa in analyses:
            src = fa.source if hasattr(fa, 'source') else ""
            if not src:
                continue

            # Check for potential security issues
            if "eval(" in src:
                observations.append(f"⚠️ `eval()` usage in `{fa.file_path}` — potential code injection risk")
            if "exec(" in src:
                observations.append(f"⚠️ `exec()` usage in `{fa.file_path}` — potential code injection risk")
            if "subprocess" in src and "shell=True" in src:
                observations.append(f"⚠️ Shell=True in subprocess call in `{fa.file_path}` — command injection risk")
            if "os.system(" in src:
                observations.append(f"⚠️ `os.system()` usage in `{fa.file_path}` — command injection risk")
            if "innerHTML" in src:
                observations.append(f"⚠️ `innerHTML` usage in `{fa.file_path}` — potential XSS risk")
            if "dangerouslySetInnerHTML" in src:
                observations.append(f"⚠️ `dangerouslySetInnerHTML` in `{fa.file_path}` — potential XSS risk")

            # Check for hardcoded secrets (basic pattern)
            secret_patterns = [
                (r'(?:password|secret|api_key|apikey|token)\s*=\s*["\'][^"\']+["\']', "hardcoded secret"),
            ]
            for pattern, desc in secret_patterns:
                matches = re.findall(pattern, src, re.IGNORECASE)
                if matches:
                    observations.append(f"⚠️ Possible {desc} in `{fa.file_path}` — verify this is not a real credential")

        if not observations:
            return "No obvious security concerns detected in the source code."

        return "\n".join(["Security observations:"] + observations)

    def _detect_circular_dependencies(self, analyses: list[FileAnalysis]) -> str:
        """Detect circular import dependencies."""
        # Build import graph
        import_graph = defaultdict(set)
        for fa in analyses:
            fp = str(fa.file_path)
            for imp in fa.imports:
                if imp.source.startswith("."):
                    # Simplified: treat source as the target
                    target = imp.source.lstrip(".")
                    import_graph[fp].add(target)

        # Find cycles using DFS
        cycles = []
        visited = set()
        path = []

        def dfs(node):
            if node in path:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            path.append(node)
            for neighbor in import_graph.get(node, set()):
                dfs(neighbor)
            path.pop()

        for node in import_graph:
            dfs(node)

        if not cycles:
            return "No circular dependencies detected."

        lines = [f"Circular dependencies detected ({len(cycles)} cycle(s)):"]
        for cycle in cycles[:5]:
            lines.append(f"  {' → '.join(cycle)}")

        return "\n".join(lines)

    # ==================================================================
    # Tech Stack Builder
    # ==================================================================

    def _build_tech_stack(self, frameworks) -> dict:
        stack = {"frontend": [], "backend": [], "database": [], "infrastructure": [], "testing": [], "build": []}
        for fw in frameworks:
            cat = fw.category
            if cat in stack:
                stack[cat].append(fw.name)
        return stack

    def _classify_file(self, fa: FileAnalysis, workspace: Path) -> str:
        """Classify a file's category."""
        fp = str(fa.file_path).lower()
        name = fa.file_path.name.lower()

        # Test files
        if any(tp in fp for tp in TEST_PATTERNS) or any(name.endswith(ts) for ts in TEST_SUFFIXES):
            return "test"

        # Config files
        if name in {c.lower() for c in CONFIG_FILES}:
            return "configuration"

        # Doc files
        if name in {d.lower() for d in DOC_FILES}:
            return "documentation"

        # Source files
        if fa.language:
            return "source"

        return "other"

    # ==================================================================
    # Command Runner
    # ==================================================================

    async def _run_command(self, cmd: list[str]):
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
