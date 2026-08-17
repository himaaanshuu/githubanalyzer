"""
Symbol and dependency resolution for the repository knowledge graph.

The resolver converts uncertain structural relationships into
high-confidence relationships by using:

    - same-file symbol lookup
    - local import relationships
    - imported symbol metadata
    - qualified names
    - repository-wide unique symbols

Resolution is deliberately conservative. When multiple possible
definitions exist, the resolver does not guess.
"""

from __future__ import annotations

import logging
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
class ResolutionResult:
    """Result produced by graph resolution."""

    graph: CodeGraph

    resolved_edges: int

    unresolved_edges: int

    ambiguous_edges: int


class GraphResolver:
    """
    Resolve uncertain relationships in a CodeGraph.

    Resolution strategy:

        1. Build indexes.
        2. Resolve CALLS.
        3. Resolve IMPORTS.
        4. Preserve unresolved relationships.
        5. Return a new immutable graph.

    The original CodeGraph is never mutated.
    """

    def __init__(self) -> None:

        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )

        self._nodes_by_id: dict[
            str,
            GraphNode,
        ] = {}

        self._edges: dict[
            tuple[str, str, EdgeType],
            GraphEdge,
        ] = {}

        self._symbols: dict[
            str,
            list[GraphNode],
        ] = {}

        self._files: dict[
            Path,
            GraphNode,
        ] = {}

    # ==================================================================
    # Public API
    # ==================================================================

    def resolve(
        self,
        graph: CodeGraph,
    ) -> ResolutionResult:
        """
        Resolve relationships in the graph.

        Resolution is intentionally performed after graph construction
        so that all files, entities, imports and calls are available.
        """

        self._reset()

        # --------------------------------------------------------------
        # Index nodes.
        # --------------------------------------------------------------

        for node in graph.nodes:
            self._index_node(node)

        # --------------------------------------------------------------
        # Copy existing edges.
        # --------------------------------------------------------------

        for edge in graph.edges:

            self._edges[
                (
                    edge.source_id,
                    edge.target_id,
                    edge.edge_type,
                )
            ] = edge

        resolved = 0
        unresolved = 0
        ambiguous = 0

        # --------------------------------------------------------------
        # Resolve relationships.
        # --------------------------------------------------------------

        original_edges = tuple(
            graph.edges
        )

        for edge in original_edges:

            if edge.edge_type == EdgeType.CALLS:

                result = self._resolve_call(
                    edge
                )

            elif edge.edge_type == EdgeType.IMPORTS:

                result = self._resolve_import(
                    edge
                )

            else:
                continue

            if result == "resolved":
                resolved += 1

            elif result == "ambiguous":
                ambiguous += 1

            else:
                unresolved += 1

        # --------------------------------------------------------------
        # Build immutable graph.
        # --------------------------------------------------------------

        resolved_graph = CodeGraph(
            nodes=tuple(
                sorted(
                    self._nodes_by_id.values(),
                    key=lambda node: node.id,
                )
            ),
            edges=tuple(
                sorted(
                    self._edges.values(),
                    key=lambda edge: (
                        edge.source_id,
                        edge.edge_type.value,
                        edge.target_id,
                    ),
                )
            ),
        )

        self.logger.info(
            "Graph resolution completed: "
            "%d resolved | %d unresolved | %d ambiguous",
            resolved,
            unresolved,
            ambiguous,
        )

        return ResolutionResult(
            graph=resolved_graph,
            resolved_edges=resolved,
            unresolved_edges=unresolved,
            ambiguous_edges=ambiguous,
        )

    # ==================================================================
    # Index construction
    # ==================================================================

    def _index_node(
        self,
        node: GraphNode,
    ) -> None:
        """Index a graph node for efficient lookup."""

        self._nodes_by_id[
            node.id
        ] = node

        if node.node_type == NodeType.FILE:

            if node.file_path is not None:

                self._files[
                    node.file_path
                ] = node

        if node.node_type in {
            NodeType.FUNCTION,
            NodeType.METHOD,
            NodeType.CLASS,
            NodeType.COMPONENT,
            NodeType.VARIABLE,
        }:

            self._symbols.setdefault(
                node.name,
                [],
            ).append(node)

            if node.qualified_name:

                self._symbols.setdefault(
                    node.qualified_name,
                    [],
                ).append(node)

    # ==================================================================
    # CALL resolution
    # ==================================================================

    def _resolve_call(
        self,
        edge: GraphEdge,
    ) -> str:
        """
        Resolve a CALLS edge.

        Resolution order:

            1. Already resolved
            2. Same-file symbol
            3. Imported symbol
            4. Qualified imported symbol
            5. Unique repository symbol
            6. Ambiguous
            7. Unresolved
        """

        source = self._nodes_by_id.get(
            edge.source_id
        )

        target = self._nodes_by_id.get(
            edge.target_id
        )

        if source is None or target is None:
            return "unresolved"

        # Already resolved.
        if not target.id.startswith(
            "unresolved:"
        ):
            return "resolved"

        symbol = target.name

        # --------------------------------------------------------------
        # 1. Same-file resolution.
        # --------------------------------------------------------------

        same_file = self._same_file_candidates(
            source,
            symbol,
        )

        if len(same_file) == 1:

            self._replace_edge_target(
                edge,
                same_file[0].id,
            )

            return "resolved"

        if len(same_file) > 1:
            return "ambiguous"

        # --------------------------------------------------------------
        # 2. Imported symbol resolution.
        # --------------------------------------------------------------

        imported = self._resolve_imported_call(
            source,
            symbol,
        )

        if len(imported) == 1:

            self._replace_edge_target(
                edge,
                imported[0].id,
            )

            return "resolved"

        if len(imported) > 1:
            return "ambiguous"

        # --------------------------------------------------------------
        # 3. Repository-wide unique symbol.
        # --------------------------------------------------------------

        candidates = self._candidate_symbols(
            symbol
        )

        if len(candidates) == 1:

            self._replace_edge_target(
                edge,
                candidates[0].id,
            )

            return "resolved"

        if len(candidates) > 1:
            return "ambiguous"

        return "unresolved"

    # ==================================================================
    # Imported call resolution
    # ==================================================================

    def _resolve_imported_call(
        self,
        source: GraphNode,
        symbol: str,
    ) -> list[GraphNode]:
        """
        Resolve a call through the caller's import relationships.

        Examples:

            import { createOrder } from "../services/api"

            createOrder()

        or:

            import api from "../services/api"

            api.createOrder()

        The resolver follows:

            caller
                ↓
            containing file
                ↓
            IMPORTS
                ↓
            imported file
                ↓
            symbol definition
        """

        source_file = self._containing_file(
            source
        )

        if source_file is None:
            return []

        imported_files = self._imported_files(
            source_file
        )

        if not imported_files:
            return []

        # --------------------------------------------------------------
        # Direct symbol.
        #
        # createOrder
        # --------------------------------------------------------------

        direct_name = symbol

        # --------------------------------------------------------------
        # Qualified symbol.
        #
        # api.createOrder
        #
        # Extract the final property.
        # --------------------------------------------------------------

        property_name = symbol.split(
            "."
        )[-1]

        names = {
            direct_name,
            property_name,
        }

        results: dict[
            str,
            GraphNode,
        ] = {}

        for imported_file in imported_files:

            target_path = (
                imported_file.file_path
            )

            if target_path is None:
                continue

            for name in names:

                candidates = self._symbols.get(
                    name,
                    [],
                )

                for candidate in candidates:

                    if (
                        candidate.file_path
                        != target_path
                    ):
                        continue

                    if candidate.node_type not in {
                        NodeType.FUNCTION,
                        NodeType.METHOD,
                        NodeType.CLASS,
                        NodeType.COMPONENT,
                        NodeType.VARIABLE,
                    }:
                        continue

                    results[
                        candidate.id
                    ] = candidate

        return list(
            results.values()
        )

    # ==================================================================
    # Import resolution
    # ==================================================================

    def _resolve_import(
        self,
        edge: GraphEdge,
    ) -> str:
        """
        Validate an IMPORTS relationship.

        Local files and external modules are already valid graph
        targets.

        Symbol-level imports are also valid when they point to a
        known repository symbol.
        """

        target = self._nodes_by_id.get(
            edge.target_id
        )

        if target is None:
            return "unresolved"

        if target.node_type in {
            NodeType.FILE,
            NodeType.EXTERNAL_MODULE,
            NodeType.FUNCTION,
            NodeType.METHOD,
            NodeType.CLASS,
            NodeType.COMPONENT,
            NodeType.VARIABLE,
        }:

            return "resolved"

        return "unresolved"

    # ==================================================================
    # Import helpers
    # ==================================================================

    def _imported_files(
        self,
        source_file: GraphNode,
    ) -> tuple[GraphNode, ...]:
        """Return repository files imported by a source file."""

        results: dict[
            str,
            GraphNode,
        ] = {}

        for edge in self._edges.values():

            if (
                edge.source_id
                != source_file.id
            ):
                continue

            if edge.edge_type != EdgeType.IMPORTS:
                continue

            target = self._nodes_by_id.get(
                edge.target_id
            )

            if target is None:
                continue

            if target.node_type != NodeType.FILE:
                continue

            results[
                target.id
            ] = target

        return tuple(
            results.values()
        )

    # ==================================================================
    # Symbol lookup
    # ==================================================================

    def _candidate_symbols(
        self,
        symbol: str,
    ) -> list[GraphNode]:
        """Return unique nodes matching a symbol."""

        candidates = self._symbols.get(
            symbol,
            [],
        )

        unique: dict[
            str,
            GraphNode,
        ] = {}

        for node in candidates:
            unique[
                node.id
            ] = node

        return list(
            unique.values()
        )

    def _same_file_candidates(
        self,
        source: GraphNode,
        symbol: str,
    ) -> list[GraphNode]:
        """Return symbols with the same name in the caller's file."""

        if source.file_path is None:
            return []

        results: dict[
            str,
            GraphNode,
        ] = {}

        for candidate in self._candidate_symbols(
            symbol
        ):

            if (
                candidate.file_path
                != source.file_path
            ):
                continue

            results[
                candidate.id
            ] = candidate

        return list(
            results.values()
        )

    # ==================================================================
    # Containment
    # ==================================================================

    def _containing_file(
        self,
        node: GraphNode,
    ) -> GraphNode | None:
        """
        Return the file containing an entity.

        Most graph entities already carry file_path, so this method
        primarily uses that information.
        """

        if node.node_type == NodeType.FILE:
            return node

        if node.file_path is None:
            return None

        return self._files.get(
            node.file_path
        )

    # ==================================================================
    # Edge replacement
    # ==================================================================

    def _replace_edge_target(
        self,
        edge: GraphEdge,
        target_id: str,
    ) -> None:
        """Replace an unresolved edge with a resolved edge."""

        old_key = (
            edge.source_id,
            edge.target_id,
            edge.edge_type,
        )

        self._edges.pop(
            old_key,
            None,
        )

        new_edge = GraphEdge(
            source_id=edge.source_id,
            target_id=target_id,
            edge_type=edge.edge_type,
            metadata={
                **dict(edge.metadata),
                "resolved": True,
            },
        )

        new_key = (
            new_edge.source_id,
            new_edge.target_id,
            new_edge.edge_type,
        )

        self._edges[
            new_key
        ] = new_edge

    # ==================================================================
    # State
    # ==================================================================

    def _reset(self) -> None:
        """Reset resolver state."""

        self._nodes_by_id.clear()

        self._edges.clear()

        self._symbols.clear()

        self._files.clear()