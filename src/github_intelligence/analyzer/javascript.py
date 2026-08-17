"""
JavaScript structural analyzer powered by Tree-sitter.

This module extracts parser-independent structural information from
JavaScript and JSX source code.

Supported entities:
    - Function declarations
    - Function expressions
    - Arrow functions
    - React functional components
    - Classes
    - Class methods

Supported references:
    - ES module imports
    - Named imports
    - Default imports
    - Namespace imports
    - Aliased imports
    - Side-effect imports
    - Export declarations
    - Named exports
    - Default exports
    - Function calls
    - Method calls

Design goals:
    - Parse each source file exactly once.
    - Keep Tree-sitter implementation details inside this module.
    - Return immutable parser-independent models.
    - Normalize imports and calls for downstream graph analysis.
    - Preserve source locations for frontend/code intelligence.
    - Produce deterministic results.

Pipeline:

    source
       |
       v
    Tree-sitter AST
       |
       v
    JavaScriptParser
       |
       v
    parser-independent models
       |
       v
    Knowledge Graph
       |
       v
    Resolver
       |
       v
    Query / RAG / AI
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
    """
    Tree-sitter based JavaScript/JSX structural analyzer.

    Tree-sitter implementation details remain inside this class.
    Higher-level systems receive only parser-independent models.
    """

    # ==================================================================
    # Parser configuration
    # ==================================================================

    @property
    def language_name(self) -> str:
        """Return the supported language name."""

        return "JavaScript"

    def configure(self) -> None:
        """Configure Tree-sitter with the JavaScript grammar."""

        self._parser.language = Language(
            tree_sitter_javascript.language()
        )

    # ==================================================================
    # Public API
    # ==================================================================

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
        Parse and structurally analyze JavaScript source.

        The source is parsed exactly once.

        Returns:
            entities:
                Functions, methods, classes and React components.

            imports:
                Normalized ES module imports.

            exports:
                Normalized export declarations.

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
            root=result.root,
            source=source,
            file_path=file_path,
            entities=entities,
            imports=imports,
            exports=exports,
            calls=calls,
        )

        return (
            tuple(entities),
            tuple(imports),
            tuple(exports),
            tuple(calls),
            result.has_errors,
        )

    # ==================================================================
    # AST traversal
    # ==================================================================

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
        """
        Traverse the Tree-sitter AST iteratively.

        The current lexical scope is propagated to child nodes so that
        function and method calls can be associated with their caller.
        """

        stack: list[
            tuple[Node, str | None]
        ] = [
            (root, None)
        ]

        while stack:
            node, parent_name = stack.pop()

            node_type = node.type

            current_scope = parent_name

            # ----------------------------------------------------------
            # Function declaration
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
                    current_scope = entity.qualified_name

            # ----------------------------------------------------------
            # Function expression
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
                    current_scope = entity.qualified_name

            # ----------------------------------------------------------
            # Arrow function
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
                    current_scope = entity.qualified_name

            # ----------------------------------------------------------
            # Class declaration
            # ----------------------------------------------------------

            elif node_type == "class_declaration":

                entity = self._extract_class(
                    node=node,
                    source=source,
                    file_path=file_path,
                )

                if entity is not None:
                    entities.append(entity)
                    current_scope = entity.qualified_name

            # ----------------------------------------------------------
            # Class method
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
                    current_scope = entity.qualified_name

            # ----------------------------------------------------------
            # Import
            # ----------------------------------------------------------

            elif node_type == "import_statement":

                import_source = (
                    self._extract_import_source(
                        node=node,
                        source=source,
                    )
                )

                imported_names = (
                    self._extract_imported_names(
                        node=node,
                        source=source,
                    )
                )

                if import_source is not None:

                    imports.append(
                        ImportReference(
                            source=import_source,
                            file_path=file_path,
                            location=self._location(node),
                            imported_names=imported_names,
                        )
                    )

            # ----------------------------------------------------------
            # Export
            # ----------------------------------------------------------

            elif node_type == "export_statement":

                export_source = (
                    self._extract_export_source(
                        node=node,
                        source=source,
                    )
                )

                if export_source is not None:

                    exports.append(
                        ExportReference(
                            source=export_source,
                            file_path=file_path,
                            location=self._location(node),
                        )
                    )

            # ----------------------------------------------------------
            # Function / method call
            # ----------------------------------------------------------

            elif node_type == "call_expression":

                call = self._extract_call(
                    node=node,
                    source=source,
                    file_path=file_path,
                    caller=current_scope,
                )

                if call is not None:
                    calls.append(call)

            # ----------------------------------------------------------
            # Preserve source order.
            # ----------------------------------------------------------

            stack.extend(
                (
                    child,
                    current_scope,
                )
                for child in reversed(
                    node.children
                )
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
        ).strip()

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
        """Extract a named or assigned function expression."""

        name_node = node.child_by_field_name(
            "name"
        )

        if name_node is not None:

            name = self._node_text(
                name_node,
                source,
            ).strip()

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

    def _extract_arrow_function(
        self,
        node: Node,
        source: str,
        file_path: Path,
        parent_name: str | None,
    ) -> CodeEntity | None:
        """
        Extract an arrow function.

        PascalCase names are classified as React-style components.
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
        ).strip()

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
    # Import extraction
    # ==================================================================

    @staticmethod
    def _extract_import_source(
        node: Node,
        source: str,
    ) -> str | None:
        """
        Extract the module path from an import statement.

        Examples:

            import React from "react"
                -> react

            import { foo } from "./api.js"
                -> ./api.js

            import * as api from "./api.js"
                -> ./api.js

            import "./styles.css"
                -> ./styles.css
        """

        source_node = node.child_by_field_name(
            "source"
        )

        if source_node is None:
            return None

        value = (
            JavaScriptParser._node_text(
                source_node,
                source,
            )
            .strip()
        )

        value = (
            JavaScriptParser._strip_quotes(
                value
            )
        )

        return value or None

    @staticmethod
    def _extract_imported_names(
        node: Node,
        source: str,
    ) -> tuple[str, ...]:
        """
        Extract names introduced by an import statement.

        Examples:

            import React from "react"
                -> ("React",)

            import { createOrder, getCartTotal } from "./api.js"
                -> ("createOrder", "getCartTotal")

            import { createOrder as placeOrder } from "./api.js"
                -> ("placeOrder",)

            import * as api from "./api.js"
                -> ("api",)

            import "./styles.css"
                -> ()
        """

        names: list[str] = []

        for child in node.named_children:

            # ----------------------------------------------------------
            # import_clause
            # ----------------------------------------------------------

            if child.type != "import_clause":
                continue

            for item in child.named_children:

                # ------------------------------------------------------
                # Default import
                # ------------------------------------------------------

                if item.type == "identifier":

                    name = (
                        JavaScriptParser._node_text(
                            item,
                            source,
                        )
                        .strip()
                    )

                    if name:
                        names.append(name)

                # ------------------------------------------------------
                # Namespace import
                #
                # import * as api from "./api.js"
                # ------------------------------------------------------

                elif item.type == "namespace_import":

                    name_node = (
                        item.child_by_field_name(
                            "name"
                        )
                    )

                    if name_node is not None:

                        name = (
                            JavaScriptParser._node_text(
                                name_node,
                                source,
                            )
                            .strip()
                        )

                        if name:
                            names.append(name)

                # ------------------------------------------------------
                # Named imports
                #
                # import { foo } ...
                #
                # import { foo as bar } ...
                # ------------------------------------------------------

                elif item.type == "named_imports":

                    for named_item in (
                        item.named_children
                    ):

                        imported_name = (
                            named_item.child_by_field_name(
                                "name"
                            )
                        )

                        local_name = (
                            named_item.child_by_field_name(
                                "alias"
                            )
                        )

                        if local_name is not None:

                            name = (
                                JavaScriptParser._node_text(
                                    local_name,
                                    source,
                                )
                                .strip()
                            )

                        elif imported_name is not None:

                            name = (
                                JavaScriptParser._node_text(
                                    imported_name,
                                    source,
                                )
                                .strip()
                            )

                        else:
                            name = ""

                        if name:
                            names.append(name)

        return tuple(
            dict.fromkeys(names)
        )

    # ==================================================================
    # Export extraction
    # ==================================================================

    @staticmethod
    def _extract_export_source(
        node: Node,
        source: str,
    ) -> str | None:
        """
        Extract a normalized export representation.

        Examples:

            export default OrderPage
                -> default OrderPage

            export default function foo() {}
                -> default foo

            export function createOrder() {}
                -> createOrder

            export { createOrder, getCartTotal }
                -> createOrder, getCartTotal

            export { foo as bar }
                -> bar
        """

        text = (
            JavaScriptParser._node_text(
                node,
                source,
            )
            .strip()
        )

        if not text:
            return None

        # --------------------------------------------------------------
        # export default
        # --------------------------------------------------------------

        if text.startswith(
            "export default"
        ):

            remainder = (
                text[
                    len("export default"):
                ]
                .strip()
            )

            # export default function foo() {}
            if remainder.startswith(
                "function"
            ):

                parts = remainder.split(
                    None,
                    2,
                )

                if len(parts) >= 2:
                    name = (
                        parts[1]
                        .split("(")[0]
                        .strip()
                    )

                    if name:
                        return (
                            f"default {name}"
                        )

                return "default"

            # export default class Foo {}
            if remainder.startswith(
                "class"
            ):

                parts = remainder.split(
                    None,
                    2,
                )

                if len(parts) >= 2:

                    name = (
                        parts[1]
                        .split("{")[0]
                        .strip()
                    )

                    if name:
                        return (
                            f"default {name}"
                        )

                return "default"

            # export default Foo
            name = (
                remainder
                .rstrip(";")
                .strip()
            )

            if name:
                return (
                    f"default {name}"
                )

            return "default"

        # --------------------------------------------------------------
        # export { ... }
        # --------------------------------------------------------------

        if text.startswith(
            "export {"
        ):

            start = text.find("{")
            end = text.rfind("}")

            if (
                start != -1
                and end != -1
                and end > start
            ):

                content = text[
                    start + 1:end
                ]

                exported_names: list[str] = []

                for item in content.split(","):

                    item = item.strip()

                    if not item:
                        continue

                    if " as " in item:

                        parts = item.split(
                            " as "
                        )

                        exported_name = (
                            parts[-1].strip()
                        )

                    else:

                        exported_name = item

                    if exported_name:
                        exported_names.append(
                            exported_name
                        )

                if exported_names:
                    return ",".join(
                        exported_names
                    )

                return "named"

        # --------------------------------------------------------------
        # export function foo()
        # --------------------------------------------------------------

        if text.startswith(
            "export function"
        ):

            remainder = (
                text[
                    len("export function"):
                ]
                .strip()
            )

            name = (
                remainder
                .split("(")[0]
                .strip()
            )

            return name or None

        # --------------------------------------------------------------
        # export async function foo()
        # --------------------------------------------------------------

        if text.startswith(
            "export async function"
        ):

            remainder = (
                text[
                    len(
                        "export async function"
                    ):
                ]
                .strip()
            )

            name = (
                remainder
                .split("(")[0]
                .strip()
            )

            return name or None

        # --------------------------------------------------------------
        # export class Foo
        # --------------------------------------------------------------

        if text.startswith(
            "export class"
        ):

            remainder = (
                text[
                    len("export class"):
                ]
                .strip()
            )

            name = (
                remainder
                .split("{")[0]
                .strip()
            )

            return name or None

        # --------------------------------------------------------------
        # export const foo = ...
        # export let foo = ...
        # export var foo = ...
        # --------------------------------------------------------------

        for keyword in (
            "export const",
            "export let",
            "export var",
        ):

            if text.startswith(keyword):

                remainder = (
                    text[len(keyword):]
                    .strip()
                )

                name = (
                    remainder
                    .split("=")[0]
                    .strip()
                )

                if name:
                    return name

        return text

    # ==================================================================
    # Calls
    # ==================================================================

    def _extract_call(
        self,
        node: Node,
        source: str,
        file_path: Path,
        caller: str | None,
    ) -> CallReference | None:
        """Extract a normalized function or method call."""

        function_node = node.child_by_field_name(
            "function"
        )

        if function_node is None:
            return None

        callee = self._extract_callee_name(
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

    @staticmethod
    def _extract_callee_name(
        node: Node,
        source: str,
    ) -> str | None:
        """
        Extract a concise callable name.

        Supported examples:

            foo()
                -> foo

            api.createOrder()
                -> api.createOrder

            mongoose.connect()
                -> mongoose.connect

            foo().then()
                -> then

            document.cookie.split()
                -> document.cookie.split
        """

        node_type = node.type

        # --------------------------------------------------------------
        # Identifier
        # --------------------------------------------------------------

        if node_type == "identifier":

            value = (
                JavaScriptParser._node_text(
                    node,
                    source,
                )
                .strip()
            )

            return value or None

        # --------------------------------------------------------------
        # Member expression
        # --------------------------------------------------------------

        if node_type == "member_expression":

            property_node = (
                node.child_by_field_name(
                    "property"
                )
            )

            object_node = (
                node.child_by_field_name(
                    "object"
                )
            )

            if property_node is None:
                return None

            property_name = (
                JavaScriptParser._node_text(
                    property_node,
                    source,
                )
                .strip()
            )

            if not property_name:
                return None

            if object_node is None:
                return property_name

            object_name = (
                JavaScriptParser._extract_callee_name(
                    object_node,
                    source,
                )
            )

            if object_name:
                return (
                    f"{object_name}."
                    f"{property_name}"
                )

            return property_name

        # --------------------------------------------------------------
        # Nested call expression
        # --------------------------------------------------------------

        if node_type == "call_expression":

            nested_function = (
                node.child_by_field_name(
                    "function"
                )
            )

            if nested_function is None:
                return None

            return (
                JavaScriptParser._extract_callee_name(
                    nested_function,
                    source,
                )
            )

        # --------------------------------------------------------------
        # Optional chaining
        # --------------------------------------------------------------

        if node_type == "optional_chain":

            named_children = (
                node.named_children
            )

            if not named_children:
                return None

            return (
                JavaScriptParser._extract_callee_name(
                    named_children[-1],
                    source,
                )
            )

        return None

    # ==================================================================
    # Function helpers
    # ==================================================================

    @staticmethod
    def _assigned_function_name(
        node: Node,
        source: str,
    ) -> str | None:
        """
        Determine the name assigned to an anonymous function.

        Supports:

            const login = () => {};

            const login = function () {};

            const api = {
                login: () => {}
            };
        """

        parent = node.parent

        if parent is None:
            return None

        # --------------------------------------------------------------
        # Variable declaration
        # --------------------------------------------------------------

        if parent.type == "variable_declarator":

            name_node = (
                parent.child_by_field_name(
                    "name"
                )
            )

            if name_node is not None:

                value = (
                    JavaScriptParser._node_text(
                        name_node,
                        source,
                    )
                    .strip()
                )

                return value or None

        # --------------------------------------------------------------
        # Object property
        # --------------------------------------------------------------

        if parent.type == "pair":

            key_node = (
                parent.child_by_field_name(
                    "key"
                )
            )

            if key_node is not None:

                value = (
                    JavaScriptParser._node_text(
                        key_node,
                        source,
                    )
                    .strip()
                )

                return value or None

        return None

    @staticmethod
    def _extract_parameters(
        node: Node,
        source: str,
    ) -> tuple[str, ...]:
        """Extract function parameter source text."""

        parameters_node = (
            node.child_by_field_name(
                "parameters"
            )
        )

        if parameters_node is None:
            return ()

        parameters: list[str] = []

        for child in parameters_node.named_children:

            value = (
                JavaScriptParser._node_text(
                    child,
                    source,
                )
                .strip()
            )

            if value:
                parameters.append(value)

        return tuple(parameters)

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

    # ==================================================================
    # Source helpers
    # ==================================================================

    @staticmethod
    def _strip_quotes(
        value: str,
    ) -> str:
        """Remove JavaScript string delimiters."""

        if len(value) < 2:
            return value

        if (
            value[0]
            in {"'", '"', "`"}
            and value[-1]
            == value[0]
        ):
            return value[1:-1]

        return value

    @staticmethod
    def _node_text(
        node: Node | None,
        source: str,
    ) -> str:
        """Return exact UTF-8 source text represented by a node."""

        if node is None:
            return ""

        source_bytes = source.encode(
            "utf-8"
        )

        return (
            source_bytes[
                node.start_byte:node.end_byte
            ]
            .decode(
                "utf-8",
                errors="replace",
            )
        )

    @staticmethod
    def _location(
        node: Node,
    ) -> SourceLocation:
        """Convert Tree-sitter coordinates to one-based coordinates."""

        return SourceLocation(
            start_line=(
                node.start_point.row + 1
            ),
            start_column=(
                node.start_point.column + 1
            ),
            end_line=(
                node.end_point.row + 1
            ),
            end_column=(
                node.end_point.column + 1
            ),
        )