"""
Base parser interface for language-specific analyzers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from tree_sitter import Node, Parser


@dataclass(frozen=True, slots=True)
class ParseResult:
    file_path: Path
    source: str
    root: Node
    has_errors: bool


@dataclass
class ExtractedEntity:
    name: str
    entity_type: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    parent: str | None = None
    parameters: list[str] = field(default_factory=list)
    source: str = ""
    is_async: bool = False


@dataclass
class ExtractedImport:
    source: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    imported_names: list[str] = field(default_factory=list)
    is_default: bool = False
    is_namespace: bool = False


@dataclass
class ExtractedExport:
    source: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    exported_names: list[str] = field(default_factory=list)
    is_default: bool = False


@dataclass
class ExtractedCall:
    caller: str
    callee: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass
class FileAnalysis:
    file_path: Path
    language: str
    entities: list[ExtractedEntity] = field(default_factory=list)
    imports: list[ExtractedImport] = field(default_factory=list)
    exports: list[ExtractedExport] = field(default_factory=list)
    calls: list[ExtractedCall] = field(default_factory=list)
    has_syntax_errors: bool = False


class BaseParser(ABC):
    """Abstract base for language-specific parsers."""

    def __init__(self) -> None:
        self._parser = None
        self.configure()

    @property
    @abstractmethod
    def language_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def configure(self) -> None:
        raise NotImplementedError

    def _set_language(self, lang: 'Language') -> None:
        """Set the Tree-sitter language on the parser."""
        self._parser = Parser(lang)

    def parse(self, source: str, file_path: Path) -> ParseResult:
        source_bytes = source.encode("utf-8")
        tree = self._parser.parse(source_bytes)
        root = tree.root_node
        return ParseResult(
            file_path=file_path,
            source=source,
            root=root,
            has_errors=root.has_error,
        )

    def analyze(self, source: str, file_path: Path) -> FileAnalysis:
        result = self.parse(source, file_path)
        return self.extract(result)

    @abstractmethod
    def extract(self, result: ParseResult) -> FileAnalysis:
        raise NotImplementedError

    @staticmethod
    def walk(node: Node) -> Iterator[Node]:
        stack: list[Node] = [node]
        while stack:
            current = stack.pop()
            yield current
            stack.extend(reversed(current.children))

    @staticmethod
    def get_node_text(node: Node, source: bytes) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
