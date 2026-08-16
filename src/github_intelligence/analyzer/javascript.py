"""
JavaScript structural analyzer powered by Tree-sitter.

Extracts:
    - Function declarations
    - Function expressions
    - Arrow functions
    - React-style functional components
    - Classes
    - Class methods
    - Imports
    - Exports
    - Function/method calls

The analyzer converts Tree-sitter nodes into parser-independent
models defined in ``models.py``.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_javascript
from tree_sitter import Language, Node

from .models import (
    CallReference,
    CodeEntity,
    CodeEntityType,
    ExportReference,
    ImportReference,
    SourceLocation,
)
from .parser import CodeParser


class JavaScriptParser(CodeParser):
    """Tree-sitter parser and structural analyzer for JavaScript."""

    def __init__(self) -> None:
        super().__init__()

    @property
    def language_name(self) -> str:
        """Return the language supported by this parser."""

        return "JavaScript"

    def configure(self) -> None:
        """Configure Tree-sitter with the JavaScript grammar."""

        self._parser.language = Language(
            tree_sitter_javascript.language()
        )

    def analyze(
        self,
        source: str,
        file_path: Path,
    ) -> tuple[
        tuple[CodeEntity, ...],
        tuple[ImportReference, ...],
        tuple[ExportReference, ...],
        tuple[CallReference, ...],
        bool,
    ]:
        """
        Parse and analyze JavaScript source.

        The source is parsed exactly once. The resulting AST is then
        traversed to extract all supported structural information.

        Returns:
            entities:
                Functions, methods, classes, and components.

            imports:
                ES module imports.

            exports:
                Export declarations.

            calls:
                Function and method calls.

            has_errors:
                Whether Tree-sitter detected syntax errors.
        """

        result = self.parse(
            source,
            file_path,
        )

        entities: list[CodeEntity] = []
        imports: list[ImportReference] = []
        exports: list[ExportReference] = []
        calls: list[CallReference] = []

        self._extract_nodes(
            result.root,
            source,
            file_path,
            entities,
            imports,
            exports,
            calls,
        )

        return (
            tuple(entities),
            tuple(imports),
            tuple(exports),
            tuple(calls),
            result.has_errors,
        )

    def _extract_nodes(
        self,
        root: Node,
        source: str,
        file_path: Path,
        entities: list[CodeEntity],
        imports: list[ImportReference],
        exports: list[ExportReference],
        calls: list[CallReference],
    ) -> None:
        """Traverse the AST and extract supported JavaScript entities."""

        stack: list[tuple[Node, str | None]] = [
            (root, None)
        ]

        while stack:
            node, parent_name = stack.pop()

            node_type = node.type

            # ----------------------------------------------------------
            # Function declarations
            # ----------------------------------------------------------

            if node_type == "function_declaration":
                entity = self._extract_named_function(
                    node=node,
                    source=source,
                    file_path=file_path,
                    parent_name=parent_name,
                    entity_type=CodeEntityType.FUNCTION,
                )

                if entity is not None:
                    entities.append(entity)

            # ----------------------------------------------------------
            # Function expressions
            # ----------------------------------------------------------

            elif node_type == "function_expression":
                entity = self._extract_function_expression(
                    node=node,
                    source=source,
                    file_path=file_path,
                    parent_name=parent_name,
                )

                if entity is not None:
                    entities.append(entity)

            # ----------------------------------------------------------
            # Arrow functions
            # ----------------------------------------------------------

            elif node_type == "arrow_function":
                entity = self._extract_arrow_function(
                    node=node,
                    source=source,
                    file_path=file_path,
                    parent_name=parent_name,
                )

                if entity is not None:
                    entities.append(entity)

            # ----------------------------------------------------------
            # Classes
            # ----------------------------------------------------------

            elif node_type == "class_declaration":
                entity = self._extract_class(
                    node=node,
                    source=source,
                    file_path=file_path,
                )

                if entity is not None:
                    entities.append(entity)

                class_name_node = node.child_by_field_name(
                    "name"
                )

                if class_name_node is not None:
                    parent_name = self._node_text(
                        class_name_node,
                        source,
                    )

            # ----------------------------------------------------------
            # Class methods
            # ----------------------------------------------------------

            elif node_type == "method_definition":
                entity = self._extract_named_function(
                    node=node,
                    source=source,
                    file_path=file_path,
                    parent_name=parent_name,
                    entity_type=CodeEntityType.METHOD,
                )

                if entity is not None:
                    entities.append(entity)

            # ----------------------------------------------------------
            # Imports
            # ----------------------------------------------------------

            elif node_type == "import_statement":
                imports.append(
                    ImportReference(
                        source=self._node_text(
                            node,
                            source,
                        ),
                        file_path=file_path,
                        location=self._location(node),
                    )
                )

            # ----------------------------------------------------------
            # Exports
            # ----------------------------------------------------------

            elif node_type == "export_statement":
                exports.append(
                    ExportReference(
                        source=self._node_text(
                            node,
                            source,
                        ),
                        file_path=file_path,
                        location=self._location(node),
                    )
                )

            # ----------------------------------------------------------
            # Calls
            # ----------------------------------------------------------

            elif node_type == "call_expression":
                call = self._extract_call(
                    node=node,
                    source=source,
                    file_path=file_path,
                    caller=parent_name,
                )

                if call is not None:
                    calls.append(call)

            # Preserve source order during iterative traversal.
            stack.extend(
                (child, parent_name)
                for child in reversed(node.children)
            )

    # ==================================================================
    # Functions
    # ==================================================================

    def _extract_named_function(
        self,
        node: Node,
        source: str,
        file_path: Path,
        parent_name: str | None,
        entity_type: CodeEntityType,
    ) -> CodeEntity | None:
        """Extract a named function or class method."""

        name_node = node.child_by_field_name(
            "name"
        )

        if name_node is None:
            return None

        name = self._node_text(
            name_node,
            source,
        )

        if not name:
            return None

        return CodeEntity(
            entity_type=entity_type,
            name=name,
            file_path=file_path,
            location=self._location(node),
            parent=parent_name,
            parameters=self._extract_parameters(
                node,
                source,
            ),
            source=self._node_text(
                node,
                source,
            ),
            is_async=self._is_async(node),
        )

    def _extract_function_expression(
        self,
        node: Node,
        source: str,
        file_path: Path,
        parent_name: str | None,
    ) -> CodeEntity | None:
        """
        Extract a named function expression.

        Anonymous function expressions are handled when assigned to a
        variable or object property.
        """

        name_node = node.child_by_field_name(
            "name"
        )

        if name_node is not None:
            name = self._node_text(
                name_node,
                source,
            )
        else:
            name = self._assigned_function_name(
                node,
                source,
            )

        if not name:
            return None

        return CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name=name,
            file_path=file_path,
            location=self._location(node),
            parent=parent_name,
            parameters=self._extract_parameters(
                node,
                source,
            ),
            source=self._node_text(
                node,
                source,
            ),
            is_async=self._is_async(node),
        )

    # ==================================================================
    # Arrow functions
    # ==================================================================

    def _extract_arrow_function(
        self,
        node: Node,
        source: str,
        file_path: Path,
        parent_name: str | None,
    ) -> CodeEntity | None:
        """
        Extract an arrow function.

        React functional components are identified using conventional
        PascalCase naming, for example ``Navbar`` or ``OrderPage``.
        """

        name = self._assigned_function_name(
            node,
            source,
        )

        if not name:
            return None

        entity_type = (
            CodeEntityType.COMPONENT
            if self._looks_like_component(name)
            else CodeEntityType.FUNCTION
        )

        return CodeEntity(
            entity_type=entity_type,
            name=name,
            file_path=file_path,
            location=self._location(node),
            parent=parent_name,
            parameters=self._extract_parameters(
                node,
                source,
            ),
            source=self._node_text(
                node,
                source,
            ),
            is_async=self._is_async(node),
        )

    # ==================================================================
    # Classes
    # ==================================================================

    def _extract_class(
        self,
        node: Node,
        source: str,
        file_path: Path,
    ) -> CodeEntity | None:
        """Extract a JavaScript class declaration."""

        name_node = node.child_by_field_name(
            "name"
        )

        if name_node is None:
            return None

        name = self._node_text(
            name_node,
            source,
        )

        if not name:
            return None

        return CodeEntity(
            entity_type=CodeEntityType.CLASS,
            name=name,
            file_path=file_path,
            location=self._location(node),
            source=self._node_text(
                node,
                source,
            ),
        )

    # ==================================================================
    # Imports / exports
    # ==================================================================

    def _extract_call(
        self,
        node: Node,
        source: str,
        file_path: Path,
        caller: str | None,
    ) -> CallReference | None:
        """Extract a function or method call."""

        function_node = node.child_by_field_name(
            "function"
        )

        if function_node is None:
            return None

        callee = self._node_text(
            function_node,
            source,
        )

        if not callee:
            return None

        return CallReference(
            caller=caller or "<module>",
            callee=callee,
            file_path=file_path,
            location=self._location(node),
        )

    # ==================================================================
    # Helper methods
    # ==================================================================

    @staticmethod
    def _assigned_function_name(
        node: Node,
        source: str,
    ) -> str | None:
        """
        Determine the name assigned to an anonymous function.

        Supports patterns such as:

            const login = () => {};
            const login = function () {};
            const api = {
                login: () => {}
            };
        """

        parent = node.parent

        if parent is None:
            return None

        # const functionName = () => {}
        if parent.type == "variable_declarator":
            name_node = parent.child_by_field_name(
                "name"
            )

            if name_node is not None:
                return JavaScriptParser._node_text(
                    name_node,
                    source,
                )

        # { login: () => {} }
        if parent.type == "pair":
            key_node = parent.child_by_field_name(
                "key"
            )

            if key_node is not None:
                return JavaScriptParser._node_text(
                    key_node,
                    source,
                )

        return None

    @staticmethod
    def _extract_parameters(
        node: Node,
        source: str,
    ) -> tuple[str, ...]:
        """Extract function parameters."""

        parameters_node = node.child_by_field_name(
            "parameters"
        )

        if parameters_node is None:
            return ()

        return tuple(
            JavaScriptParser._node_text(
                child,
                source,
            )
            for child in parameters_node.named_children
        )

    @staticmethod
    def _looks_like_component(
        name: str,
    ) -> bool:
        """Identify conventional PascalCase React components."""

        return bool(
            name
            and name[0].isupper()
        )

    @staticmethod
    def _is_async(
        node: Node,
    ) -> bool:
        """Determine whether a function is asynchronous."""

        return any(
            child.type == "async"
            for child in node.children
        )

    @staticmethod
    def _node_text(
        node: Node | None,
        source: str,
    ) -> str:
        """Return the exact UTF-8 source text represented by a node."""

        if node is None:
            return ""

        source_bytes = source.encode(
            "utf-8"
        )

        return source_bytes[
            node.start_byte:node.end_byte
        ].decode(
            "utf-8",
            errors="replace",
        )

    @staticmethod
    def _location(
        node: Node,
    ) -> SourceLocation:
        """Convert Tree-sitter coordinates to one-based coordinates."""

        return SourceLocation(
            start_line=node.start_point.row + 1,
            start_column=node.start_point.column + 1,
            end_line=node.end_point.row + 1,
            end_column=node.end_point.column + 1,
        )