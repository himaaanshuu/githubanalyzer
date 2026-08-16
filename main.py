"""
Application entry point for the GitHub Intelligence Engine.

This module currently runs the repository ingestion and filesystem
analysis pipeline.
"""

import logging
from pathlib import Path

from src.github_intelligence.exceptions import RepositoryError
from src.github_intelligence.scanner import RepositoryScanner


def configure_logging() -> None:
    """Configure application-wide logging."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
    )


def print_repository_report(manifest) -> None:
    """Display the structural analysis of a repository."""

    print("\nRepository Analysis")
    print("=" * 50)

    print(f"Repository: {manifest.root}")
    print(f"Total files: {manifest.total_files}")
    print(
        f"Total size: "
        f"{manifest.total_size_bytes:,} bytes"
    )

    print("\nFile Categories")
    print("-" * 50)

    for category, count in manifest.category_statistics.items():
        print(f"{category.capitalize():<20} {count}")

    print("\nLanguages")
    print("-" * 50)

    for language, count in manifest.language_statistics.items():
        print(f"{language:<20} {count}")


def main() -> None:
    """Run the repository scanning pipeline."""

    configure_logging()

    # We are currently analyzing the repository that was already cloned
    # during the previous stage.
    repository_path = Path(
        "repositories/Bitz"
    )

    scanner = RepositoryScanner()

    try:
        manifest = scanner.scan(
            repository_path
        )

    except RepositoryError as exc:
        logging.error("%s", exc)
        return

    print_repository_report(manifest)


if __name__ == "__main__":
    main()