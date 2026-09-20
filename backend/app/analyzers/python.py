"""
Python Tree-sitter parser with comprehensive extraction.

Extracts: functions, methods, classes, imports, decorators, variables,
calls, docstrings, type annotations, async functions, and more.
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


class PythonParser(BaseParser):
    """Python parser using Tree-sitter."""

    @property
    def language_name(self) -> str:
        return "python"

    def configure(self) -> None:
        import tree_sitter_python as tspython
        self._set_language(Language(tspython.language()))

    def extract(self, result: ParseResult) -> FileAnalysis:
        source = result.source.encode("utf-8")
        analysis = FileAnalysis(
            file_path=result.file_path,
            language="python",
            has_syntax_errors=result.has_errors,
        )

        for node in self.walk(result.root):
            ntype = node.type

            if ntype == "import_statement":
                imp = self._extract_import(node, source)
                if imp:
                    analysis.imports.append(imp)

            elif ntype == "import_from_statement":
                imp = self._extract_from_import(node, source)
                if imp:
                    analysis.imports.append(imp)

            elif ntype == "function_definition":
                ent = self._extract_function(node, source, analysis)
                if ent:
                    analysis.entities.append(ent)

            elif ntype == "class_definition":
                ent = self._extract_class(node, source, analysis)
                if ent:
                    analysis.entities.append(ent)

            elif ntype == "assignment":
                var = self._extract_assignment(node, source)
                if var:
                    analysis.variables.append(var)

            elif ntype == "augmented_assignment":
                var = self._extract_assignment(node, source)
                if var:
                    analysis.variables.append(var)

        return analysis

    # ==================================================================
    # Import Extraction
    # ==================================================================

    def _extract_import(self, node, source: bytes) -> ExtractedImport | None:
        names = []
        aliases = []
        for child in node.children:
            if child.type == "dotted_name":
                names.append(self.get_node_text(child, source))
            elif child.type == "aliased_import":
                name = child.child_by_field_name("name")
                alias = child.child_by_field_name("alias")
                if name:
                    name_text = self.get_node_text(name, source)
                    names.append(name_text)
                    if alias:
                        aliases.append((name_text, self.get_node_text(alias, source)))

        return ExtractedImport(
            source=names[0] if names else "",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            imported_names=names,
            aliases=aliases,
        )

    def _extract_from_import(self, node, source: bytes) -> ExtractedImport | None:
        module_node = node.child_by_field_name("module_name")
        if not module_node:
            return None
        module_path = self.get_node_text(module_node, source)

        imported_names = []
        aliases = []
        is_wildcard = False

        for child in node.children:
            if child.type == "dotted_name":
                imported_names.append(self.get_node_text(child, source))
            elif child.type == "aliased_import":
                name = child.child_by_field_name("name")
                alias = child.child_by_field_name("alias")
                if name:
                    name_text = self.get_node_text(name, source)
                    imported_names.append(name_text)
                    if alias:
                        aliases.append((name_text, self.get_node_text(alias, source)))
            elif child.type == "wildcard_import":
                is_wildcard = True
                imported_names.append("*")

        return ExtractedImport(
            source=module_path,
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            imported_names=imported_names,
            is_default=False,
            is_namespace=is_wildcard,
            aliases=aliases,
        )

    # ==================================================================
    # Function Extraction
    # ==================================================================

    def _extract_function(self, node, source: bytes, analysis: FileAnalysis | None = None) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)
        params = self._extract_params(node, source)
        decorators, decorators_raw = self.extract_decorators(node, source)
        docstring = self._extract_docstring(node, source)
        return_type = self._extract_return_type(node, source)
        is_async = "async" in self.get_node_text(node, source)[:30]

        ent = ExtractedEntity(
            name=name,
            entity_type="function",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            parameters=params,
            return_type=return_type,
            source=self.get_node_text(node, source),
            is_async=is_async,
            decorators=decorators,
            decorators_raw=decorators_raw,
            docstring=docstring,
        )

        # Extract calls within function body
        if analysis is not None:
            for child in self.walk(node):
                if child.type == "call_expression":
                    call = self._extract_single_call(child, name, source)
                    if call:
                        analysis.calls.append(call)

        return ent

    def _extract_return_type(self, node, source: bytes) -> str | None:
        """Extract return type annotation."""
        for child in node.children:
            if child.type == "type":
                return self.get_node_text(child, source)
            if child.type == "return_type":
                return self.get_node_text(child, source)
        return None

    def _extract_params(self, node, source: bytes) -> list[str]:
        params = []
        for child in node.children:
            if child.type == "parameters":
                for param in child.children:
                    if param.type == "identifier":
                        params.append(self.get_node_text(param, source))
                    elif param.type == "default_parameter":
                        name = param.child_by_field_name("name")
                        if name:
                            params.append(self.get_node_text(name, source))
                    elif param.type == "typed_parameter":
                        name = param.child_by_field_name("name")
                        if name:
                            params.append(self.get_node_text(name, source))
                    elif param.type == "typed_default_parameter":
                        name = param.child_by_field_name("name")
                        if name:
                            params.append(self.get_node_text(name, source))
                    elif param.type == "tuple":
                        params.append(self.get_node_text(param, source))
                    elif param.type == "list_splat_pattern":
                        params.append(self.get_node_text(param, source))
                    elif param.type == "dictionary_splat_pattern":
                        params.append(self.get_node_text(param, source))
                    elif param.type == "positional_separator":
                        pass  # Skip the bare * or / separators
                    elif param.type == "keyword_separator":
                        pass
        return params

    def _extract_docstring(self, node, source: bytes) -> str | None:
        """Extract Python docstring."""
        for child in node.children:
            if child.type == "block":
                for stmt in child.children:
                    if stmt.type == "expression_statement":
                        for expr in stmt.children:
                            if expr.type == "string" or expr.type == "concatenated_string":
                                text = self.get_node_text(expr, source)
                                return text.strip('"\',\n ')
        return None

    # ==================================================================
    # Class Extraction
    # ==================================================================

    def _extract_class(self, node, source: bytes, analysis: FileAnalysis | None = None) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)
        decorators, decorators_raw = self.extract_decorators(node, source)
        docstring = self._extract_docstring(node, source)

        # Extract parent classes and metaclass
        parent_classes = []
        metaclass = None
        for child in node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type == "identifier":
                        parent_classes.append(self.get_node_text(arg, source))
                    elif arg.type == "keyword_argument":
                        key = arg.child_by_field_name("name")
                        if key and self.get_node_text(key, source) == "metaclass":
                            val = arg.child_by_field_name("value")
                            if val:
                                metaclass = self.get_node_text(val, source)

        # Extract class body
        for child in node.children:
            if child.type == "block":
                for method_node in child.children:
                    if method_node.type == "function_definition":
                        method_ent = self._extract_function(method_node, source, analysis)
                        if method_ent:
                            method_ent.entity_type = "method"
                            method_ent.parent_class = name
                            method_ent.parent = name
                            if analysis:
                                analysis.entities.append(method_ent)

        return ExtractedEntity(
            name=name,
            entity_type="class",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            source=self.get_node_text(node, source),
            parent_class=", ".join(parent_classes) if parent_classes else None,
            decorators=decorators,
            decorators_raw=decorators_raw,
            docstring=docstring,
        )

    # ==================================================================
    # Variable / Assignment Extraction
    # ==================================================================

    def _extract_assignment(self, node, source: bytes) -> ExtractedVariable | None:
        targets = node.children
        if not targets:
            return None

        target = targets[0]
        if target.type not in ("identifier", "attribute", "subscript", "tuple", "list"):
            return None

        name = self.get_node_text(target, source)
        if name.startswith("_"):
            return None  # Skip private module-level vars

        value_type = None
        if len(node.children) > 1:
            value = node.children[-1] if node.type == "assignment" else None
            if value:
                if value.type == "string" or value.type == "concatenated_string":
                    value_type = "string"
                elif value.type == "integer" or value.type == "float":
                    value_type = "number"
                elif value.type == "true" or value.type == "false":
                    value_type = "boolean"
                elif value.type == "none":
                    value_type = "none"
                elif value.type == "list":
                    value_type = "list"
                elif value.type == "dictionary":
                    value_type = "dict"
                elif value.type == "identifier":
                    value_type = "reference"
                elif value.type == "call":
                    value_type = "call"
                elif value.type == "lambda":
                    value_type = "function"
                elif value.type == "list_comprehension":
                    value_type = "list"
                elif value.type == "dictionary_comprehension":
                    value_type = "dict"
                elif value.type == "set":
                    value_type = "set"

        is_const = name.isupper()

        return ExtractedVariable(
            name=name,
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            value_type=value_type,
            is_const=is_const,
            source=self.get_node_text(node, source),
        )

    # ==================================================================
    # Call Extraction
    # ==================================================================

    def _extract_single_call(self, node, caller: str, source: bytes) -> ExtractedCall | None:
        func = node.child_by_field_name("function")
        if not func:
            return None
        callee_text = self.get_node_text(func, source)

        if func.type == "attribute":
            # self.method() or module.function()
            value = func.child_by_field_name("value")
            attr = func.child_by_field_name("attribute")
            if value and attr:
                callee_text = f"{self.get_node_text(value, source)}.{self.get_node_text(attr, source)}"

        # Detect await
        is_awaited = False
        parent = node.parent
        if parent and parent.type == "await_expression":
            is_awaited = True

        return ExtractedCall(
            caller=caller,
            callee=callee_text,
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            is_awaited=is_awaited,
        )
