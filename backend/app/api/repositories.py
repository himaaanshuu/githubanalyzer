"""
Repository API endpoints.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import InvalidURLError, RepositoryNotFoundError
from app.models.database import Repository, AnalysisStatus, RepositoryFile, Symbol
from app.models.schemas import (
    AnalyzeRequest,
    FileDetailResponse,
    FileResponse,
    RepositoryResponse,
    RepositoryStats,
    SymbolResponse,
)
from app.services.analysis_service import RepositoryAnalyzer

router = APIRouter()
analyzer = RepositoryAnalyzer()
logger = logging.getLogger(__name__)


async def _run_analysis(repo_id: int):
    """Background task to analyze a repository."""
    from app.core.database import async_session_factory
    async with async_session_factory() as db:
        try:
            await analyzer.analyze_repository(repo_id, db)
        except Exception as e:
            logger.exception("Background analysis failed for repo %d", repo_id)


@router.post("/analyze", response_model=RepositoryResponse)
async def analyze_repository(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Submit a GitHub repository URL for analysis."""
    try:
        owner, name = analyzer.parse_url(request.url)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid GitHub URL format")

    # Check if already analyzed
    result = await db.execute(
        select(Repository).where(Repository.url == request.url.rstrip("/").rstrip(".git"))
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    # Clone repository
    try:
        repo = await analyzer.clone_repository(request.url, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clone repository: {str(e)}")

    # Start background analysis
    background_tasks.add_task(_run_analysis, repo.id)

    return repo


@router.get("/{repo_id}", response_model=RepositoryResponse)
async def get_repository(repo_id: int, db: AsyncSession = Depends(get_db)):
    """Get repository details."""
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


@router.get("/{repo_id}/stats", response_model=RepositoryStats)
async def get_repository_stats(repo_id: int, db: AsyncSession = Depends(get_db)):
    """Get repository analysis statistics."""
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    from app.models.database import Analysis
    result = await db.execute(select(Analysis).where(Analysis.repository_id == repo_id))
    analysis = result.scalar_one_or_none()

    if not analysis:
        return RepositoryStats()

    return RepositoryStats(
        total_files=analysis.total_files,
        total_source_files=analysis.total_source_files,
        total_functions=analysis.total_functions,
        total_classes=analysis.total_classes,
        total_imports=analysis.total_imports,
        total_exports=analysis.total_exports,
        total_calls=analysis.total_calls,
        languages=analysis.languages or {},
        frameworks=analysis.frameworks or [],
    )


@router.get("/{repo_id}/files", response_model=list[FileResponse])
async def get_repository_files(repo_id: int, db: AsyncSession = Depends(get_db)):
    """Get all files in a repository."""
    result = await db.execute(
        select(RepositoryFile)
        .where(RepositoryFile.repository_id == repo_id)
        .order_by(RepositoryFile.path)
    )
    files = result.scalars().all()
    return files


@router.get("/{repo_id}/files/{file_id}", response_model=FileDetailResponse)
async def get_file_detail(repo_id: int, file_id: int, db: AsyncSession = Depends(get_db)):
    """Get detailed file information including content and symbols."""
    result = await db.execute(
        select(RepositoryFile)
        .where(RepositoryFile.id == file_id, RepositoryFile.repository_id == repo_id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    # Get symbols
    sym_result = await db.execute(
        select(Symbol)
        .where(Symbol.file_id == file_id)
        .order_by(Symbol.start_line)
    )
    symbols = sym_result.scalars().all()

    return FileDetailResponse(
        id=file.id,
        path=file.path,
        language=file.language,
        size_bytes=file.size_bytes,
        category=file.category,
        has_syntax_errors=bool(file.has_syntax_errors),
        entity_count=file.entity_count,
        import_count=file.import_count,
        export_count=file.export_count,
        call_count=file.call_count,
        content=file.content,
        symbols=symbols,
    )


@router.get("/{repo_id}/symbols", response_model=list[SymbolResponse])
async def get_repository_symbols(
    repo_id: int,
    symbol_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get all symbols in a repository, optionally filtered by type."""
    query = select(Symbol).where(Symbol.repository_id == repo_id)
    if symbol_type:
        query = query.where(Symbol.symbol_type == symbol_type)
    query = query.order_by(Symbol.name)
    result = await db.execute(query)
    return result.scalars().all()


@router.delete("/{repo_id}")
async def delete_repository(repo_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a repository and its analysis."""
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    import shutil
    from pathlib import Path

    if repo.workspace_path:
        workspace = Path(repo.workspace_path)
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)

    await db.delete(repo)
    await db.commit()
    return {"status": "deleted"}
