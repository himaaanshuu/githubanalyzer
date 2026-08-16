"""
Generic Tree-sitter parser infrastructure.

This module provides the common parsing contract used by all
language-specific analyzers.

Design goals:
    - Parse source code exactly once.
    - Keep Tree-sitter isolated from higher-level application logic.
    - Support multiple programming languages through inheritance.
    - Provide iterative AST traversal to avoid recursion limits.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from tree_sitter import Node, Parser


@dataclass(frozen=True, slots=True)
class ParseResult:
    """
    Immutable result produced by a parser.

    Attributes:
        file_path: Repository-relative source file path.
        source: Original source code.
        root: Root node of the Tree-sitter syntax tree.
        has_errors: Whether Tree-sitter detected syntax errors.
    """

    file_path: Path
    source: str
    root: Node
    has_errors: bool


class CodeParser(ABC):
    """
    Abstract base class for language-specific Tree-sitter parsers.

    Concrete implementations configure the appropriate grammar and
    use the resulting AST to perform language-specific extraction.
    """

    def __init__(self) -> None:
        """Initialize the underlying Tree-sitter parser."""

        self._parser = Parser()

        self.configure()

    @property
    @abstractmethod
    def language_name(self) -> str:
        """Return the human-readable language name."""

        raise NotImplementedError

    @abstractmethod
    def configure(self) -> None:
        """
        Configure the Tree-sitter language grammar.

        Each language-specific parser must implement this method.
        """

        raise NotImplementedError

    def parse(
        self,
        source: str,
        file_path: Path,
    ) -> ParseResult:
        """
        Parse source code exactly once.

        Args:
            source:
                Complete source code.

            file_path:
                Repository-relative path.

        Returns:
            Immutable ParseResult containing the syntax tree.
        """

        source_bytes = source.encode("utf-8")

        tree = self._parser.parse(
            source_bytes
        )

        root = tree.root_node

        return ParseResult(
            file_path=file_path,
            source=source,
            root=root,
            has_errors=root.has_error,
        )

    @staticmethod
    def walk(
        node: Node,
    ) -> Iterator[Node]:
        """
        Iteratively traverse a Tree-sitter syntax tree.

        A stack is used instead of recursive traversal so deeply
        nested source code cannot cause Python recursion errors.

        Args:
            node:
                Root Tree-sitter node.

        Yields:
            Nodes in deterministic depth-first order.
        """

        stack: list[Node] = [node]

        while stack:
            current = stack.pop()

            yield current

            # Reverse children to preserve source order.
            stack.extend(
                reversed(current.children)
            )