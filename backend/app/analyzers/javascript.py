"""
JavaScript/JSX Tree-sitter parser with comprehensive extraction.

Extracts: functions, methods, classes, imports (ALL), exports, calls,
variables, decorators, class inheritance, and more.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Language

from .base import (
    BaseParser,
    ExtractedCall,
    ExtractedDecorator,
    ExtractedEntity,
    ExtractedExport,
    ExtractedImport,
    ExtractedVariable,
    FileAnalysis,
    ParseResult,
)


class JavaScriptParser(BaseParser):
    """JavaScript and JSX parser using Tree-sitter."""

    @property
    def language_name(self) -> str:
        return "javascript"

    def configure(self) -> None:
        import tree_sitter_javascript as tsjs
        self._set_language(Language(tsjs.language()))

    def extract(self, result: ParseResult) -> FileAnalysis:
        source = result.source.encode("utf-8")
        analysis = FileAnalysis(
            file_path=result.file_path,
            language="javascript",
            has_syntax_errors=result.has_errors,
        )

        # Track current function scope for call extraction
        current_function: str | None = None

        for node in self.walk(result.root):
            ntype = node.type

            if ntype == "import_statement":
                imp = self._extract_import(node, source, result.file_path)
                if imp:
                    analysis.imports.append(imp)

            elif ntype == "export_statement":
                exp = self._extract_export(node, source, result.file_path)
                if exp:
                    analysis.exports.append(exp)

            elif ntype == "function_declaration":
                ent = self._extract_function(node, source)
                if ent:
                    analysis.entities.append(ent)
                    self._extract_calls_in_body(node, ent.name, source, analysis)

            elif ntype == "lexical_declaration":
                for child in node.children:
                    if child.type == "variable_declarator":
                        val = child.child_by_field_name("value")
                        if val and val.type in ("arrow_function", "function"):
                            ent = self._extract_variable_function(child, node, source)
                            if ent:
                                analysis.entities.append(ent)
                                self._extract_calls_in_body(val, ent.name, source, analysis)
                        else:
                            var = self._extract_variable(child, node, source)
                            if var:
                                analysis.variables.append(var)

            elif ntype == "variable_declaration":
                for child in node.children:
                    if child.type == "variable_declarator":
                        val = child.child_by_field_name("value")
                        if val and val.type in ("arrow_function", "function"):
                            ent = self._extract_variable_function(child, node, source)
                            if ent:
                                analysis.entities.append(ent)
                                self._extract_calls_in_body(val, ent.name, source, analysis)
                        else:
                            var = self._extract_variable(child, node, source)
                            if var:
                                analysis.variables.append(var)

            elif ntype == "class_declaration":
                ent = self._extract_class(node, source)
                if ent:
                    analysis.entities.append(ent)

            elif ntype == "method_definition":
                ent = self._extract_method(node, source)
                if ent:
                    analysis.entities.append(ent)
                    self._extract_calls_in_body(node, ent.name, source, analysis)

            elif ntype == "export_statement":
                # Already handled above
                pass

            elif ntype == "expression_statement":
                # Handle module.exports = ... and exports.X = ...
                for child in node.children:
                    if child.type == "assignment_expression":
                        self._extract_module_export(child, source, analysis)

        # Extract all function/method calls at file level (not scoped to a function)
        self._extract_all_calls(result.root, source, analysis)

        return analysis

    # ==================================================================
    # Import Extraction
    # ==================================================================

    def _extract_import(self, node, source: bytes, file_path: Path) -> ExtractedImport | None:
        module_node = node.child_by_field_name("source")
        if not module_node:
            return None
        module_path = self.get_node_text(module_node, source).strip("'\"")

        imported_names = []
        is_default = False
        is_namespace = False
        is_type_only = False
        aliases = []

        # Check for 'import type' (TypeScript)
        if self.get_node_text(node, source).startswith("import type"):
            is_type_only = True

        for child in node.children:
            if child.type == "identifier":
                # import React from "react"
                imported_names.append(self.get_node_text(child, source))
                is_default = True

            elif child.type == "namespace_import":
                # import * as X from "..."
                is_namespace = True
                imported_names.append("*")

            elif child.type == "import_clause":
                for sub in child.children:
                    if sub.type == "identifier":
                        imported_names.append(self.get_node_text(sub, source))
                        is_default = True
                    elif sub.type == "named_imports":
                        for spec in sub.children:
                            if spec.type == "import_specifier":
                                name_node = spec.child_by_field_name("name")
                                alias_node = spec.child_by_field_name("alias")
                                if name_node:
                                    imported_name = self.get_node_text(name_node, source)
                                    imported_names.append(imported_name)
                                    if alias_node:
                                        alias = self.get_node_text(alias_node, source)
                                        aliases.append((imported_name, alias))

        return ExtractedImport(
            source=module_path,
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            imported_names=imported_names,
            is_default=is_default,
            is_namespace=is_namespace,
            is_type_only=is_type_only,
            aliases=aliases,
        )

    # ==================================================================
    # Export Extraction
    # ==================================================================

    def _extract_export(self, node, source: bytes, file_path: Path) -> ExtractedExport | None:
        text = self.get_node_text(node, source)
        is_default = "default" in text.split("{")[0]
        exported_names = []
        export_source = ""
        reexport_source = None

        for child in node.children:
            if child.type == "declaration":
                if child.type == "function_declaration":
                    name = child.child_by_field_name("name")
                    if name:
                        exported_names.append(self.get_node_text(name, source))
                elif child.type == "class_declaration":
                    name = child.child_by_field_name("name")
                    if name:
                        exported_names.append(self.get_node_text(name, source))
                elif child.type in ("lexical_declaration", "variable_declaration"):
                    for vc in child.children:
                        if vc.type == "variable_declarator":
                            name = vc.child_by_field_name("name")
                            if name:
                                exported_names.append(self.get_node_text(name, source))

            elif child.type == "export_clause":
                # export { A, B as C }
                for spec in child.children:
                    if spec.type == "export_specifier":
                        name_node = spec.child_by_field_name("name")
                        if name_node:
                            exported_names.append(self.get_node_text(name_node, source))

            elif child.type == "sequence_expression":
                # export { A } from "./other"
                for expr in child.children:
                    if expr.type == "export_clause":
                        for spec in expr.children:
                            if spec.type == "export_specifier":
                                name_node = spec.child_by_field_name("name")
                                if name_node:
                                    exported_names.append(self.get_node_text(name_node, source))
                    elif expr.type == "string":
                        reexport_source = self.get_node_text(expr, source).strip("'\"")

        # Handle: export default function/class/identifier
        if not exported_names:
            for child in node.children:
                if child.type == "identifier":
                    exported_names.append(self.get_node_text(child, source))

        # Extract re-export source from the full text
        if "from" in text and reexport_source is None:
            from_idx = text.rfind("from")
            if from_idx > 0:
                reexport_source = text[from_idx + 4:].strip().strip("'\"").rstrip(";")

        return ExtractedExport(
            source=export_source or (exported_names[0] if exported_names else ""),
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            exported_names=exported_names,
            is_default=is_default,
            reexport_source=reexport_source,
        )

    # ==================================================================
    # Function Extraction
    # ==================================================================

    def _extract_function(self, node, source: bytes) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)
        params = self._extract_params(node, source)
        decorators, decorators_raw = self.extract_decorators(node, source)
        is_async = "async" in self.get_node_text(node, source)[:30]
        is_generator = any(c.type == "*" for c in node.children)
        docstring = self.extract_docstring(node, source)

        return ExtractedEntity(
            name=name,
            entity_type="function",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            parameters=params,
            source=self.get_node_text(node, source),
            is_async=is_async,
            is_generator=is_generator,
            decorators=decorators,
            decorators_raw=decorators_raw,
            docstring=docstring,
        )

    def _extract_variable_function(self, declarator, parent, source: bytes) -> ExtractedEntity | None:
        name_node = declarator.child_by_field_name("name")
        value_node = declarator.child_by_field_name("value")
        if not name_node or not value_node:
            return None
        if value_node.type not in ("arrow_function", "function"):
            return None
        name = self.get_node_text(name_node, source)
        params = self._extract_params(value_node, source)
        is_async = False
        if parent:
            is_async = "async" in self.get_node_text(parent, source)[:30]
        decorators, decorators_raw = self.extract_decorators(declarator, source)

        return ExtractedEntity(
            name=name,
            entity_type="function",
            start_line=declarator.start_point[0] + 1,
            start_column=declarator.start_point[1],
            end_line=declarator.end_point[0] + 1,
            end_column=declarator.end_point[1],
            parameters=params,
            source=self.get_node_text(declarator, source),
            is_async=is_async,
            decorators=decorators,
            decorators_raw=decorators_raw,
        )

    # ==================================================================
    # Class Extraction
    # ==================================================================

    def _extract_class(self, node, source: bytes) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)
        decorators, decorators_raw = self.extract_decorators(node, source)
        docstring = self.extract_docstring(node, source)

        # Extract parent class and implemented interfaces
        parent_class = None
        implements = []
        for child in node.children:
            if child.type == "class_heritage":
                heritage_text = self.get_node_text(child, source)
                # extends X
                if "extends" in heritage_text:
                    extends_part = heritage_text.split("extends")[-1]
                    if "implements" in extends_part:
                        extends_part = extends_part.split("implements")[0]
                    parent_class = extends_part.strip().split("{")[0].strip().split("(")[0].strip()
                # implements X, Y
                if "implements" in heritage_text:
                    impl_part = heritage_text.split("implements")[-1]
                    implements = [i.strip() for i in impl_part.split(",") if i.strip()]

        # Extract methods and properties from the class body
        methods = []
        for child in node.children:
            if child.type == "class_body":
                for member in child.children:
                    if member.type == "method_definition":
                        method_ent = self._extract_method(member, source)
                        if method_ent:
                            method_ent.parent_class = name
                            methods.append(method_ent)
                    elif member.type == "field_definition":
                        # Class property
                        prop_name = member.child_by_field_name("property")
                        if prop_name:
                            prop_text = self.get_node_text(prop_name, source)
                            methods.append(ExtractedEntity(
                                name=prop_text,
                                entity_type="variable",
                                start_line=member.start_point[0] + 1,
                                start_column=member.start_point[1],
                                end_line=member.end_point[0] + 1,
                                end_column=member.end_point[1],
                                parent_class=name,
                            ))

        return ExtractedEntity(
            name=name,
            entity_type="class",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            source=self.get_node_text(node, source),
            parent_class=parent_class,
            implements=implements,
            decorators=decorators,
            decorators_raw=decorators_raw,
            docstring=docstring,
        )

    def _extract_method(self, node, source: bytes) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)
        params = self._extract_params(node, source)
        decorators, decorators_raw = self.extract_decorators(node, source)
        is_async = "async" in self.get_node_text(node, source)[:30]
        is_generator = any(c.type == "*" for c in node.children)
        docstring = self.extract_docstring(node, source)

        # Detect visibility
        visibility = None
        for child in node.children:
            if child.type == "#private_property_identifier":
                visibility = "private"
                break

        # Detect static
        is_static = any(c.type == "static" for c in node.children)

        parent_class = None
        p = node.parent
        while p:
            if p.type == "class_declaration":
                pname = p.child_by_field_name("name")
                if pname:
                    parent_class = self.get_node_text(pname, source)
                break
            p = p.parent

        return ExtractedEntity(
            name=name,
            entity_type="method",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            parent=parent_class,
            parent_class=parent_class,
            parameters=params,
            source=self.get_node_text(node, source),
            is_async=is_async,
            is_generator=is_generator,
            decorators=decorators,
            decorators_raw=decorators_raw,
            docstring=docstring,
            visibility=visibility,
        )

    # ==================================================================
    # Variable Extraction
    # ==================================================================

    def _extract_variable(self, declarator, parent, source: bytes) -> ExtractedVariable | None:
        name_node = declarator.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)
        value_node = declarator.child_by_field_name("value")

        value_type = None
        if value_node:
            if value_node.type == "string":
                value_type = "string"
            elif value_node.type == "number":
                value_type = "number"
            elif value_node.type == "true" or value_node.type == "false":
                value_type = "boolean"
            elif value_node.type == "null":
                value_type = "null"
            elif value_node.type == "array":
                value_type = "array"
            elif value_node.type == "object":
                value_type = "object"
            elif value_node.type == "identifier":
                value_type = "reference"
            elif value_node.type == "call_expression":
                value_type = "call"
            elif value_node.type == "arrow_function" or value_node.type == "function":
                value_type = "function"

        is_const = parent is not None and parent.type == "lexical_declaration" and "const" in self.get_node_text(parent, source)[:10]

        return ExtractedVariable(
            name=name,
            start_line=declarator.start_point[0] + 1,
            start_column=declarator.start_point[1],
            end_line=declarator.end_point[0] + 1,
            end_column=declarator.end_point[1],
            value_type=value_type,
            is_const=is_const,
            source=self.get_node_text(declarator, source),
        )

    # ==================================================================
    # Module Exports (CommonJS)
    # ==================================================================

    def _extract_module_export(self, node, source: bytes, analysis: FileAnalysis) -> None:
        left = node.child_by_field_name("left")
        if left:
            text = self.get_node_text(left, source)
            if text.startswith("module.exports") or text.startswith("exports."):
                export_name = text.split(".")[-1] if "." in text else "default"
                analysis.exports.append(ExtractedExport(
                    source=export_name,
                    start_line=node.start_point[0] + 1,
                    start_column=node.start_point[1],
                    end_line=node.end_point[0] + 1,
                    end_column=node.end_point[1],
                    exported_names=[export_name],
                    is_default=export_name == "default",
                ))

    # ==================================================================
    # Parameter Extraction
    # ==================================================================

    def _extract_params(self, node, source: bytes) -> list[str]:
        params = []
        for child in node.children:
            if child.type == "formal_parameters":
                for param in child.children:
                    if param.type == "identifier":
                        params.append(self.get_node_text(param, source))
                    elif param.type == "required_parameter":
                        name = param.child_by_field_name("pattern")
                        if name:
                            params.append(self.get_node_text(name, source))
                    elif param.type == "optional_parameter":
                        name = param.child_by_field_name("pattern")
                        if name:
                            params.append(self.get_node_text(name, source))
                    elif param.type == "rest_pattern":
                        params.append("..." + self.get_node_text(param, source).lstrip("..."))
                    elif param.type == "object_pattern":
                        # Destructuring: { a, b } = params
                        params.append(self.get_node_text(param, source))
                    elif param.type == "array_pattern":
                        params.append(self.get_node_text(param, source))
        return params

    # ==================================================================
    # Call Extraction
    # ==================================================================

    def _extract_calls_in_body(self, node, caller_name: str, source: bytes, analysis: FileAnalysis):
        """Extract function calls within a node's body."""
        for child in self.walk(node):
            if child.type == "call_expression":
                call = self._extract_single_call(child, caller_name, source)
                if call:
                    analysis.calls.append(call)

    def _extract_all_calls(self, root, source: bytes, analysis: FileAnalysis):
        """Extract all top-level function calls (not scoped to a function)."""
        for node in self.walk(root):
            if node.type == "call_expression":
                # Find the enclosing function if any
                enclosing = self._find_enclosing_function(node)
                caller = enclosing if enclosing else "__module__"
                call = self._extract_single_call(node, caller, source)
                if call:
                    # Avoid duplicates if already extracted in _extract_calls_in_body
                    existing = any(
                        c.start_line == call.start_line and c.callee == call.callee
                        for c in analysis.calls
                    )
                    if not existing:
                        analysis.calls.append(call)

    def _extract_single_call(self, node, caller: str, source: bytes) -> ExtractedCall | None:
        func = node.child_by_field_name("function")
        if not func:
            return None
        callee_text = self.get_node_text(func, source)

        # For method calls like obj.method(), extract the full chain
        if func.type == "member_expression":
            object_node = func.child_by_field_name("object")
            property_node = func.child_by_field_name("property")
            if object_node and property_node:
                obj_name = self.get_node_text(object_node, source)
                prop_name = self.get_node_text(property_node, source)
                callee_text = f"{obj_name}.{prop_name}"
            else:
                callee_text = self.get_node_text(func, source)

        # Detect await
        is_awaited = False
        parent = node.parent
        if parent and parent.type == "await_expression":
            is_awaited = True

        # Detect chaining
        is_chained = False
        if parent and parent.type == "member_expression":
            is_chained = True

        # Extract argument count
        args_node = node.child_by_field_name("arguments")
        arg_count = 0
        if args_node:
            arg_count = len([c for c in args_node.children if c.type != "," and c.type != "(" and c.type != ")"])

        return ExtractedCall(
            caller=caller,
            callee=callee_text,
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            is_awaited=is_awaited,
            is_chained=is_chained,
        )

    def _find_enclosing_function(self, node) -> str | None:
        """Find the name of the enclosing function/method."""
        parent = node.parent
        while parent:
            if parent.type == "function_declaration":
                name = parent.child_by_field_name("name")
                if name:
                    return self.get_node_text(name, parent._source if hasattr(parent, '_source') else b'')
            elif parent.type == "method_definition":
                name = parent.child_by_field_name("name")
                if name:
                    return self.get_node_text(name, b'')
            elif parent.type in ("arrow_function", "function"):
                # Anonymous function assigned to variable
                p = parent.parent
                if p and p.type == "variable_declarator":
                    name = p.child_by_field_name("name")
                    if name:
                        return self.get_node_text(name, b'')
            parent = parent.parent
        return None
