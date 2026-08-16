"""
Repository scanning and filesystem analysis.

The scanner builds a lightweight structural representation of a
repository without loading the complete source code into memory.

Responsibilities:
    - Traverse repository directories efficiently.
    - Ignore generated/dependency directories.
    - Identify file categories.
    - Detect programming languages.
    - Collect file metadata.
    - Produce deterministic repository statistics.

Actual source-code understanding is intentionally handled by the
AST/Tree-sitter analysis layer that will be implemented later.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .exceptions import RepositoryError


# ---------------------------------------------------------------------------
# File classification
# ---------------------------------------------------------------------------

class FileCategory(Enum):
    """High-level classification of repository files."""

    SOURCE = "source"
    CONFIGURATION = "configuration"
    DOCUMENTATION = "documentation"
    DATA = "data"
    OTHER = "other"


# ---------------------------------------------------------------------------
# File metadata
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FileMetadata:
    """
    Metadata describing a single repository file.

    Attributes:
        path:
            Path relative to the repository root.

        extension:
            Normalized file extension.

        size_bytes:
            File size in bytes.

        category:
            High-level file category.

        language:
            Detected programming/data/document language, if known.
    """

    path: Path
    extension: str
    size_bytes: int
    category: FileCategory
    language: str | None


# ---------------------------------------------------------------------------
# Repository manifest
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RepositoryManifest:
    """
    Immutable representation of a scanned repository.

    The manifest becomes the structured input for later analysis stages
    such as AST parsing, dependency analysis, code graphs, and RAG.

    Attributes:
        root:
            Absolute path of the analyzed repository.

        files:
            Immutable collection of discovered file metadata.
    """

    root: Path
    files: tuple[FileMetadata, ...]

    @property
    def total_files(self) -> int:
        """Return the total number of discovered files."""

        return len(self.files)

    @property
    def total_size_bytes(self) -> int:
        """Return the combined size of discovered files."""

        return sum(
            file.size_bytes
            for file in self.files
        )

    @property
    def category_statistics(self) -> dict[str, int]:
        """
        Return the number of files in each file category.

        Categories with zero files are omitted from the result.
        """

        statistics: dict[str, int] = {}

        for file in self.files:
            category = file.category.value

            statistics[category] = (
                statistics.get(category, 0) + 1
            )

        return dict(
            sorted(
                statistics.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )

    @property
    def language_statistics(self) -> dict[str, int]:
        """
        Return the number of files detected for each language.

        Files whose language could not be identified are excluded.
        """

        statistics: dict[str, int] = {}

        for file in self.files:
            if file.language is None:
                continue

            statistics[file.language] = (
                statistics.get(file.language, 0) + 1
            )

        return dict(
            sorted(
                statistics.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )


# ---------------------------------------------------------------------------
# Scanner configuration
# ---------------------------------------------------------------------------

DEFAULT_IGNORED_DIRECTORIES: frozenset[str] = frozenset(
    {
        # Version control
        ".git",
        ".hg",
        ".svn",

        # Dependencies
        "node_modules",
        "vendor",

        # Python environments/cache
        "__pycache__",
        ".venv",
        "venv",
        ".tox",

        # Build artifacts
        "dist",
        "build",
        "target",
        "out",

        # Test/analysis caches
        "coverage",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",

        # IDE metadata
        ".idea",
        ".vscode",
    }
)


# File extensions that represent source code.
SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".go",
        ".rs",
        ".php",
        ".rb",
        ".swift",
        ".kt",
        ".kts",
        ".scala",
        ".dart",
        ".lua",
        ".r",
        ".R",
    }
)


# Configuration files.
CONFIGURATION_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".xml",
        ".properties",
    }
)


# Documentation files.
DOCUMENTATION_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".md",
        ".rst",
        ".txt",
        ".adoc",
    }
)


# Data/query files.
DATA_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".csv",
        ".tsv",
        ".sql",
        ".db",
        ".sqlite",
    }
)


# Extension → language mapping.
LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
    ".cs": "C#",
    ".go": "Go",
    ".rs": "Rust",
    ".php": "PHP",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".scala": "Scala",
    ".dart": "Dart",
    ".lua": "Lua",
    ".r": "R",
    ".R": "R",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".less": "Less",
    ".sql": "SQL",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".xml": "XML",
    ".md": "Markdown",
}


# ---------------------------------------------------------------------------
# Special files
# ---------------------------------------------------------------------------

SPECIAL_FILE_LANGUAGES: dict[str, str] = {
    "Dockerfile": "Dockerfile",
    "Makefile": "Makefile",
    "Jenkinsfile": "Groovy/Jenkins",
    "Vagrantfile": "Ruby/Vagrant",
    "Procfile": "Procfile",
}


# ---------------------------------------------------------------------------
# Repository scanner
# ---------------------------------------------------------------------------

class RepositoryScanner:
    """
    Efficiently scan a repository and generate a RepositoryManifest.

    The scanner performs filesystem-level analysis only.

    It deliberately does NOT:
        - read entire source files,
        - generate embeddings,
        - call an LLM,
        - parse ASTs.

    Those responsibilities belong to later stages.
    """

    def __init__(
        self,
        ignored_directories: frozenset[str] = DEFAULT_IGNORED_DIRECTORIES,
    ) -> None:
        """
        Initialize the scanner.

        Args:
            ignored_directories:
                Directory names that should be excluded from traversal.
        """

        self.ignored_directories = ignored_directories

        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(
        self,
        repository_root: Path,
    ) -> RepositoryManifest:
        """
        Scan a repository and return its manifest.

        Args:
            repository_root:
                Root directory of the repository.

        Returns:
            Immutable RepositoryManifest.

        Raises:
            RepositoryError:
                If the repository path is invalid.
        """

        repository_root = repository_root.resolve()

        self._validate_repository_root(
            repository_root
        )

        self.logger.info(
            "Starting repository scan: %s",
            repository_root,
        )

        files: list[FileMetadata] = []

        for current_directory in self._walk_repository(
            repository_root
        ):
            try:
                entries = current_directory.iterdir()

            except OSError as exc:
                self.logger.warning(
                    "Unable to access directory '%s': %s",
                    current_directory,
                    exc,
                )
                continue

            for entry in entries:

                # Only regular files are relevant at this stage.
                if not entry.is_file():
                    continue

                try:
                    metadata = self._build_file_metadata(
                        entry,
                        repository_root,
                    )

                except OSError as exc:
                    self.logger.warning(
                        "Unable to inspect file '%s': %s",
                        entry,
                        exc,
                    )
                    continue

                files.append(metadata)

        # Deterministic ordering makes reports, tests, caching, and
        # downstream indexing reproducible.
        files.sort(
            key=lambda file: file.path.as_posix()
        )

        manifest = RepositoryManifest(
            root=repository_root,
            files=tuple(files),
        )

        self.logger.info(
            "Repository scan completed: %d files discovered.",
            manifest.total_files,
        )

        return manifest

    # ------------------------------------------------------------------
    # Directory traversal
    # ------------------------------------------------------------------

    def _walk_repository(
        self,
        repository_root: Path,
    ):
        """
        Traverse the repository using iterative DFS.

        An explicit stack is used instead of recursive function calls.
        This avoids Python recursion-depth limitations on deeply nested
        repositories.

        Ignored directories are pruned before their contents are
        traversed.
        """

        directories_to_visit: list[Path] = [
            repository_root
        ]

        while directories_to_visit:

            current_directory = (
                directories_to_visit.pop()
            )

            yield current_directory

            try:
                entries = current_directory.iterdir()

            except OSError as exc:
                self.logger.warning(
                    "Unable to access directory '%s': %s",
                    current_directory,
                    exc,
                )
                continue

            for entry in entries:

                if not entry.is_dir():
                    continue

                # Prune ignored directories immediately.
                if entry.name in self.ignored_directories:

                    self.logger.debug(
                        "Skipping ignored directory: %s",
                        entry,
                    )

                    continue

                directories_to_visit.append(entry)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_repository_root(
        repository_root: Path,
    ) -> None:
        """Validate that the repository root is a directory."""

        if not repository_root.exists():
            raise RepositoryError(
                f"Repository does not exist: "
                f"{repository_root}"
            )

        if not repository_root.is_dir():
            raise RepositoryError(
                f"Repository path is not a directory: "
                f"{repository_root}"
            )

    # ------------------------------------------------------------------
    # File metadata
    # ------------------------------------------------------------------

    @staticmethod
    def _build_file_metadata(
        file_path: Path,
        repository_root: Path,
    ) -> FileMetadata:
        """
        Build metadata for one file.

        Only filesystem metadata is accessed. File contents are not
        loaded into memory.
        """

        relative_path = file_path.relative_to(
            repository_root
        )

        extension = file_path.suffix.lower()

        size_bytes = file_path.stat().st_size

        category = RepositoryScanner._classify_file(
            file_path
        )

        language = RepositoryScanner._detect_language(
            file_path,
            extension,
        )

        return FileMetadata(
            path=relative_path,
            extension=extension,
            size_bytes=size_bytes,
            category=category,
            language=language,
        )

    # ------------------------------------------------------------------
    # File classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_file(
        file_path: Path,
    ) -> FileCategory:
        """
        Classify a file using its extension and filename.
        """

        filename = file_path.name
        extension = file_path.suffix.lower()

        # Special files such as Dockerfile have no conventional
        # extension and therefore need filename-based detection.
        if filename in SPECIAL_FILE_LANGUAGES:
            return FileCategory.CONFIGURATION

        if extension in SOURCE_EXTENSIONS:
            return FileCategory.SOURCE

        if extension in CONFIGURATION_EXTENSIONS:
            return FileCategory.CONFIGURATION

        if extension in DOCUMENTATION_EXTENSIONS:
            return FileCategory.DOCUMENTATION

        if extension in DATA_EXTENSIONS:
            return FileCategory.DATA

        return FileCategory.OTHER

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_language(
        file_path: Path,
        extension: str,
    ) -> str | None:
        """
        Detect the language associated with a file.

        Detection currently uses filename and extension metadata only.
        Content-based detection will be added later when required.
        """

        filename = file_path.name

        special_language = SPECIAL_FILE_LANGUAGES.get(
            filename
        )

        if special_language is not None:
            return special_language

        return LANGUAGE_BY_EXTENSION.get(
            extension
        )