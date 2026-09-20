"""
TypeScript/TSX Tree-sitter parser.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Language

from .javascript import JavaScriptParser
from .base import (
    ExtractedCall,
    ExtractedEntity,
    ExtractedExport,
    ExtractedImport,
    FileAnalysis,
    ParseResult,
)


class TypeScriptParser(JavaScriptParser):
    """TypeScript and TSX parser using Tree-sitter."""

    @property
    def language_name(self) -> str:
        return "typescriptcript"

    def configure(self) -> None:
        import tree_sitter_typescript as tsjs
        self._set_language(Language(tsjs.language_typescript()))

    def extract(self, result: ParseResult) -> FileAnalysis:
        source = result.source.encode("utf-8")
        analysis = FileAnalysis(
            file_path=result.file_path,
            language="typescript",
            has_syntax_errors=result.has_errors,
        )

        for node in self.walk(result.root):
            if node.type == "import_statement":
                imp = self._extract_import(node, source, result.file_path)
                if imp:
                    analysis.imports.append(imp)

            elif node.type in ("export_statement",):
                exp = self._extract_export(node, source, result.file_path)
                if exp:
                    analysis.exports.append(exp)

            elif node.type == "function_declaration":
                ent = self._extract_function(node, source, result.file_path)
                if ent:
                    analysis.entities.append(ent)
                    self._extract_calls_from_body(node, ent.name, source, result.file_path, analysis)

            elif node.type == "lexical_declaration":
                for child in node.children:
                    if child.type == "variable_declarator":
                        ent = self._extract_variable_function(child, node, source, result.file_path)
                        if ent:
                            analysis.entities.append(ent)
                            self._extract_calls_from_body(child, ent.name, source, result.file_path, analysis)

            elif node.type == "class_declaration":
                ent = self._extract_class(node, source, result.file_path)
                if ent:
                    analysis.entities.append(ent)

            elif node.type == "method_definition":
                ent = self._extract_method(node, source, result.file_path)
                if ent:
                    analysis.entities.append(ent)
                    self._extract_calls_from_body(node, ent.name, source, result.file_path, analysis)

            elif node.type == "interface_declaration":
                ent = self._extract_interface(node, source, result.file_path)
                if ent:
                    analysis.entities.append(ent)

            elif node.type == "type_alias_declaration":
                ent = self._extract_type_alias(node, source, result.file_path)
                if ent:
                    analysis.entities.append(ent)

            elif node.type == "arrow_function":
                parent = node.parent
                if parent and parent.type == "variable_declarator":
                    ent = self._extract_variable_function(parent, parent.parent, source, result.file_path)
                    if ent:
                        analysis.entities.append(ent)

        return analysis

    def _extract_interface(self, node, source: bytes, file_path: Path) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)
        return ExtractedEntity(
            name=name,
            entity_type="class",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            source=self.get_node_text(node, source),
        )

    def _extract_type_alias(self, node, source: bytes, file_path: Path) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)
        return ExtractedEntity(
            name=name,
            entity_type="variable",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            source=self.get_node_text(node, source),
        )
