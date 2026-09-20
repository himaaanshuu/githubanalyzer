"""
Python Tree-sitter parser.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Language

from .base import (
    BaseParser,
    ExtractedCall,
    ExtractedEntity,
    ExtractedExport,
    ExtractedImport,
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
            if node.type == "import_statement":
                imp = self._extract_import(node, source)
                if imp:
                    analysis.imports.append(imp)

            elif node.type == "import_from_statement":
                imp = self._extract_from_import(node, source)
                if imp:
                    analysis.imports.append(imp)

            elif node.type == "function_definition":
                ent = self._extract_function(node, source, analysis)
                if ent:
                    analysis.entities.append(ent)

            elif node.type == "class_definition":
                ent = self._extract_class(node, source)
                if ent:
                    analysis.entities.append(ent)

        return analysis

    def _extract_import(self, node, source: bytes) -> ExtractedImport | None:
        names = []
        for child in node.children:
            if child.type == "dotted_name":
                names.append(self.get_node_text(child, source))
            elif child.type == "aliased_import":
                name = child.child_by_field_name("name")
                alias = child.child_by_field_name("alias")
                if name:
                    names.append(self.get_node_text(name, source))

        return ExtractedImport(
            source=names[0] if names else "",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            imported_names=names,
        )

    def _extract_from_import(self, node, source: bytes) -> ExtractedImport | None:
        module_node = node.child_by_field_name("module_name")
        if not module_node:
            return None
        module_path = self.get_node_text(module_node, source)

        imported_names = []
        for child in node.children:
            if child.type == "dotted_name":
                imported_names.append(self.get_node_text(child, source))
            elif child.type == "aliased_import":
                name = child.child_by_field_name("name")
                if name:
                    imported_names.append(self.get_node_text(name, source))

        return ExtractedImport(
            source=module_path,
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            imported_names=imported_names,
        )

    def _extract_function(self, node, source: bytes, analysis: FileAnalysis) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)
        params = self._extract_params(node, source)
        ent = ExtractedEntity(
            name=name,
            entity_type="function",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            parameters=params,
            source=self.get_node_text(node, source),
        )

        # Extract calls within function body
        for child in self.walk(node):
            if child.type == "call_expression":
                func = child.child_by_field_name("function")
                if func:
                    callee = self.get_node_text(func, source)
                    if "." in callee:
                        callee = callee.split(".")[-1]
                    analysis.calls.append(ExtractedCall(
                        caller=name,
                        callee=callee,
                        start_line=child.start_point[0] + 1,
                        start_column=child.start_point[1],
                        end_line=child.end_point[0] + 1,
                        end_column=child.end_point[1],
                    ))

        return ent

    def _extract_class(self, node, source: bytes) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)

        # Extract methods
        for child in node.children:
            if child.type == "block":
                for method_node in child.children:
                    if method_node.type == "function_definition":
                        method_ent = self._extract_function(method_node, source, None)
                        if method_ent:
                            method_ent.entity_type = "method"
                            method_ent.parent = name
                            # We'll add methods to the class's source
                            # but they are separate entities

        return ExtractedEntity(
            name=name,
            entity_type="class",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            source=self.get_node_text(node, source),
        )

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
        return params
