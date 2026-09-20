"""
FastAPI application entry point.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine
from app.models.database import Base
from app.api import repositories, analysis, graph, questions, reports


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="GitHub Intelligence",
    description="AI-Powered Repository Understanding Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repositories.router, prefix="/api/repositories", tags=["repositories"])
app.include_router(analysis.router, prefix="/api/repositories", tags=["analysis"])
app.include_router(graph.router, prefix="/api/repositories", tags=["graph"])
app.include_router(questions.router, prefix="/api/repositories", tags=["questions"])
app.include_router(reports.router, prefix="/api/repositories", tags=["reports"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "GitHub Intelligence"}
