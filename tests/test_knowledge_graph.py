"""
Integration test for the repository knowledge graph.

This test runs the real Bitz repository through:

    RepositoryCodeAnalyzer
            ↓
    KnowledgeGraphBuilder
            ↓
    GraphResolver

The goal is to verify that structural relationships are actually
being produced from real source code.
"""

from pathlib import Path

from src.github_intelligence.analyzer.repository_analyzer import (
    RepositoryCodeAnalyzer,
)
from src.github_intelligence.graph.builder import (
    KnowledgeGraphBuilder,
)
from src.github_intelligence.graph.models import (
    EdgeType,
    NodeType,
)
from src.github_intelligence.graph.resolver import (
    GraphResolver,
)


def main() -> None:
    """Build and inspect the Bitz repository knowledge graph."""

    repository_root = Path(
        "repositories/Bitz"
    )

    # ---------------------------------------------------------------
    # 1. Analyze repository source code
    # ---------------------------------------------------------------

    analyzer = RepositoryCodeAnalyzer()

    inventory = analyzer.analyze(
        repository_root
    )

    print("\nRepository Knowledge Graph")
    print("=" * 70)

    print(
        f"Files analyzed: "
        f"{inventory.total_files}"
    )

    print(
        f"Entities: "
        f"{inventory.total_entities}"
    )

    print(
        f"Imports: "
        f"{inventory.total_imports}"
    )

    print(
        f"Calls: "
        f"{inventory.total_calls}"
    )

    # ---------------------------------------------------------------
    # 2. Build graph
    # ---------------------------------------------------------------

    builder = KnowledgeGraphBuilder()

    graph = builder.build(
        inventory,
        repository_root,
    )

    print("\nGraph Before Resolution")
    print("-" * 70)

    print(
        f"Nodes: "
        f"{graph.node_count}"
    )

    print(
        f"Edges: "
        f"{graph.edge_count}"
    )

    # ---------------------------------------------------------------
    # 3. Resolve graph relationships
    # ---------------------------------------------------------------

    resolver = GraphResolver()

    resolution = resolver.resolve(
        graph
    )

    resolved_graph = resolution.graph

    print("\nGraph Resolution")
    print("-" * 70)

    print(
        f"Resolved edges: "
        f"{resolution.resolved_edges}"
    )

    print(
        f"Unresolved edges: "
        f"{resolution.unresolved_edges}"
    )

    print(
        f"Ambiguous edges: "
        f"{resolution.ambiguous_edges}"
    )

    print("\nFinal Graph")
    print("-" * 70)

    print(
        f"Nodes: "
        f"{resolved_graph.node_count}"
    )

    print(
        f"Edges: "
        f"{resolved_graph.edge_count}"
    )

    # ---------------------------------------------------------------
    # 4. Graph node statistics
    # ---------------------------------------------------------------

    node_counts: dict[NodeType, int] = {}

    for node in resolved_graph.nodes:
        node_counts[node.node_type] = (
            node_counts.get(
                node.node_type,
                0,
            )
            + 1
        )

    print("\nNode Types")
    print("-" * 70)

    for node_type, count in sorted(
        node_counts.items(),
        key=lambda item: item[0].value,
    ):
        print(
            f"{node_type.value:<20}"
            f"{count}"
        )

    # ---------------------------------------------------------------
    # 5. Graph edge statistics
    # ---------------------------------------------------------------

    edge_counts: dict[EdgeType, int] = {}

    for edge in resolved_graph.edges:
        edge_counts[edge.edge_type] = (
            edge_counts.get(
                edge.edge_type,
                0,
            )
            + 1
        )

    print("\nEdge Types")
    print("-" * 70)

    for edge_type, count in sorted(
        edge_counts.items(),
        key=lambda item: item[0].value,
    ):
        print(
            f"{edge_type.value:<20}"
            f"{count}"
        )

    # ---------------------------------------------------------------
    # 6. Display sample relationships
    # ---------------------------------------------------------------

    print("\nSample Relationships")
    print("-" * 70)

    displayed = 0

    for edge in resolved_graph.edges:

        source = resolved_graph.node(
            edge.source_id
        )

        target = resolved_graph.node(
            edge.target_id
        )

        if source is None or target is None:
            continue

        print(
            f"{source.name}"
            f" --{edge.edge_type.value.upper()}--> "
            f"{target.name}"
        )

        displayed += 1

        if displayed >= 25:
            break


if __name__ == "__main__":
    main()