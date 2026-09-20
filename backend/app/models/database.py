"""
SQLAlchemy database models.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON, Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


class AnalysisStatus(str, enum.Enum):
    PENDING = "pending"
    CLONING = "cloning"
    SCANNING = "scanning"
    PARSING = "parsing"
    BUILDING_GRAPH = "building_graph"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(1024), nullable=False)
    name = Column(String(256), nullable=False)
    owner = Column(String(256), nullable=False)
    branch = Column(String(256), default="main")
    commit_sha = Column(String(64), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(AnalysisStatus), default=AnalysisStatus.PENDING)
    error_message = Column(Text, nullable=True)
    workspace_path = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    analysis = relationship("Analysis", back_populates="repository", uselist=False)
    files = relationship("RepositoryFile", back_populates="repository")
    symbols = relationship("Symbol", back_populates="repository")
    graph_nodes = relationship("GraphNodeDB", back_populates="repository")
    graph_edges = relationship("GraphEdgeDB", back_populates="repository")


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), unique=True)
    total_files = Column(Integer, default=0)
    total_source_files = Column(Integer, default=0)
    total_functions = Column(Integer, default=0)
    total_classes = Column(Integer, default=0)
    total_imports = Column(Integer, default=0)
    total_exports = Column(Integer, default=0)
    total_calls = Column(Integer, default=0)
    languages = Column(JSON, default=dict)
    frameworks = Column(JSON, default=list)
    architecture = Column(JSON, default=dict)
    tech_stack = Column(JSON, default=dict)
    beginner_analysis = Column(JSON, nullable=True)
    intermediate_analysis = Column(JSON, nullable=True)
    advanced_analysis = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    repository = relationship("Repository", back_populates="analysis")


class RepositoryFile(Base):
    __tablename__ = "repository_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    path = Column(String(1024), nullable=False)
    language = Column(String(64), nullable=True)
    size_bytes = Column(Integer, default=0)
    category = Column(String(32), default="source")
    content = Column(Text, nullable=True)
    has_syntax_errors = Column(Integer, default=0)
    entity_count = Column(Integer, default=0)
    import_count = Column(Integer, default=0)
    export_count = Column(Integer, default=0)
    call_count = Column(Integer, default=0)

    repository = relationship("Repository", back_populates="files")
    symbols = relationship("Symbol", back_populates="file")


class Symbol(Base):
    __tablename__ = "symbols"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    file_id = Column(Integer, ForeignKey("repository_files.id"), nullable=True)
    name = Column(String(512), nullable=False)
    qualified_name = Column(String(1024), nullable=True)
    symbol_type = Column(String(64), nullable=False)
    file_path = Column(String(1024), nullable=True)
    start_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    parameters = Column(JSON, default=list)
    extra_metadata = Column("metadata", JSON, default=dict)

    repository = relationship("Repository", back_populates="symbols")
    file = relationship("RepositoryFile", back_populates="symbols")


class GraphNodeDB(Base):
    __tablename__ = "graph_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    node_id = Column(String(512), nullable=False)
    node_type = Column(String(64), nullable=False)
    name = Column(String(512), nullable=False)
    file_path = Column(String(1024), nullable=True)
    qualified_name = Column(String(1024), nullable=True)
    extra_metadata = Column("metadata", JSON, default=dict)

    repository = relationship("Repository", back_populates="graph_nodes")


class GraphEdgeDB(Base):
    __tablename__ = "graph_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    source_id = Column(String(512), nullable=False)
    target_id = Column(String(512), nullable=False)
    edge_type = Column(String(64), nullable=False)
    extra_metadata = Column("metadata", JSON, default=dict)

    repository = relationship("Repository", back_populates="graph_edges")


class AIInsight(Base):
    __tablename__ = "ai_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    evidence = Column(JSON, default=list)
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    report_type = Column(String(32), default="full")
    content = Column(Text, nullable=False)
    format = Column(String(16), default="markdown")
    created_at = Column(DateTime, default=datetime.utcnow)
