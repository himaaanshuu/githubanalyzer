
from pathlib import Path

from src.github_intelligence.analyzer.javascript import (
    JavaScriptParser,
)


def main() -> None:
    """Run JavaScript analysis against a real Bitz file."""

    repository_root = Path("repositories/Bitz")

    parser = JavaScriptParser()

    javascript_files = sorted(
        repository_root.rglob("*.js")
    )

    if not javascript_files:
        print("No JavaScript files found.")
        return

    file_path = javascript_files[0]

    source = file_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    relative_path = file_path.relative_to(
        repository_root
    )

    entities, imports, calls = parser.analyze(
        source,
        relative_path,
    )

    print("\nJavaScript Analysis")
    print("=" * 60)

    print(f"File: {relative_path}")
    print(f"Functions/classes: {len(entities)}")
    print(f"Imports: {len(imports)}")
    print(f"Calls: {len(calls)}")

    print("\nEntities")
    print("-" * 60)

    for entity in entities:
        print(
            f"{entity.entity_type.value:<10}"
            f" {entity.name:<30}"
            f" line {entity.location.start_line}"
        )

    print("\nImports")
    print("-" * 60)

    for import_ref in imports:
        print(
            f"line {import_ref.location.start_line:<5}"
            f" {import_ref.source}"
        )

    print("\nCalls")
    print("-" * 60)

    for call in calls[:30]:
        print(
            f"{call.caller:<25}"
            f" -> {call.callee}"
        )


if __name__ == "__main__":
    main()
