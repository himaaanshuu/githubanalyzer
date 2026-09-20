"""
Pydantic schemas for API request/response models.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, HttpUrl


class AnalyzeRequest(BaseModel):
    url: str


class RepositoryResponse(BaseModel):
    id: int
    url: str
    name: str
    owner: str
    branch: str
    commit_sha: Optional[str] = None
    description: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AnalysisProgress(BaseModel):
    repository_id: int
    status: str
    step: str
    message: str
    progress_pct: int = 0


class RepositoryStats(BaseModel):
    total_files: int = 0
    total_source_files: int = 0
    total_functions: int = 0
    total_classes: int = 0
    total_imports: int = 0
    total_exports: int = 0
    total_calls: int = 0
    languages: dict[str, int] = {}
    frameworks: list[str] = []


class FileResponse(BaseModel):
    id: int
    path: str
    language: Optional[str] = None
    size_bytes: int
    category: str
    has_syntax_errors: bool
    entity_count: int
    import_count: int
    export_count: int
    call_count: int

    class Config:
        from_attributes = True


class FileDetailResponse(FileResponse):
    content: Optional[str] = None
    symbols: list["SymbolResponse"] = []


class SymbolResponse(BaseModel):
    id: int
    name: str
    qualified_name: Optional[str] = None
    symbol_type: str
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    parameters: list[str] = []
    metadata: dict[str, Any] = {}

    class Config:
        from_attributes = True


class GraphNodeResponse(BaseModel):
    node_id: str
    node_type: str
    name: str
    file_path: Optional[str] = None
    qualified_name: Optional[str] = None
    metadata: dict[str, Any] = {}


class GraphEdgeResponse(BaseModel):
    source_id: str
    target_id: str
    edge_type: str
    metadata: dict[str, Any] = {}


class GraphResponse(BaseModel):
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
    stats: dict[str, int] = {}


class AnalysisLevelResponse(BaseModel):
    level: str
    project_overview: str = ""
    technology_explanation: str = ""
    repository_structure: str = ""
    basic_flow: str = ""
    learning_path: str = ""
    architecture: str = ""
    modules: str = ""
    data_flow: str = ""
    dependencies: str = ""
    important_functions: str = ""
    function_analysis: str = ""
    call_graph: str = ""
    dependency_graph: str = ""
    complexity: str = ""
    security: str = ""
    api_surface: str = ""
    entry_points: list[str] = []
    call_graph_summary: str = ""
    coupling_analysis: str = ""
    dead_code_candidates: str = ""
    security_observations: str = ""
    circular_dependencies: str = ""


class QuestionRequest(BaseModel):
    question: str


class QuestionResponse(BaseModel):
    question: str
    answer: str
    evidence: list[dict[str, Any]] = []
    confidence: float = 0.0
    related_files: list[str] = []
    related_symbols: list[str] = []


class FlowStep(BaseModel):
    node_id: str
    name: str
    node_type: str
    file_path: Optional[str] = None
    metadata: dict[str, Any] = {}


class ExecutionFlowResponse(BaseModel):
    entry_point: str
    steps: list[FlowStep]
    description: str = ""


class ReportResponse(BaseModel):
    id: int
    repository_id: int
    content: str
    format: str
    created_at: datetime

    class Config:
        from_attributes = True
