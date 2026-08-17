from pathlib import Path

from src.github_intelligence.analyzer.repository_analyzer import (
    RepositoryCodeAnalyzer,
)


def main() -> None:
    """Analyze the complete Bitz repository."""

    repository_root = Path("repositories/Bitz")

    analyzer = RepositoryCodeAnalyzer()

    inventory = analyzer.analyze(repository_root)

    print("\nRepository Code Intelligence")
    print("=" * 60)

    print(
        f"JavaScript files analyzed: "
        f"{inventory.total_files}"
    )

    print(
        f"Code entities: "
        f"{inventory.total_entities}"
    )

    print(
        f"Imports: "
        f"{inventory.total_imports}"
    )

    print(
        f"Exports: "
        f"{inventory.total_exports}"
    )

    print(
        f"Function/method calls: "
        f"{inventory.total_calls}"
    )

    print(
        f"Files with syntax errors: "
        f"{inventory.files_with_syntax_errors}"
    )

    print("\nFiles")
    print("-" * 60)

    for result in inventory.files:
        print(
            f"{result.file_path}"
            f" | entities={len(result.entities)}"
            f" | imports={len(result.imports)}"
            f" | exports={len(result.exports)}"
            f" | calls={len(result.calls)}"
            f" | syntax_errors={result.has_syntax_errors}"
        )


if __name__ == "__main__":
    main()
