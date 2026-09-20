"""
Analysis level endpoints (Beginner, Intermediate, Advanced).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.database import Analysis, Repository
from app.models.schemas import AnalysisLevelResponse

router = APIRouter()


@router.get("/{repo_id}/analysis/{level}", response_model=AnalysisLevelResponse)
async def get_analysis_level(
    repo_id: int,
    level: str,
    db: AsyncSession = Depends(get_db),
):
    """Get analysis at a specific level (beginner, intermediate, advanced)."""
    if level not in ("beginner", "intermediate", "advanced"):
        raise HTTPException(status_code=400, detail="Level must be beginner, intermediate, or advanced")

    # Check repo exists and is completed
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    if repo.status != "completed":
        raise HTTPException(status_code=409, detail=f"Analysis is {repo.status.value}")

    # Get analysis
    result = await db.execute(select(Analysis).where(Analysis.repository_id == repo_id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    level_data = getattr(analysis, f"{level}_analysis", None) or {}

    return AnalysisLevelResponse(
        level=level,
        project_overview=level_data.get("project_overview", ""),
        technology_explanation=level_data.get("technology_explanation", ""),
        repository_structure=level_data.get("repository_structure", ""),
        basic_flow=level_data.get("basic_flow", ""),
        learning_path=level_data.get("learning_path", ""),
        architecture=level_data.get("architecture", ""),
        modules=level_data.get("modules", ""),
        data_flow=level_data.get("data_flow", ""),
        dependencies=level_data.get("dependencies", ""),
        important_functions=level_data.get("important_functions", ""),
        function_analysis=level_data.get("function_analysis", ""),
        call_graph=level_data.get("call_graph_summary", ""),
        dependency_graph=level_data.get("dependency_graph", ""),
        complexity=level_data.get("complexity", ""),
        security=level_data.get("security", ""),
        api_surface=level_data.get("api_surface", ""),
        entry_points=level_data.get("entry_points", []),
        call_graph_summary=level_data.get("call_graph_summary", ""),
        coupling_analysis=level_data.get("coupling_analysis", ""),
        dead_code_candidates=level_data.get("dead_code_candidates", ""),
        security_observations=level_data.get("security_observations", ""),
        circular_dependencies=level_data.get("circular_dependencies", ""),
    )
