"""
Parser-independent models for repository code intelligence.

These immutable models form the contract between the AST parsing layer
and higher-level systems such as the code graph, static analysis,
embeddings, and RAG.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class CodeEntityType(str, Enum):
    """Supported source-code entity types."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    COMPONENT = "component"
    IMPORT = "import"
    EXPORT = "export"
    VARIABLE = "variable"


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """
    One-based source-code location.

    Using one-based coordinates makes locations easier to display
    directly in the frontend and generated reports.
    """

    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass(frozen=True, slots=True)
class CodeEntity:
    """
    Normalized representation of a source-code entity.

    The model intentionally does not expose Tree-sitter objects.
    This keeps the rest of the application parser-independent.
    """

    entity_type: CodeEntityType
    name: str
    file_path: Path
    location: SourceLocation

    parent: str | None = None

    parameters: tuple[str, ...] = ()

    source: str | None = None

    is_async: bool = False

    @property
    def qualified_name(self) -> str:
        """
        Return a stable name including the parent scope.

        Examples:
            loginUser
            UserController.loginUser
        """

        if self.parent:
            return f"{self.parent}.{self.name}"

        return self.name


@dataclass(frozen=True, slots=True)
class ImportReference:
    """Represents an import statement."""

    source: str
    file_path: Path
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class ExportReference:
    """Represents an export declaration."""

    source: str
    file_path: Path
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class CallReference:
    """Represents a function or method call."""

    caller: str
    callee: str
    file_path: Path
    location: SourceLocation