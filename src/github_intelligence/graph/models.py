"""
Core data models for the repository knowledge graph.

The graph represents structural relationships discovered from source
code analysis.

Example:

    OrderPage.jsx
        ├── IMPORTS ──> api.js
        ├── IMPORTS ──> createOrder
        └── CALLS ────> createOrderAndPay()
                              └── CALLS ──> createOrder()

The graph layer is intentionally independent of any database or graph
library. This keeps the core intelligence engine portable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping


class NodeType(str, Enum):
    """Supported knowledge-graph node types."""

    # Repository structure
    REPOSITORY = "repository"
    DIRECTORY = "directory"
    FILE = "file"

    # Code entities
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    COMPONENT = "component"

    # Higher-level semantic entities
    API_ENDPOINT = "api_endpoint"
    DATABASE_MODEL = "database_model"

    # Generic / unresolved symbols
    VARIABLE = "variable"

    # External dependencies
    EXTERNAL_MODULE = "external_module"


class EdgeType(str, Enum):
    """Supported relationships between graph nodes."""

    # Structural relationships
    CONTAINS = "contains"
    DEFINES = "defines"

    # Module relationships
    IMPORTS = "imports"
    EXPORTS = "exports"

    # Code relationships
    CALLS = "calls"
    USES = "uses"
    DEPENDS_ON = "depends_on"

    # Application relationships
    REQUESTS = "requests"

    # Object-oriented relationships
    EXTENDS = "extends"
    IMPLEMENTS = "implements"


@dataclass(frozen=True, slots=True)
class GraphNode:
    """
    Immutable node representing an entity in the repository graph.

    A GraphNode can represent:

        - repository
        - directory
        - source file
        - function
        - method
        - class
        - React component
        - API endpoint
        - database model
        - variable
        - external module

    Attributes:
        id:
            Globally unique identifier.

        node_type:
            Semantic category of the node.

        name:
            Human-readable entity name.

        file_path:
            Source file associated with the node, when applicable.

        qualified_name:
            Fully qualified symbol name when available.

        metadata:
            Additional structured information discovered during
            repository analysis.
    """

    id: str

    node_type: NodeType

    name: str

    file_path: Path | None = None

    qualified_name: str | None = None

    metadata: Mapping[str, object] = field(
        default_factory=dict
    )

    @property
    def is_code_entity(self) -> bool:
        """Return True when the node represents a source-code entity."""

        return self.node_type in {
            NodeType.FUNCTION,
            NodeType.METHOD,
            NodeType.CLASS,
            NodeType.COMPONENT,
            NodeType.VARIABLE,
        }

    @property
    def is_file(self) -> bool:
        """Return True when the node represents a source file."""

        return self.node_type == NodeType.FILE

    @property
    def is_external(self) -> bool:
        """Return True when the node represents an external module."""

        return self.node_type == NodeType.EXTERNAL_MODULE


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """
    Immutable directed relationship between two graph nodes.

    Example:

        OrderPage
            --IMPORTS-->
        api.js

        OrderPage
            --CALLS-->
        createOrder()

    Attributes:
        source_id:
            ID of the originating node.

        target_id:
            ID of the destination node.

        edge_type:
            Semantic relationship.

        metadata:
            Evidence and additional information about the relationship.

            Examples:

                {
                    "source": "../services/api.js",
                    "symbol": "createOrder",
                    "line": 12,
                }

            or:

                {
                    "line": 42,
                    "resolved": True,
                }
    """

    source_id: str

    target_id: str

    edge_type: EdgeType

    metadata: Mapping[str, object] = field(
        default_factory=dict
    )

    @property
    def is_resolved(self) -> bool:
        """
        Return whether the relationship has been resolved.

        Relationships without an explicit ``resolved`` field are treated
        as resolved because structural relationships such as CONTAINS
        and IMPORTS are deterministic.
        """

        resolved = self.metadata.get(
            "resolved"
        )

        if resolved is None:
            return True

        return bool(resolved)


@dataclass(frozen=True, slots=True)
class CodeGraph:
    """
    Immutable repository knowledge graph.

    The graph is represented using tuples rather than mutable lists so
    the result can safely be passed between analysis stages.

    Nodes and edges are intentionally parser-independent.

    Higher-level systems such as:

        - dependency analysis
        - architecture analysis
        - RAG
        - embeddings
        - LLM reasoning
        - frontend visualization

    can consume this graph without knowing anything about Tree-sitter.
    """

    nodes: tuple[GraphNode, ...] = ()

    edges: tuple[GraphEdge, ...] = ()

    @property
    def node_count(self) -> int:
        """Return the total number of nodes."""

        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        """Return the total number of edges."""

        return len(self.edges)

    @property
    def resolved_edge_count(self) -> int:
        """Return the number of resolved graph relationships."""

        return sum(
            edge.is_resolved
            for edge in self.edges
        )

    @property
    def unresolved_edge_count(self) -> int:
        """Return the number of unresolved graph relationships."""

        return sum(
            not edge.is_resolved
            for edge in self.edges
        )

    def node(
        self,
        node_id: str,
    ) -> GraphNode | None:
        """
        Find a node by ID.

        Complexity:
            O(n)

        This method is intended for occasional inspection.
        The query engine maintains dictionaries for hot-path lookups.
        """

        return next(
            (
                node
                for node in self.nodes
                if node.id == node_id
            ),
            None,
        )

    def outgoing_edges(
        self,
        node_id: str,
    ) -> tuple[GraphEdge, ...]:
        """Return all relationships originating from a node."""

        return tuple(
            edge
            for edge in self.edges
            if edge.source_id == node_id
        )

    def incoming_edges(
        self,
        node_id: str,
    ) -> tuple[GraphEdge, ...]:
        """Return all relationships pointing to a node."""

        return tuple(
            edge
            for edge in self.edges
            if edge.target_id == node_id
        )

    def edges_of_type(
        self,
        edge_type: EdgeType,
    ) -> tuple[GraphEdge, ...]:
        """Return all edges of a particular relationship type."""

        return tuple(
            edge
            for edge in self.edges
            if edge.edge_type == edge_type
        )

    def nodes_of_type(
        self,
        node_type: NodeType,
    ) -> tuple[GraphNode, ...]:
        """Return all nodes of a particular type."""

        return tuple(
            node
            for node in self.nodes
            if node.node_type == node_type
        )