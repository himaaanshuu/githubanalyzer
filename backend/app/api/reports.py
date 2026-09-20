"""
Report generation endpoints.
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.database import Analysis, GraphEdgeDB, GraphNodeDB, Repository, RepositoryFile, Symbol

router = APIRouter()


@router.post("/{repo_id}/report")
async def generate_report(repo_id: int, db: AsyncSession = Depends(get_db)):
    """Generate a comprehensive project report."""
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    if repo.status != "completed":
        raise HTTPException(status_code=409, detail="Analysis not completed yet")

    # Get analysis
    result = await db.execute(select(Analysis).where(Analysis.repository_id == repo_id))
    analysis = result.scalar_one_or_none()

    # Get files
    result = await db.execute(
        select(RepositoryFile).where(RepositoryFile.repository_id == repo_id).order_by(RepositoryFile.path)
    )
    files = result.scalars().all()

    # Get symbols
    result = await db.execute(
        select(Symbol).where(Symbol.repository_id == repo_id).order_by(Symbol.name)
    )
    symbols = result.scalars().all()

    # Get graph
    result = await db.execute(
        select(GraphNodeDB).where(GraphNodeDB.repository_id == repo_id)
    )
    nodes = result.scalars().all()

    result = await db.execute(
        select(GraphEdgeDB).where(GraphEdgeDB.repository_id == repo_id)
    )
    edges = result.scalars().all()

    # Build report
    report_lines = []
    report_lines.append("# GitHub Intelligence Report")
    report_lines.append(f"\n**Repository:** {repo.name}")
    report_lines.append(f"**Owner:** {repo.owner}")
    report_lines.append(f"**Branch:** {repo.branch}")
    report_lines.append(f"**Commit:** {repo.commit_sha or 'N/A'}")
    report_lines.append(f"**Generated:** {datetime.utcnow().isoformat()}")

    if analysis:
        report_lines.append("\n## 1. Executive Summary")
        report_lines.append(f"\n{analysis.total_files} source files analyzed.")
        report_lines.append(f"- Functions: {analysis.total_functions}")
        report_lines.append(f"- Classes: {analysis.total_classes}")
        report_lines.append(f"- Imports: {analysis.total_imports}")
        report_lines.append(f"- Exports: {analysis.total_exports}")
        report_lines.append(f"- Calls: {analysis.total_calls}")

        report_lines.append("\n## 2. Technology Stack")
        report_lines.append(f"\n**Languages:** {', '.join(f'{k} ({v} files)' for k, v in (analysis.languages or {}).items())}")
        if analysis.frameworks:
            report_lines.append(f"\n**Frameworks:** {', '.join(analysis.frameworks)}")

        report_lines.append("\n## 3. Architecture")
        arch = analysis.architecture or {}
        for pattern in arch.get("patterns", []):
            report_lines.append(f"\n### {pattern['name']}")
            report_lines.append(f"- Confidence: {pattern.get('confidence', 0):.0%}")
            report_lines.append(f"- Evidence: {', '.join(pattern.get('evidence', []))}")

    report_lines.append("\n## 4. Repository Structure")
    dir_stats = {}
    for f in files:
        parts = f.path.split("/")
        top = parts[0] if len(parts) > 1 else "."
        if top not in dir_stats:
            dir_stats[top] = {"files": 0, "languages": set()}
        dir_stats[top]["files"] += 1
        if f.language:
            dir_stats[top]["languages"].add(f.language)

    for d, stats in sorted(dir_stats.items()):
        langs = ", ".join(sorted(stats["languages"])) if stats["languages"] else "N/A"
        report_lines.append(f"\n### `{d}/`")
        report_lines.append(f"- Files: {stats['files']}")
        report_lines.append(f"- Languages: {langs}")

    report_lines.append("\n## 5. Important Functions and Classes")
    funcs = [s for s in symbols if s.symbol_type in ("function", "method")]
    classes = [s for s in symbols if s.symbol_type == "class"]

    if funcs:
        report_lines.append("\n### Functions")
        for f in funcs[:50]:
            params = ", ".join(f.parameters) if f.parameters else ""
            report_lines.append(f"- `{f.name}({params})` in `{f.file_path}:{f.start_line}`")

    if classes:
        report_lines.append("\n### Classes")
        for c in classes[:30]:
            report_lines.append(f"- `{c.name}` in `{c.file_path}:{c.start_line}`")

    report_lines.append("\n## 6. Dependencies")
    import_symbols = [s for s in symbols if s.symbol_type == "import"]
    # Group by file
    file_imports = {}
    for s in symbols:
        # This is simplified - in a real app we'd track imports differently
        pass
    report_lines.append(f"\nTotal import relationships: {analysis.total_imports if analysis else 'N/A'}")

    report_lines.append("\n## 7. Code Graph")
    report_lines.append(f"\n- Nodes: {len(nodes)}")
    report_lines.append(f"- Edges: {len(edges)}")

    edge_types = {}
    for e in edges:
        edge_types[e.edge_type] = edge_types.get(e.edge_type, 0) + 1
    for et, count in sorted(edge_types.items()):
        report_lines.append(f"  - {et}: {count}")

    report_lines.append("\n## 8. Three-Level Analysis")

    if analysis and analysis.beginner_analysis:
        report_lines.append("\n### Beginner Level")
        ba = analysis.beginner_analysis
        for key in ["project_overview", "technology_explanation", "repository_structure", "basic_flow", "learning_path"]:
            if key in ba:
                report_lines.append(f"\n**{key.replace('_', ' ').title()}:**")
                report_lines.append(ba[key])

    if analysis and analysis.intermediate_analysis:
        report_lines.append("\n### Intermediate Level")
        ia = analysis.intermediate_analysis
        for key in ["architecture", "modules", "data_flow", "dependencies"]:
            if key in ia:
                report_lines.append(f"\n**{key.replace('_', ' ').title()}:**")
                report_lines.append(ia[key])

    if analysis and analysis.advanced_analysis:
        report_lines.append("\n### Advanced Level")
        adva = analysis.advanced_analysis
        for key in ["complexity", "security", "call_graph_summary", "circular_dependencies"]:
            if key in adva:
                report_lines.append(f"\n**{key.replace('_', ' ').title()}:**")
                report_lines.append(str(adva[key]))

    report_lines.append("\n---")
    report_lines.append("\n*Generated by GitHub Intelligence*")

    report_content = "\n".join(report_lines)

    return PlainTextResponse(content=report_content, media_type="text/markdown")
