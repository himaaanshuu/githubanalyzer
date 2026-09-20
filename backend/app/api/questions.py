"""
Questions API endpoint.
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.database import GraphEdgeDB, GraphNodeDB, Repository, RepositoryFile, Symbol
from app.models.schemas import QuestionRequest, QuestionResponse

router = APIRouter()


@router.post("/{repo_id}/questions", response_model=QuestionResponse)
async def ask_question(
    repo_id: int,
    request: QuestionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Ask a question about the repository."""
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    if repo.status != "completed":
        raise HTTPException(status_code=409, detail="Analysis not completed yet")

    # Find relevant context
    question_lower = request.question.lower()

    # Search symbols
    sym_result = await db.execute(
        select(Symbol).where(Symbol.repository_id == repo_id)
    )
    all_symbols = sym_result.scalars().all()

    relevant_symbols = []
    related_files = set()

    for sym in all_symbols:
        name_lower = sym.name.lower()
        if any(word in name_lower for word in question_lower.split() if len(word) > 2):
            relevant_symbols.append(sym)
            if sym.file_path:
                related_files.add(sym.file_path)

    # Search files
    file_result = await db.execute(
        select(RepositoryFile).where(RepositoryFile.repository_id == repo_id)
    )
    all_files = file_result.scalars().all()

    for f in all_files:
        path_lower = f.path.lower()
        if any(word in path_lower for word in question_lower.split() if len(word) > 2):
            related_files.add(f.path)

    # Build evidence
    evidence = []
    for sym in relevant_symbols[:10]:
        evidence.append({
            "type": "symbol",
            "name": sym.name,
            "file": sym.file_path,
            "line": sym.start_line,
            "symbol_type": sym.symbol_type,
        })

    # Get graph relationships
    graph_result = await db.execute(
        select(GraphEdgeDB).where(GraphEdgeDB.repository_id == repo_id)
    )
    all_edges = graph_result.scalars().all()

    node_result = await db.execute(
        select(GraphNodeDB).where(GraphNodeDB.repository_id == repo_id)
    )
    all_nodes = {n.node_id: n for n in (await db.execute(
        select(GraphNodeDB).where(GraphNodeDB.repository_id == repo_id)
    )).scalars().all()}

    # Build answer from evidence
    answer_parts = []
    if relevant_symbols:
        answer_parts.append(f"Found {len(relevant_symbols)} relevant symbols:")
        for sym in relevant_symbols[:5]:
            answer_parts.append(f"- **{sym.name}** ({sym.symbol_type}) in `{sym.file_path}` at line {sym.start_line}")

    if related_files:
        answer_parts.append(f"\nRelated files: {', '.join(sorted(related_files)[:10])}")

    # Trace relationships
    for sym in relevant_symbols[:3]:
        sym_id = f"{sym.symbol_type}:{sym.file_path}:{sym.name}:{sym.start_line}"
        # Find outgoing edges
        outgoing = [e for e in all_edges if e.source_id == sym_id]
        if outgoing:
            answer_parts.append(f"\n{sym.name} connects to:")
            for edge in outgoing[:5]:
                target = all_nodes.get(edge.target_id)
                if target:
                    answer_parts.append(f"  - {target.name} ({edge.edge_type})")

    answer = "\n".join(answer_parts) if answer_parts else f"Based on static analysis, here is what I found related to your question about '{request.question}':\n\nThe repository contains {len(all_symbols)} symbols across {len(all_files)} files. Try asking about specific functions, files, or features."

    confidence = min(len(relevant_symbols) / 5.0, 1.0) if relevant_symbols else 0.3

    return QuestionResponse(
        question=request.question,
        answer=answer,
        evidence=evidence,
        confidence=confidence,
        related_files=sorted(related_files)[:20],
        related_symbols=[s.name for s in relevant_symbols[:10]],
    )
