"""
Query engine for the repository knowledge graph.

This module provides high-level, read-only queries over CodeGraph.

The goal is to hide graph traversal details from higher-level systems.

Example:

    OrderPage.jsx
        |
        +-- IMPORTS --> api.js
        |
        +-- CALLS --> createOrder()

The AI/RAG layer should be able to ask:

    "What does OrderPage depend on?"

without knowing how GraphEdge objects are stored internally.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from .models import (
    CodeGraph,
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
)


@dataclass(frozen=True, slots=True)
class GraphPath:
    """
    Represents a path between two graph nodes.

    Example:

        OrderPage
            ↓
        api.js
            ↓
        orders.js
    """

    nodes: tuple[GraphNode, ...]

    @property
    def length(self) -> int:
        """Return the number of edges in the path."""

        return max(
            len(self.nodes) - 1,
            0,
        )


@dataclass(frozen=True, slots=True)
class DependencyResult:
    """Result of a dependency query."""

    source: GraphNode

    dependencies: tuple[GraphNode, ...]


@dataclass(frozen=True, slots=True)
class CallerResult:
    """Result of a caller query."""

    target: GraphNode

    callers: tuple[GraphNode, ...]


class GraphQueryEngine:
    """
    High-performance read-only query interface over CodeGraph.

    Indexes are built once during initialization so repeated queries
    avoid scanning the complete graph.

    Construction:
        O(V + E)

    Most direct relationship queries:
        O(degree(node))

    Symbol lookup:
        O(1) average-case

    Shortest-path traversal:
        O(V + E)
    """

    def __init__(
        self,
        graph: CodeGraph,
    ) -> None:
        self.graph = graph

        self._nodes: dict[
            str,
            GraphNode,
        ] = {
            node.id: node
            for node in graph.nodes
        }

        self._nodes_by_name: dict[
            str,
            tuple[GraphNode, ...],
        ] = self._build_name_index()

        self._outgoing: dict[
            str,
            tuple[GraphEdge, ...],
        ] = self._build_edge_index(
            outgoing=True
        )

        self._incoming: dict[
            str,
            tuple[GraphEdge, ...],
        ] = self._build_edge_index(
            outgoing=False
        )

    # ==================================================================
    # Node lookup
    # ==================================================================

    def get_node(
        self,
        node_id: str,
    ) -> GraphNode | None:
        """Return a node by its unique ID."""

        return self._nodes.get(
            node_id
        )

    def find_by_name(
        self,
        name: str,
    ) -> tuple[GraphNode, ...]:
        """
        Find graph nodes by symbol/file name.

        Example:

            find_by_name("OrderPage")
        """

        return self._nodes_by_name.get(
            name,
            (),
        )

    def find_file(
        self,
        file_path: str | Path,
    ) -> GraphNode | None:
        """Find a file node using its repository path."""

        target = Path(file_path)

        for node in self._nodes.values():
            if (
                node.node_type == NodeType.FILE
                and node.file_path == target
            ):
                return node

        return None

    # ==================================================================
    # Relationship queries
    # ==================================================================

    def outgoing(
        self,
        node_id: str,
        edge_type: EdgeType | None = None,
    ) -> tuple[GraphEdge, ...]:
        """
        Return outgoing relationships from a node.

        Optional edge_type restricts results.

        Example:

            outgoing(
                node_id,
                EdgeType.CALLS,
            )
        """

        edges = self._outgoing.get(
            node_id,
            (),
        )

        if edge_type is None:
            return edges

        return tuple(
            edge
            for edge in edges
            if edge.edge_type == edge_type
        )

    def incoming(
        self,
        node_id: str,
        edge_type: EdgeType | None = None,
    ) -> tuple[GraphEdge, ...]:
        """Return incoming relationships to a node."""

        edges = self._incoming.get(
            node_id,
            (),
        )

        if edge_type is None:
            return edges

        return tuple(
            edge
            for edge in edges
            if edge.edge_type == edge_type
        )

    # ==================================================================
    # Dependency analysis
    # ==================================================================

    def dependencies(
        self,
        node_id: str,
        edge_types: frozenset[EdgeType] | None = None,
    ) -> DependencyResult:
        """
        Return direct dependencies of a node.

        For source entities such as components/functions, the query
        combines:

            entity-level dependencies
            +
            containing-file dependencies

        Default relationships:

            IMPORTS
            CALLS
            USES
            DEPENDS_ON
            REQUESTS
        """

        node = self._require_node(
            node_id
        )

        if edge_types is None:
            edge_types = frozenset(
                {
                    EdgeType.IMPORTS,
                    EdgeType.CALLS,
                    EdgeType.USES,
                    EdgeType.DEPENDS_ON,
                    EdgeType.REQUESTS,
                }
            )

        dependencies: list[GraphNode] = []

        # --------------------------------------------------------------
        # Direct entity dependencies.
        # --------------------------------------------------------------

        for edge in self._outgoing.get(
            node_id,
            (),
        ):

            if edge.edge_type not in edge_types:
                continue

            target = self._nodes.get(
                edge.target_id
            )

            if target is not None:
                dependencies.append(
                    target
                )

        # --------------------------------------------------------------
        # File-level dependencies.
        # --------------------------------------------------------------

        file_node = self._file_for_node(
            node_id
        )

        if (
            file_node is not None
            and file_node.id != node_id
        ):

            for edge in self._outgoing.get(
                file_node.id,
                (),
            ):

                if edge.edge_type not in edge_types:
                    continue

                target = self._nodes.get(
                    edge.target_id
                )

                if target is not None:
                    dependencies.append(
                        target
                    )

        return DependencyResult(
            source=node,
            dependencies=self._unique_nodes(
                dependencies
            ),
        )

    def dependents(
        self,
        node_id: str,
        edge_types: frozenset[EdgeType] | None = None,
    ) -> tuple[GraphNode, ...]:
        """
        Find nodes that depend on the target node.

        Useful for questions such as:

            "Who imports api.js?"
            "Who calls createOrder?"
        """

        if edge_types is None:
            edge_types = frozenset(
                {
                    EdgeType.IMPORTS,
                    EdgeType.CALLS,
                    EdgeType.USES,
                    EdgeType.DEPENDS_ON,
                    EdgeType.REQUESTS,
                }
            )

        results: list[GraphNode] = []

        for edge in self._incoming.get(
            node_id,
            (),
        ):
            if edge.edge_type not in edge_types:
                continue

            source = self._nodes.get(
                edge.source_id
            )

            if source is not None:
                results.append(
                    source
                )

        return self._unique_nodes(
            results
        )

    # ==================================================================
    # Function / method analysis
    # ==================================================================

    def calls(
        self,
        node_id: str,
    ) -> tuple[GraphNode, ...]:
        """Return functions/methods called by a node."""

        return self._targets_for(
            node_id,
            EdgeType.CALLS,
        )

    def callers(
        self,
        node_id: str,
    ) -> tuple[GraphNode, ...]:
        """Return functions/methods that call a node."""

        return self._sources_for(
            node_id,
            EdgeType.CALLS,
        )

    # ==================================================================
    # Import analysis
    # ==================================================================

    def imports(
        self,
        node_id: str,
    ) -> tuple[GraphNode, ...]:
        """
        Return modules/files/symbols imported by a node.

        If the supplied node is a source-code entity such as a
        component or function, imports are resolved through its
        containing file.

        Example:

            OrderPage
                ↓
            OrderPage.jsx
                ↓ IMPORTS
            api.js
                ↓
            createOrder
        """

        node = self._require_node(
            node_id
        )

        # --------------------------------------------------------------
        # Direct imports.
        # --------------------------------------------------------------

        direct = self._targets_for(
            node_id,
            EdgeType.IMPORTS,
        )

        if direct:
            return direct

        # --------------------------------------------------------------
        # Entity-level query.
        #
        # Example:
        #
        # OrderPage -> OrderPage.jsx -> api.js
        # --------------------------------------------------------------

        file_node = self._file_for_node(
            node.id
        )

        if file_node is None:
            return ()

        if file_node.id == node.id:
            return direct

        return self._targets_for(
            file_node.id,
            EdgeType.IMPORTS,
        )

    def imported_by(
        self,
        node_id: str,
    ) -> tuple[GraphNode, ...]:
        """Return files/modules importing this node."""

        return self._sources_for(
            node_id,
            EdgeType.IMPORTS,
        )

    # ==================================================================
    # Containment
    # ==================================================================

    def children(
        self,
        node_id: str,
    ) -> tuple[GraphNode, ...]:
        """Return entities directly contained by a node."""

        return self._targets_for(
            node_id,
            EdgeType.CONTAINS,
        )

    def parent(
        self,
        node_id: str,
    ) -> GraphNode | None:
        """Return the immediate containing node."""

        parents = self._sources_for(
            node_id,
            EdgeType.CONTAINS,
        )

        if not parents:
            return None

        return parents[0]

    # ==================================================================
    # Path analysis
    # ==================================================================

    def shortest_path(
        self,
        source_id: str,
        target_id: str,
        edge_types: frozenset[EdgeType] | None = None,
    ) -> GraphPath | None:
        """
        Find the shortest directed path between two nodes.

        Uses breadth-first search.

        Complexity:
            O(V + E)
        """

        self._require_node(
            source_id
        )

        self._require_node(
            target_id
        )

        if source_id == target_id:
            return GraphPath(
                nodes=(
                    self._nodes[source_id],
                )
            )

        queue: deque[str] = deque(
            [source_id]
        )

        previous: dict[
            str,
            str | None,
        ] = {
            source_id: None
        }

        while queue:
            current = queue.popleft()

            for edge in self._outgoing.get(
                current,
                (),
            ):
                if (
                    edge_types is not None
                    and edge.edge_type
                    not in edge_types
                ):
                    continue

                target = edge.target_id

                if target in previous:
                    continue

                previous[target] = current

                if target == target_id:
                    return self._build_path(
                        previous,
                        target_id,
                    )

                queue.append(target)

        return None

    # ==================================================================
    # Feature tracing
    # ==================================================================

    def trace(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 8,
    ) -> tuple[GraphPath, ...]:
        """
        Find paths between two nodes up to max_depth.

        Unlike shortest_path(), this returns multiple possible paths.

        This will later become useful for feature-flow explanations.
        """

        self._require_node(
            source_id
        )

        self._require_node(
            target_id
        )

        if max_depth < 1:
            return ()

        results: list[GraphPath] = []

        path: list[str] = [
            source_id
        ]

        visited: set[str] = {
            source_id
        }

        self._dfs_paths(
            current=source_id,
            target=target_id,
            max_depth=max_depth,
            path=path,
            visited=visited,
            results=results,
        )

        return tuple(results)

    def _dfs_paths(
        self,
        current: str,
        target: str,
        max_depth: int,
        path: list[str],
        visited: set[str],
        results: list[GraphPath],
    ) -> None:
        """Depth-first traversal used by trace()."""

        if (
            len(path) - 1
            >= max_depth
        ):
            return

        for edge in self._outgoing.get(
            current,
            (),
        ):
            next_id = edge.target_id

            if next_id in visited:
                continue

            path.append(next_id)

            if next_id == target:
                results.append(
                    GraphPath(
                        nodes=tuple(
                            self._nodes[node_id]
                            for node_id in path
                        )
                    )
                )
            else:
                visited.add(next_id)

                self._dfs_paths(
                    current=next_id,
                    target=target,
                    max_depth=max_depth,
                    path=path,
                    visited=visited,
                    results=results,
                )

                visited.remove(next_id)

            path.pop()

    # ==================================================================
    # Statistics
    # ==================================================================

    def node_counts(
        self,
    ) -> dict[NodeType, int]:
        """Return counts grouped by node type."""

        counts: dict[
            NodeType,
            int,
        ] = defaultdict(int)

        for node in self._nodes.values():
            counts[
                node.node_type
            ] += 1

        return dict(counts)

    def edge_counts(
        self,
    ) -> dict[EdgeType, int]:
        """Return counts grouped by edge type."""

        counts: dict[
            EdgeType,
            int,
        ] = defaultdict(int)

        for edges in self._outgoing.values():
            for edge in edges:
                counts[
                    edge.edge_type
                ] += 1

        return dict(counts)

    # ==================================================================
    # Internal indexes
    # ==================================================================

    def _build_name_index(
        self,
    ) -> dict[
        str,
        tuple[GraphNode, ...],
    ]:
        """Build a symbol/name lookup index."""

        index: dict[
            str,
            list[GraphNode],
        ] = defaultdict(list)

        for node in self._nodes.values():

            index[
                node.name
            ].append(node)

            if node.qualified_name:
                index[
                    node.qualified_name
                ].append(node)

        return {
            name: tuple(
                self._unique_nodes(nodes)
            )
            for name, nodes in index.items()
        }

    def _build_edge_index(
        self,
        *,
        outgoing: bool,
    ) -> dict[
        str,
        tuple[GraphEdge, ...],
    ]:
        """Build an adjacency index."""

        index: dict[
            str,
            list[GraphEdge],
        ] = defaultdict(list)

        for edge in self.graph.edges:

            key = (
                edge.source_id
                if outgoing
                else edge.target_id
            )

            index[key].append(
                edge
            )

        return {
            node_id: tuple(edges)
            for node_id, edges
            in index.items()
        }

    # ==================================================================
    # Internal helpers
    # ==================================================================

    def _targets_for(
        self,
        node_id: str,
        edge_type: EdgeType,
    ) -> tuple[GraphNode, ...]:
        """Return target nodes for a specific edge type."""

        return self._unique_nodes(
            [
                self._nodes[edge.target_id]
                for edge in self._outgoing.get(
                    node_id,
                    (),
                )
                if (
                    edge.edge_type == edge_type
                    and edge.target_id
                    in self._nodes
                )
            ]
        )

    def _sources_for(
        self,
        node_id: str,
        edge_type: EdgeType,
    ) -> tuple[GraphNode, ...]:
        """Return source nodes for a specific edge type."""

        return self._unique_nodes(
            [
                self._nodes[edge.source_id]
                for edge in self._incoming.get(
                    node_id,
                    (),
                )
                if (
                    edge.edge_type == edge_type
                    and edge.source_id
                    in self._nodes
                )
            ]
        )

    @staticmethod
    def _unique_nodes(
        nodes: list[GraphNode],
    ) -> tuple[GraphNode, ...]:
        """Deduplicate nodes while preserving deterministic order."""

        unique: dict[
            str,
            GraphNode,
        ] = {}

        for node in nodes:
            unique.setdefault(
                node.id,
                node,
            )

        return tuple(
            sorted(
                unique.values(),
                key=lambda node: node.id,
            )
        )

    def _require_node(
        self,
        node_id: str,
    ) -> GraphNode:
        """Return a node or raise a descriptive error."""

        node = self._nodes.get(
            node_id
        )

        if node is None:
            raise KeyError(
                f"Graph node not found: {node_id}"
            )

        return node

    def _build_path(
        self,
        previous: dict[
            str,
            str | None,
        ],
        target_id: str,
    ) -> GraphPath:
        """Reconstruct a BFS path."""

        path: list[str] = []

        current: str | None = target_id

        while current is not None:
            path.append(current)
            current = previous[current]

        path.reverse()

        return GraphPath(
            nodes=tuple(
                self._nodes[node_id]
                for node_id in path
            )
        )
            # ==================================================================
    # Query scope helpers
    # ==================================================================

    def _file_for_node(
        self,
        node_id: str,
    ) -> GraphNode | None:
        """
        Return the file containing a node.

        For a FILE node, return the node itself.

        For an entity such as a component or function, walk through
        CONTAINS relationships until the containing file is found.

        This allows high-level queries such as:

            dependencies("OrderPage")

        to work even though imports are stored on the file node.
        """

        node = self._nodes.get(
            node_id
        )

        if node is None:
            return None

        if node.node_type == NodeType.FILE:
            return node

        current_id = node_id

        visited: set[str] = set()

        while current_id not in visited:

            visited.add(
                current_id
            )

            parents = self._incoming.get(
                current_id,
                (),
            )

            file_parent = None

            for edge in parents:

                if edge.edge_type != EdgeType.CONTAINS:
                    continue

                parent_node = self._nodes.get(
                    edge.source_id
                )

                if parent_node is None:
                    continue

                if parent_node.node_type == NodeType.FILE:
                    return parent_node

                file_parent = parent_node
                break

            if file_parent is None:
                return None

            current_id = file_parent.id

        return None