"""
Base parser interface and data models for all language analyzers.

These models represent the contract between Tree-sitter parsing and
all downstream systems (graph builder, AI analysis, reporting).
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from tree_sitter import Node, Parser


# ======================================================================
# Parse Result
# ======================================================================

@dataclass(frozen=True, slots=True)
class ParseResult:
    """Raw Tree-sitter parse output."""
    file_path: Path
    source: str
    root: Node
    has_errors: bool


# ======================================================================
# Extracted Entities
# ======================================================================

@dataclass
class ExtractedEntity:
    """A function, method, or class extracted from source."""
    name: str
    entity_type: str  # function, method, class, interface, type, enum, constant, variable
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    parent: str | None = None
    parameters: list[str] = field(default_factory=list)
    return_type: str | None = None
    decorators: list[str] = field(default_factory=list)
    source: str = ""
    is_async: bool = False
    is_generator: bool = False
    parent_class: str | None = None
    implements: list[str] = field(default_factory=list)
    decorators_raw: list[str] = field(default_factory=list)
    docstring: str | None = None
    visibility: str | None = None  # public, private, protected


@dataclass
class ExtractedImport:
    """An import statement."""
    source: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    imported_names: list[str] = field(default_factory=list)
    is_default: bool = False
    is_namespace: bool = False
    is_type_only: bool = False
    aliases: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ExtractedExport:
    """An export statement."""
    source: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    exported_names: list[str] = field(default_factory=list)
    is_default: bool = False
    reexport_source: str | None = None


@dataclass
class ExtractedCall:
    """A function/method call."""
    caller: str
    callee: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    arguments: list[str] = field(default_factory=list)
    is_awaited: bool = False
    is_chained: bool = False


@dataclass
class ExtractedVariable:
    """A standalone variable/constant assignment."""
    name: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    value_type: str | None = None  # string, number, array, object, function, null, etc.
    is_const: bool = False
    is_exported: bool = False
    source: str = ""


@dataclass
class ExtractedDecorator:
    """A decorator annotation."""
    name: str
    start_line: int
    arguments: list[str] = field(default_factory=list)


# ======================================================================
# File Analysis
# ======================================================================

@dataclass
class FileAnalysis:
    """Complete analysis of a single source file."""
    file_path: Path
    language: str
    entities: list[ExtractedEntity] = field(default_factory=list)
    imports: list[ExtractedImport] = field(default_factory=list)
    exports: list[ExtractedExport] = field(default_factory=list)
    calls: list[ExtractedCall] = field(default_factory=list)
    variables: list[ExtractedVariable] = field(default_factory=list)
    decorators: list[ExtractedDecorator] = field(default_factory=list)
    has_syntax_errors: bool = False
    parse_error: str | None = None
    source: str = ""
    file_hash: str = ""

    def compute_hash(self, content: str) -> str:
        self.file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return self.file_hash


# ======================================================================
# Base Parser
# ======================================================================

class BaseParser(ABC):
    """Abstract base for language-specific Tree-sitter parsers."""

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

    def _set_language(self, lang) -> None:
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
        analysis = self.extract(result)
        analysis.source = source
        analysis.compute_hash(source)
        return analysis

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

    @staticmethod
    def get_child_by_type(node: Node, type_name: str) -> Node | None:
        for child in node.children:
            if child.type == type_name:
                return child
        return None

    @staticmethod
    def get_children_by_type(node: Node, type_name: str) -> list[Node]:
        return [c for c in node.children if c.type == type_name]

    @staticmethod
    def extract_decorators(node: Node, source: bytes) -> tuple[list[str], list[str]]:
        """Extract decorators from a node. Returns (names, raw_texts)."""
        names = []
        raws = []
        for child in node.children:
            if child.type == "decorator":
                text = BaseParser.get_node_text(child, source).strip().lstrip("@")
                # Extract decorator name (before any parentheses)
                paren_idx = text.find("(")
                name = text[:paren_idx].strip() if paren_idx > 0 else text.strip()
                names.append(name)
                raws.append(BaseParser.get_node_text(child, source).strip())
        return names, raws

    @staticmethod
    def extract_docstring(node: Node, source: bytes) -> str | None:
        """Extract the first string literal after a function/class definition."""
        for child in node.children:
            if child.type == "block":
                for stmt in child.children:
                    if stmt.type == "expression_statement":
                        for expr in stmt.children:
                            if expr.type in ("string", "template_string", "string_literal"):
                                text = BaseParser.get_node_text(expr, source)
                                return text.strip('"\',\n ')
        return None
