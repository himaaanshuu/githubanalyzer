"""
Repository-wide source-code intelligence.

This module coordinates language-specific analyzers and produces a
normalized repository-level code inventory.

Design goals:
    - Analyze supported source files deterministically.
    - Parse each file exactly once.
    - Isolate failures to individual files.
    - Provide immutable results for downstream systems.
    - Remain extensible for additional programming languages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .javascript import JavaScriptParser
from .models import (
    CallReference,
    CodeEntity,
    ExportReference,
    ImportReference,
)


@dataclass(frozen=True, slots=True)
class FileAnalysisResult:
    """Structural analysis result for a single source file."""

    file_path: Path

    entities: tuple[CodeEntity, ...]

    imports: tuple[ImportReference, ...]

    exports: tuple[ExportReference, ...]

    calls: tuple[CallReference, ...]

    has_syntax_errors: bool


@dataclass(frozen=True, slots=True)
class RepositoryCodeInventory:
    """
    Complete structural inventory of a repository.

    This object becomes the foundation for:

        AST analysis
            ↓
        Code graph
            ↓
        Semantic chunking
            ↓
        Retrieval
            ↓
        RAG
            ↓
        AI repository understanding
    """

    files: tuple[FileAnalysisResult, ...]

    @property
    def total_files(self) -> int:
        """Return the number of analyzed source files."""

        return len(self.files)

    @property
    def total_entities(self) -> int:
        """Return the total number of extracted entities."""

        return sum(
            len(result.entities)
            for result in self.files
        )

    @property
    def total_imports(self) -> int:
        """Return the total number of import references."""

        return sum(
            len(result.imports)
            for result in self.files
        )

    @property
    def total_exports(self) -> int:
        """Return the total number of export references."""

        return sum(
            len(result.exports)
            for result in self.files
        )

    @property
    def total_calls(self) -> int:
        """Return the total number of call references."""

        return sum(
            len(result.calls)
            for result in self.files
        )

    @property
    def files_with_syntax_errors(self) -> int:
        """Return the number of files containing syntax errors."""

        return sum(
            result.has_syntax_errors
            for result in self.files
        )


class RepositoryCodeAnalyzer:
    """
    Analyze supported source files throughout a repository.

    Language parsers are registered centrally so additional languages
    can be added without changing the repository traversal logic.
    """

    _IGNORED_DIRECTORIES: frozenset[str] = frozenset(
        {
            ".git",
            ".hg",
            ".svn",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            "dist",
            "build",
            "coverage",
            ".next",
            ".cache",
        }
    )

    def __init__(self) -> None:
        """Initialize the repository analyzer."""

        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )

        self._parsers = {
            ".js": JavaScriptParser(),
            ".jsx": JavaScriptParser(),
        }

    def analyze(
        self,
        repository_root: Path,
    ) -> RepositoryCodeInventory:
        """
        Analyze every supported source file.

        Args:
            repository_root:
                Root directory of the repository.

        Returns:
            Immutable repository-wide code inventory.
        """

        repository_root = repository_root.resolve()

        if not repository_root.exists():
            raise FileNotFoundError(
                f"Repository does not exist: "
                f"{repository_root}"
            )

        if not repository_root.is_dir():
            raise NotADirectoryError(
                f"Repository path is not a directory: "
                f"{repository_root}"
            )

        results: list[FileAnalysisResult] = []

        for file_path in self._iter_source_files(
            repository_root
        ):
            result = self._analyze_file(
                file_path,
                repository_root,
            )

            if result is not None:
                results.append(result)

        # Deterministic ordering is important for reproducibility,
        # testing, caching, and future embedding generation.
        results.sort(
            key=lambda result: result.file_path.as_posix()
        )

        inventory = RepositoryCodeInventory(
            files=tuple(results)
        )

        self.logger.info(
            "Repository code analysis completed: "
            "%d files | %d entities | %d imports | "
            "%d exports | %d calls | %d syntax-error files",
            inventory.total_files,
            inventory.total_entities,
            inventory.total_imports,
            inventory.total_exports,
            inventory.total_calls,
            inventory.files_with_syntax_errors,
        )

        return inventory

    def _analyze_file(
        self,
        file_path: Path,
        repository_root: Path,
    ) -> FileAnalysisResult | None:
        """Analyze a single source file safely."""

        relative_path = file_path.relative_to(
            repository_root
        )

        parser = self._select_parser(
            file_path
        )

        if parser is None:
            return None

        try:
            source = file_path.read_text(
                encoding="utf-8",
                errors="replace",
            )

            (
                entities,
                imports,
                exports,
                calls,
                has_syntax_errors,
            ) = parser.analyze(
                source,
                relative_path,
            )

            return FileAnalysisResult(
                file_path=relative_path,
                entities=entities,
                imports=imports,
                exports=exports,
                calls=calls,
                has_syntax_errors=has_syntax_errors,
            )

        except OSError as exc:
            self.logger.warning(
                "Unable to read '%s': %s",
                relative_path,
                exc,
            )

        except UnicodeError as exc:
            self.logger.warning(
                "Unable to decode '%s': %s",
                relative_path,
                exc,
            )

        except Exception as exc:
            # A parser failure must not terminate analysis of the
            # entire repository.
            self.logger.exception(
                "Analysis failed for '%s': %s",
                relative_path,
                exc,
            )

        return None

    def _select_parser(
        self,
        file_path: Path,
    ) -> JavaScriptParser | None:
        """Return the parser associated with a file extension."""

        return self._parsers.get(
            file_path.suffix.lower()
        )

    def _iter_source_files(
        self,
        repository_root: Path,
    ):
        """
        Yield supported source files using iterative traversal.

        Iterative traversal avoids Python recursion depth limitations
        for repositories with unusually deep directory structures.
        """

        stack: list[Path] = [
            repository_root
        ]

        while stack:
            directory = stack.pop()

            try:
                entries = sorted(
                    directory.iterdir(),
                    key=lambda path: path.name,
                    reverse=True,
                )

            except OSError as exc:
                self.logger.warning(
                    "Unable to access '%s': %s",
                    directory,
                    exc,
                )
                continue

            for entry in entries:

                if entry.is_dir():

                    if (
                        entry.name
                        not in self._IGNORED_DIRECTORIES
                    ):
                        stack.append(entry)

                    continue

                if not entry.is_file():
                    continue

                if (
                    entry.suffix.lower()
                    in self._parsers
                ):
                    yield entry