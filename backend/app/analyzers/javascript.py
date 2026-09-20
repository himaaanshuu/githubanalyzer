"""
JavaScript/JSX Tree-sitter parser.
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

            elif node.type == "arrow_function":
                parent = node.parent
                if parent and parent.type == "variable_declarator":
                    ent = self._extract_variable_function(parent, parent.parent, source, result.file_path)
                    if ent:
                        analysis.entities.append(ent)

        return analysis

    def _extract_import(self, node, source: bytes, file_path: Path) -> ExtractedImport | None:
        module_node = node.child_by_field_name("source")
        if not module_node:
            return None
        module_path = self.get_node_text(module_node, source).strip("'\"")
        if module_path.startswith("."):
            imported_names = []
            is_default = False
            is_namespace = False

            for child in node.children:
                if child.type == "identifier":
                    imported_names.append(self.get_node_text(child, source))
                    is_default = True
                elif child.type == "namespace_import":
                    is_namespace = True
                    imported_names.append("*")
                elif child.type == "import_clause":
                    for sub in child.children:
                        if sub.type == "identifier":
                            imported_names.append(self.get_node_text(sub, source))
                            is_default = True
                        elif sub.type == "named_imports":
                            for imp in sub.children:
                                if imp.type == "import_specifier":
                                    name_node = imp.child_by_field_name("name") or imp.child_by_field_name("alias")
                                    if name_node:
                                        imported_names.append(self.get_node_text(name_node, source))

            return ExtractedImport(
                source=module_path,
                start_line=node.start_point[0] + 1,
                start_column=node.start_point[1],
                end_line=node.end_point[0] + 1,
                end_column=node.end_point[1],
                imported_names=imported_names,
                is_default=is_default,
                is_namespace=is_namespace,
            )
        return None

    def _extract_export(self, node, source: bytes, file_path: Path) -> ExtractedExport | None:
        is_default = "default" in self.get_node_text(node, source)
        exported_names = []
        export_source = ""

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
                elif child.type == "lexical_declaration":
                    for vc in child.children:
                        if vc.type == "variable_declarator":
                            name = vc.child_by_field_name("name")
                            if name:
                                exported_names.append(self.get_node_text(name, source))

        if not exported_names:
            text = self.get_node_text(node, source)
            if "export default" in text:
                parts = text.split("export default", 1)
                if len(parts) > 1:
                    export_source = parts[1].strip().rstrip(";")
                    is_default = True

        return ExtractedExport(
            source=export_source or (exported_names[0] if exported_names else ""),
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            exported_names=exported_names,
            is_default=is_default,
        )

    def _extract_function(self, node, source: bytes, file_path: Path) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)
        params = self._extract_params(node, source)
        return ExtractedEntity(
            name=name,
            entity_type="function",
            start_line=node.start_point[0] + 1,
            start_column=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1],
            parameters=params,
            source=self.get_node_text(node, source),
            is_async="async" in self.get_node_text(node, source)[:20],
        )

    def _extract_variable_function(self, declarator, parent, source: bytes, file_path: Path) -> ExtractedEntity | None:
        name_node = declarator.child_by_field_name("name")
        value_node = declarator.child_by_field_name("value")
        if not name_node or not value_node:
            return None
        if value_node.type not in ("arrow_function", "function"):
            return None
        name = self.get_node_text(name_node, source)
        params = self._extract_params(value_node, source)
        return ExtractedEntity(
            name=name,
            entity_type="function",
            start_line=declarator.start_point[0] + 1,
            start_column=declarator.start_point[1],
            end_line=declarator.end_point[0] + 1,
            end_column=declarator.end_point[1],
            parameters=params,
            source=self.get_node_text(declarator, source),
            is_async="async" in self.get_node_text(parent, source)[:30] if parent else False,
        )

    def _extract_class(self, node, source: bytes, file_path: Path) -> ExtractedEntity | None:
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

    def _extract_method(self, node, source: bytes, file_path: Path) -> ExtractedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self.get_node_text(name_node, source)
        params = self._extract_params(node, source)
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
            parameters=params,
            source=self.get_node_text(node, source),
            is_async="async" in self.get_node_text(node, source)[:20],
        )

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
        return params

    def _extract_calls_from_body(self, node, caller_name: str, source: bytes, file_path: Path, analysis: FileAnalysis):
        for child in self.walk(node):
            if child.type == "call_expression":
                func = child.child_by_field_name("function")
                if func:
                    callee = self.get_node_text(func, source)
                    # Strip method calls to just the function name
                    if "." in callee:
                        callee = callee.split(".")[-1]
                    analysis.calls.append(ExtractedCall(
                        caller=caller_name,
                        callee=callee,
                        start_line=child.start_point[0] + 1,
                        start_column=child.start_point[1],
                        end_line=child.end_point[0] + 1,
                        end_column=child.end_point[1],
                    ))
