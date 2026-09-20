"""
Framework-aware analysis for common web frameworks.

Detects framework-specific patterns and provides framework-specific
insights based on actual code analysis, not folder name guessing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..analyzers.base import FileAnalysis


@dataclass
class FrameworkDetection:
    name: str
    version: str | None = None
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    category: str = "unknown"  # frontend, backend, fullstack, database, build


@dataclass
class APIEndpoint:
    method: str
    path: str
    file: str
    line: int
    handler: str | None = None
    middleware: list[str] = field(default_factory=list)
    request_model: str | None = None
    response_model: str | None = None


@dataclass
class DatabaseModel:
    name: str
    file: str
    line: int
    fields: list[str] = field(default_factory=list)
    orm: str | None = None


class FrameworkAnalyzer:
    """Framework-specific analysis based on actual code patterns."""

    def detect_frameworks(
        self,
        workspace: Path,
        analyses: list[FileAnalysis],
    ) -> list[FrameworkDetection]:
        """Detect frameworks from package files and code patterns."""
        detections = []
        detections.extend(self._detect_from_package_json(workspace))
        detections.extend(self._detect_from_python_deps(workspace))
        detections.extend(self._detect_from_code_patterns(analyses))
        return self._deduplicate(detections)

    def detect_api_endpoints(
        self,
        analyses: list[FileAnalysis],
    ) -> list[APIEndpoint]:
        """Detect API routes from code patterns."""
        endpoints = []
        for fa in analyses:
            if fa.language == "javascript" or fa.language == "typescript":
                endpoints.extend(self._detect_js_routes(fa))
            elif fa.language == "python":
                endpoints.extend(self._detect_python_routes(fa))
        return endpoints

    def detect_database_models(
        self,
        analyses: list[FileAnalysis],
    ) -> list[DatabaseModel]:
        """Detect database model definitions."""
        models = []
        for fa in analyses:
            if fa.language == "python":
                models.extend(self._detect_python_models(fa))
            elif fa.language in ("javascript", "typescript"):
                models.extend(self._detect_js_models(fa))
        return models

    # ==================================================================
    # Package.json Detection
    # ==================================================================

    def _detect_from_package_json(self, workspace: Path) -> list[FrameworkDetection]:
        pkg_json = workspace / "package.json"
        if not pkg_json.exists():
            return []
        try:
            pkg = json.loads(pkg_json.read_text())
        except (json.JSONDecodeError, OSError):
            return []

        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        detections = []

        framework_map = {
            "react": ("React", "frontend", "UI library for building interfaces"),
            "next": ("Next.js", "fullstack", "React framework with SSR/SSG"),
            "vue": ("Vue.js", "frontend", "Progressive JavaScript framework"),
            "nuxt": ("Nuxt.js", "fullstack", "Vue framework with SSR"),
            "angular": ("Angular", "frontend", "Platform for web applications"),
            "@angular/core": ("Angular", "frontend", "Platform for web applications"),
            "svelte": ("Svelte", "frontend", "Compile-time reactive framework"),
            "solid-js": ("SolidJS", "frontend", "Reactive JavaScript framework"),
            "express": ("Express", "backend", "Node.js web framework"),
            "fastify": ("Fastify", "backend", "Fast Node.js web framework"),
            "hono": ("Hono", "backend", "Ultrafast web framework"),
            "@nestjs/core": ("NestJS", "backend", "Progressive Node.js framework"),
            "koa": ("Koa", "backend", "Expressive HTTP middleware framework"),
            "remix": ("Remix", "fullstack", "Full-stack web framework"),
            "gatsby": ("Gatsby", "fullstack", "React-based static site generator"),
            "electron": ("Electron", "frontend", "Desktop app framework"),
            "tauri": ("Tauri", "frontend", "Desktop app framework"),
            "react-native": ("React Native", "frontend", "Mobile app framework"),
            "next": ("Next.js", "fullstack", "React framework with SSR/SSG"),
            "mongoose": ("MongoDB", "database", "MongoDB ODM"),
            "sequelize": ("Sequelize", "database", "SQL ORM for Node.js"),
            "prisma": ("Prisma", "database", "Next-gen Node.js ORM"),
            "typeorm": ("TypeORM", "database", "ORM for TypeScript"),
            "knex": ("Knex.js", "database", "SQL query builder"),
            "drizzle-orm": ("Drizzle", "database", "TypeScript ORM"),
            "@prisma/client": ("Prisma", "database", "Prisma Client"),
            "pg": ("PostgreSQL", "database", "PostgreSQL client"),
            "mysql2": ("MySQL", "database", "MySQL client"),
            "better-sqlite3": ("SQLite", "database", "SQLite client"),
            "ioredis": ("Redis", "database", "Redis client"),
            "redis": ("Redis", "database", "Redis client"),
            "axios": ("Axios", "utility", "HTTP client"),
            "graphql": ("GraphQL", "backend", "GraphQL implementation"),
            "@apollo/server": ("Apollo", "backend", "GraphQL server"),
            "socket.io": ("Socket.IO", "backend", "Real-time communication"),
            "tailwindcss": ("Tailwind CSS", "frontend", "Utility-first CSS"),
            "styled-components": ("Styled Components", "frontend", "CSS-in-JS"),
            "framer-motion": ("Framer Motion", "frontend", "Animation library"),
            "d3": ("D3.js", "frontend", "Data visualization"),
            "chart.js": ("Chart.js", "frontend", "Charting library"),
            "zustand": ("Zustand", "frontend", "State management"),
            "redux": ("Redux", "frontend", "State management"),
            "@reduxjs/toolkit": ("Redux Toolkit", "frontend", "State management"),
            "jotai": ("Jotai", "frontend", "State management"),
            "recoil": ("Recoil", "frontend", "State management"),
            "tanstack/react-query": ("React Query", "frontend", "Data fetching"),
            "swr": ("SWR", "frontend", "Data fetching"),
            "vitest": ("Vitest", "testing", "Test framework"),
            "jest": ("Jest", "testing", "Test framework"),
            "cypress": ("Cypress", "testing", "E2E testing"),
            "playwright": ("Playwright", "testing", "E2E testing"),
            "storybook": ("Storybook", "testing", "Component development"),
        }

        for dep, (name, category, desc) in framework_map.items():
            if dep in deps:
                detections.append(FrameworkDetection(
                    name=name,
                    version=deps[dep],
                    confidence=0.9,
                    evidence=[f"Found '{dep}' in package.json"],
                    category=category,
                ))

        # Build tools
        build_tools = {
            "vite": ("Vite", "build"),
            "webpack": ("Webpack", "build"),
            "esbuild": ("esbuild", "build"),
            "rollup": ("Rollup", "build"),
            "parcel": ("Parcel", "build"),
            "turbo": ("Turborepo", "build"),
        }
        for dep, (name, category) in build_tools.items():
            if dep in deps:
                detections.append(FrameworkDetection(
                    name=name,
                    confidence=0.9,
                    evidence=[f"Found '{dep}' in package.json"],
                    category=category,
                ))

        return detections

    # ==================================================================
    # Python Dependencies Detection
    # ==================================================================

    def _detect_from_python_deps(self, workspace: Path) -> list[FrameworkDetection]:
        detections = []

        # Check requirements.txt
        for req_file in ["requirements.txt", "requirements/base.txt", "requirements/prod.txt"]:
            p = workspace / req_file
            if p.exists():
                try:
                    content = p.read_text()
                    detections.extend(self._parse_python_deps(content, req_file))
                except OSError:
                    pass

        # Check pyproject.toml
        pyproject = workspace / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                detections.extend(self._parse_python_deps(content, "pyproject.toml"))
            except OSError:
                pass

        # Check setup.py
        setup_py = workspace / "setup.py"
        if setup_py.exists():
            try:
                content = setup_py.read_text()
                detections.extend(self._parse_python_deps(content, "setup.py"))
            except OSError:
                pass

        return detections

    def _parse_python_deps(self, content: str, source: str) -> list[FrameworkDetection]:
        detections = []
        python_map = {
            "fastapi": ("FastAPI", "backend", "Modern Python web framework"),
            "flask": ("Flask", "backend", "Lightweight Python web framework"),
            "django": ("Django", "fullstack", "High-level Python web framework"),
            "starlette": ("Starlette", "backend", "ASGI framework"),
            "uvicorn": ("Uvicorn", "backend", "ASGI server"),
            "gunicorn": ("Gunicorn", "backend", "WSGI HTTP server"),
            "tornado": ("Tornado", "backend", "Async networking framework"),
            "sanic": ("Sanic", "backend", "Async Python web framework"),
            "bottle": ("Bottle", "backend", "Micro web framework"),
            "pydantic": ("Pydantic", "utility", "Data validation"),
            "sqlalchemy": ("SQLAlchemy", "database", "Python SQL toolkit"),
            "alembic": ("Alembic", "database", "Database migrations"),
            "tortoise-orm": ("Tortoise ORM", "database", "Async ORM"),
            "peewee": ("Peewee", "database", "Small ORM"),
            "motor": ("Motor", "database", "Async MongoDB driver"),
            "pymongo": ("PyMongo", "database", "MongoDB driver"),
            "psycopg2": ("PostgreSQL", "database", "PostgreSQL adapter"),
            "asyncpg": ("PostgreSQL", "database", "Async PostgreSQL"),
            "pymysql": ("MySQL", "database", "MySQL driver"),
            "celery": ("Celery", "backend", "Task queue"),
            "redis": ("Redis", "database", "Redis client"),
            "httpx": ("HTTPX", "utility", "Async HTTP client"),
            "requests": ("Requests", "utility", "HTTP library"),
            "pytest": ("Pytest", "testing", "Testing framework"),
            "unittest": ("Unittest", "testing", "Testing framework"),
            "black": ("Black", "build", "Code formatter"),
            "ruff": ("Ruff", "build", "Linter"),
            "mypy": ("MyPy", "build", "Type checker"),
            "mangum": ("Mangum", "backend", "AWS Lambda adapter for ASGI"),
            "boto3": ("AWS SDK", "infrastructure", "AWS Python SDK"),
            "google-cloud-storage": ("GCS", "infrastructure", "Google Cloud Storage"),
            "python-jose": ("JWT", "security", "JWT implementation"),
            "passlib": ("Auth", "security", "Password hashing"),
            "python-multipart": ("Multipart", "utility", "Form data parsing"),
        }

        content_lower = content.lower()
        for dep, (name, category, desc) in python_map.items():
            # Check for the dependency name in the content
            if re.search(rf'\b{re.escape(dep)}\b', content_lower):
                detections.append(FrameworkDetection(
                    name=name,
                    confidence=0.85,
                    evidence=[f"Found '{dep}' in {source}"],
                    category=category,
                ))

        return detections

    # ==================================================================
    # Code Pattern Detection
    # ==================================================================

    def _detect_from_code_patterns(self, analyses: list[FileAnalysis]) -> list[FrameworkDetection]:
        detections = []
        react_patterns = 0
        express_patterns = 0
        fastapi_patterns = 0
        django_patterns = 0

        for fa in analyses:
            src = fa.source if hasattr(fa, 'source') else ""
            if not src:
                continue

            # React patterns
            if "React.FC" in src or "React.Component" in src or "jsx" in fa.file_path.suffix:
                react_patterns += 1
            if any(imp.source == "react" for imp in fa.imports):
                react_patterns += 1

            # Express patterns
            if "app.get(" in src or "app.post(" in src or "router.get(" in src or "router.post(" in src:
                express_patterns += 1
            if any(imp.source == "express" for imp in fa.imports):
                express_patterns += 1

            # FastAPI patterns
            if "@app.get" in src or "@app.post" in src or "@router.get" in src or "@router.post" in src:
                fastapi_patterns += 1
            if any(imp.source == "fastapi" for imp in fa.imports):
                fastapi_patterns += 1

            # Django patterns
            if "from django" in src or "@csrf_exempt" in src or "HttpResponse" in src:
                django_patterns += 1

        if react_patterns > 0:
            detections.append(FrameworkDetection(
                name="React",
                confidence=min(0.5 + react_patterns * 0.1, 0.95),
                evidence=[f"Found {react_patterns} React code patterns"],
                category="frontend",
            ))
        if express_patterns > 0:
            detections.append(FrameworkDetection(
                name="Express",
                confidence=min(0.5 + express_patterns * 0.1, 0.95),
                evidence=[f"Found {express_patterns} Express code patterns"],
                category="backend",
            ))
        if fastapi_patterns > 0:
            detections.append(FrameworkDetection(
                name="FastAPI",
                confidence=min(0.5 + fastapi_patterns * 0.1, 0.95),
                evidence=[f"Found {fastapi_patterns} FastAPI code patterns"],
                category="backend",
            ))
        if django_patterns > 0:
            detections.append(FrameworkDetection(
                name="Django",
                confidence=min(0.5 + django_patterns * 0.1, 0.95),
                evidence=[f"Found {django_patterns} Django code patterns"],
                category="fullstack",
            ))

        return detections

    # ==================================================================
    # API Route Detection
    # ==================================================================

    def _detect_js_routes(self, fa: FileAnalysis) -> list[APIEndpoint]:
        endpoints = []
        src = fa.source if hasattr(fa, 'source') else ""
        if not src:
            return endpoints

        # Express-style routes: app.get("/path", ...) or router.post("/path", ...)
        route_pattern = re.compile(
            r'(?:app|router|server)\.(get|post|put|delete|patch|all|options|head)\s*\(\s*["\']([^"\']+)["\']',
            re.MULTILINE
        )
        for match in route_pattern.finditer(src):
            method = match.group(1).upper()
            path = match.group(2)
            line = src[:match.start()].count('\n') + 1
            endpoints.append(APIEndpoint(
                method=method,
                path=path,
                file=str(fa.file_path),
                line=line,
            ))

        # Next.js API routes from file path
        path_str = str(fa.file_path)
        if "/api/" in path_str and fa.language in ("javascript", "typescript"):
            # Extract the API route from the file path
            api_match = re.search(r'/api/(.+?)(?:\.(?:js|ts|tsx|jsx))?$', path_str)
            if api_match:
                route_path = "/" + api_match.group(1).replace("/index", "")
                endpoints.append(APIEndpoint(
                    method="ALL",
                    path=route_path,
                    file=str(fa.file_path),
                    line=1,
                ))

        return endpoints

    def _detect_python_routes(self, fa: FileAnalysis) -> list[APIEndpoint]:
        endpoints = []
        src = fa.source if hasattr(fa, 'source') else ""
        if not src:
            return endpoints

        # FastAPI/Flask/Django routes
        # @app.get("/path") / @router.post("/path")
        route_pattern = re.compile(
            r'@\w+\.(get|post|put|delete|patch|route|api_view)\s*\(\s*["\']([^"\']+)["\']',
            re.MULTILINE
        )
        for match in route_pattern.finditer(src):
            method_str = match.group(1)
            path = match.group(2)
            method = method_str.upper() if method_str != "route" else "ALL"
            line = src[:match.start()].count('\n') + 1
            endpoints.append(APIEndpoint(
                method=method,
                path=path,
                file=str(fa.file_path),
                line=line,
            ))

        # Django urls.py patterns
        url_pattern = re.compile(
            r'path\s*\(\s*["\']([^"\']+)["\']',
            re.MULTILINE
        )
        if "urls.py" in str(fa.file_path):
            for match in url_pattern.finditer(src):
                path = match.group(1)
                line = src[:match.start()].count('\n') + 1
                endpoints.append(APIEndpoint(
                    method="ALL",
                    path="/" + path if not path.startswith("/") else path,
                    file=str(fa.file_path),
                    line=line,
                ))

        return endpoints

    # ==================================================================
    # Database Model Detection
    # ==================================================================

    def _detect_python_models(self, fa: FileAnalysis) -> list[DatabaseModel]:
        models = []
        src = fa.source if hasattr(fa, 'source') else ""
        if not src:
            return models

        # SQLAlchemy models
        for ent in fa.entities:
            if ent.entity_type == "class":
                # Check if it inherits from Base/Model/db.Model
                if ent.parent_class and any(
                    parent in (ent.parent_class or "")
                    for parent in ["Base", "Model", "db.Model", "Document", "AbstractUser"]
                ):
                    fields = []
                    # Look for Column definitions in the class source
                    col_pattern = re.compile(r'(\w+)\s*=\s*Column\(')
                    for match in col_pattern.finditer(ent.source):
                        fields.append(match.group(1))
                    models.append(DatabaseModel(
                        name=ent.name,
                        file=str(fa.file_path),
                        line=ent.start_line,
                        fields=fields,
                        orm="sqlalchemy",
                    ))

        # Pydantic models
        for ent in fa.entities:
            if ent.entity_type == "class" and ent.parent_class:
                if "BaseModel" in ent.parent_class or "BaseSchema" in ent.parent_class:
                    models.append(DatabaseModel(
                        name=ent.name,
                        file=str(fa.file_path),
                        line=ent.start_line,
                        orm="pydantic",
                    ))

        return models

    def _detect_js_models(self, fa: FileAnalysis) -> list[DatabaseModel]:
        models = []
        src = fa.source if hasattr(fa, 'source') else ""
        if not src:
            return models

        # Mongoose models
        mongoose_pattern = re.compile(r'mongoose\.model\s*\(\s*["\'](\w+)["\']')
        for match in mongoose_pattern.finditer(src):
            line = src[:match.start()].count('\n') + 1
            models.append(DatabaseModel(
                name=match.group(1),
                file=str(fa.file_path),
                line=line,
                orm="mongoose",
            ))

        # Prisma models (from schema.prisma)
        prisma_file = fa.file_path.parent / "schema.prisma"
        # This is simplified - real prisma parsing would be more complex

        return models

    # ==================================================================
    # Helpers
    # ==================================================================

    def _deduplicate(self, detections: list[FrameworkDetection]) -> list[FrameworkDetection]:
        seen = set()
        result = []
        for d in detections:
            key = d.name.lower()
            if key not in seen:
                seen.add(key)
                result.append(d)
        return sorted(result, key=lambda x: -x.confidence)
