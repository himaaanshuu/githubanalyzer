"""
TypeScript/TSX Tree-sitter parser with comprehensive extraction.

Extends JavaScript parser with TypeScript-specific constructs:
interfaces, type aliases, enums, decorators, access modifiers, etc.
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
    ExtractedVariable,
    FileAnalysis,
    ParseResult,
)


class TypeScriptParser(JavaScriptParser):
    """TypeScript and TSX parser using Tree-sitter."""

    @property
    def language_name(self) -> str:
        return "typescript"

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

            elif ntype == "interface_declaration":
                ent = self._extract_interface(node, source)
                if ent:
                    analysis.entities.append(ent)

            elif ntype == "type_alias_declaration":
                ent = self._extract_type_alias(node, source)
                if ent:
                    analysis.entities.append(ent)

            elif ntype == "enum_declaration":
                ent = self._extract_enum(node, source)
                if ent:
                    analysis.entities.append(ent)

            elif ntype == "ambient_declaration":
                # declare function / declare class / declare module
                ent = self._extract_ambient(node, source)
                if ent:
                    analysis.entities.append(ent)

            elif ntype == "expression_statement":
                for child in node.children:
                    if child.type == "assignment_expression":
                        self._extract_module_export(child, source, analysis)

        self._extract_all_calls(result.root, source, analysis)
        return analysis

    # ==================================================================
    # TypeScript-specific Extractions
    # ==================================================================

    def _extract_interface(self, node, source: bytes) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)

        # Extract extends
        extends = []
        for child in node.children:
            if child.type == "extends_clause":
                for iface in child.children:
                    if iface.type == "generic_type" or iface.type == "type_identifier":
                        extends.append(self.get_node_text(iface, source).split("<")[0])

        # Extract methods and properties from body
        methods = []
        for child in node.children:
            if child.type == "interface_body":
                for member in child.children:
                    if member.type == "method_signature":
                        method_name = member.child_by_field_name("name")
                        if method_name:
                            methods.append(self.get_node_text(method_name, source))
                    elif member.type == "property_signature":
                        prop_name = member.child_by_field_name("name")
                        if prop_name:
                            methods.append(self.get_node_text(prop_name, source))

        decorators, decorators_raw = self.extract_decorators(node, source)

        return ExtractedEntity(
            name=name,
            entity_type="interface",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            source=self.get_node_text(node, source),
            implements=extends,
            decorators=decorators,
            decorators_raw=decorators_raw,
        )

    def _extract_type_alias(self, node, source: bytes) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)

        return ExtractedEntity(
            name=name,
            entity_type="type",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            source=self.get_node_text(node, source),
        )

    def _extract_enum(self, node, source: bytes) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)
        is_const = any(c.type == "const" for c in node.children)

        return ExtractedEntity(
            name=name,
            entity_type="enum",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            source=self.get_node_text(node, source),
        )

    def _extract_ambient(self, node, source: bytes) -> ExtractedEntity | None:
        """Extract declare function/class/module statements."""
        for child in node.children:
            if child.type == "function_signature":
                name = child.child_by_field_name("name")
                if name:
                    return ExtractedEntity(
                        name=self.get_node_text(name, source),
                        entity_type="function",
                        start_line=node.start_point[0] + 1,
                        start_column=node.start_point[1],
                        end_line=node.end_point[0] + 1,
                        end_column=node.end_point[1],
                        source=self.get_node_text(node, source),
                    )
            elif child.type == "class_declaration":
                return self._extract_class(child, source)
        return None

    # Override _extract_class to handle TypeScript extends/implements
    def _extract_class(self, node, source: bytes) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)
        decorators, decorators_raw = self.extract_decorators(node, source)
        docstring = self.extract_docstring(node, source)

        parent_class = None
        implements = []

        for child in node.children:
            if child.type == "class_heritage":
                heritage_text = self.get_node_text(child, source)
                if "extends" in heritage_text:
                    extends_part = heritage_text.split("extends")[-1]
                    if "implements" in extends_part:
                        extends_part = extends_part.split("implements")[0]
                    parent_class = extends_part.strip().split("{")[0].strip().split("<")[0].strip()
                if "implements" in heritage_text:
                    impl_part = heritage_text.split("implements")[-1]
                    implements = [i.strip().split("<")[0] for i in impl_part.split(",") if i.strip()]

        # Extract methods with visibility
        for child in node.children:
            if child.type == "class_body":
                for member in child.children:
                    if member.type == "method_definition":
                        method_ent = self._extract_method(member, source)
                        if method_ent:
                            method_ent.parent_class = name
                            method_ent.parent = name
                    elif member.type == "public_field_definition":
                        # TS class property with optional visibility
                        prop_name = member.child_by_field_name("name")
                        if prop_name:
                            pass  # Could extract property info here

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
