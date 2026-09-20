"""
Graph API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.database import GraphEdgeDB, GraphNodeDB, Repository
from app.models.schemas import GraphEdgeResponse, GraphNodeResponse, GraphResponse

router = APIRouter()


@router.get("/{repo_id}/graph", response_model=GraphResponse)
async def get_repository_graph(
    repo_id: int,
    node_type: str = None,
    edge_type: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Get the code graph for a repository."""
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Get nodes
    query = select(GraphNodeDB).where(GraphNodeDB.repository_id == repo_id)
    if node_type:
        query = query.where(GraphNodeDB.node_type == node_type)
    result = await db.execute(query)
    nodes = [
        GraphNodeResponse(
            node_id=n.node_id,
            node_type=n.node_type,
            name=n.name,
            file_path=n.file_path,
            qualified_name=n.qualified_name,
            metadata=n.extra_metadata or {},
        )
        for n in result.scalars().all()
    ]

    # Get edges
    query = select(GraphEdgeDB).where(GraphEdgeDB.repository_id == repo_id)
    if edge_type:
        query = query.where(GraphEdgeDB.edge_type == edge_type)
    result = await db.execute(query)
    edges = [
        GraphEdgeResponse(
            source_id=e.source_id,
            target_id=e.target_id,
            edge_type=e.edge_type,
            metadata=e.extra_metadata or {},
        )
        for e in result.scalars().all()
    ]

    # Stats
    stats = {}
    for n in nodes:
        stats[n.node_type] = stats.get(n.node_type, 0) + 1
    for e in edges:
        stats[f"edge:{e.edge_type}"] = stats.get(f"edge:{e.edge_type}", 0) + 1

    return GraphResponse(nodes=nodes, edges=edges, stats=stats)
