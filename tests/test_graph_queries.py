"""
Integration tests for the repository graph query engine.

Builds the real Bitz knowledge graph and exercises high-level
repository intelligence queries.
"""

from pathlib import Path

from src.github_intelligence.analyzer.repository_analyzer import (
    RepositoryCodeAnalyzer,
)
from src.github_intelligence.graph.builder import (
    KnowledgeGraphBuilder,
)
from src.github_intelligence.graph.queries import (
    GraphQueryEngine,
)
from src.github_intelligence.graph.resolver import (
    GraphResolver,
)


def main() -> None:
    """Build the Bitz graph and test repository queries."""

    repository_root = Path("repositories/Bitz")

    # --------------------------------------------------------------
    # 1. Analyze repository
    # --------------------------------------------------------------

    analyzer = RepositoryCodeAnalyzer()

    inventory = analyzer.analyze(
        repository_root
    )

    # --------------------------------------------------------------
    # 2. Build graph
    # --------------------------------------------------------------

    builder = KnowledgeGraphBuilder()

    graph = builder.build(
        inventory,
        repository_root,
    )

    # --------------------------------------------------------------
    # 3. Resolve graph
    # --------------------------------------------------------------

    resolver = GraphResolver()

    resolution = resolver.resolve(
        graph
    )

    graph = resolution.graph

    # --------------------------------------------------------------
    # 4. Create query engine
    # --------------------------------------------------------------

    queries = GraphQueryEngine(graph)

    print("\nGraph Query Engine")
    print("=" * 70)

    print(
        f"Nodes: {len(graph.nodes)}"
    )

    print(
        f"Edges: {len(graph.edges)}"
    )

    # --------------------------------------------------------------
    # 5. Find OrderPage
    # --------------------------------------------------------------

    print("\nOrderPage")
    print("-" * 70)

    order_pages = queries.find_by_name(
        "OrderPage"
    )

    for node in order_pages:
        print(
            f"{node.name}"
            f" | type={node.node_type.value}"
            f" | file={node.file_path}"
        )

    # --------------------------------------------------------------
    # 6. Test calls
    # --------------------------------------------------------------

    if order_pages:

        order_page = order_pages[0]

        calls = queries.calls(
            order_page.id
        )

        print("\nOrderPage Calls")
        print("-" * 70)

        for node in calls:
            print(
                f"{node.name}"
                f" | {node.node_type.value}"
            )

    # --------------------------------------------------------------
    # 7. Test imports
    # --------------------------------------------------------------

    if order_pages:

        imports = queries.imports(
            order_page.id
        )

        print("\nOrderPage Imports")
        print("-" * 70)

        for node in imports:
            print(
                f"{node.name}"
                f" | {node.node_type.value}"
                f" | {node.file_path}"
            )

    # --------------------------------------------------------------
    # 8. Test callers
    # --------------------------------------------------------------

    create_order_nodes = queries.find_by_name(
        "createOrder"
    )

    print("\ncreateOrder")
    print("-" * 70)

    for node in create_order_nodes:

        print(
            f"Definition:"
            f" {node.name}"
            f" | {node.file_path}"
        )

        callers = queries.callers(
            node.id
        )

        print("Callers:")

        for caller in callers:
            print(
                f"  {caller.name}"
                f" | {caller.file_path}"
            )

    # --------------------------------------------------------------
    # 9. Dependency query
    # --------------------------------------------------------------

    if order_pages:

        result = queries.dependencies(
            order_page.id
        )

        print("\nOrderPage Dependencies")
        print("-" * 70)

        for node in result.dependencies:
            print(
                f"{node.name}"
                f" | {node.node_type.value}"
                f" | {node.file_path}"
            )

    # --------------------------------------------------------------
    # 10. Graph statistics
    # --------------------------------------------------------------

    print("\nNode Statistics")
    print("-" * 70)

    for node_type, count in sorted(
        queries.node_counts().items(),
        key=lambda item: item[0].value,
    ):
        print(
            f"{node_type.value:<20}"
            f"{count}"
        )

    print("\nEdge Statistics")
    print("-" * 70)

    for edge_type, count in sorted(
        queries.edge_counts().items(),
        key=lambda item: item[0].value,
    ):
        print(
            f"{edge_type.value:<20}"
            f"{count}"
        )


if __name__ == "__main__":
    main()