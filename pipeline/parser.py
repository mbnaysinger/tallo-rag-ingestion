"""
Parser — extração de Code_Blocks via Tree-sitter por linguagem.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.10, 3b.1, 3b.2, 3b.5, 3b.6
"""
from pathlib import Path
from typing import List

from models.code_block import Code_Block
from utils.logging import get_logger

logger = get_logger(__name__)

# DDL keywords (case-insensitive prefix match)
_DDL_KEYWORDS = ("CREATE", "ALTER", "DROP")
# DML keywords
_DML_KEYWORDS = ("SELECT", "INSERT", "UPDATE", "DELETE")


class Parser:
    """Extrai Code_Blocks de arquivos de código-fonte via Tree-sitter.

    Requirements: 3.7, 3.8
    """

    def parse(
        self,
        content: str,
        file_path: Path,
        ts_parser,
        sql_dialect: str,
    ) -> List[Code_Block]:
        """Despacha para o método de parsing correto com base na extensão de file_path.

        Em caso de erro de sintaxe parcial, retorna blocos extraídos até o ponto
        do erro e emite log WARNING.

        Requirements: 3.7, 3.8
        """
        if ts_parser is None:
            logger.warning(
                "ts_parser is None — grammar not available, skipping file",
                extra={"file_path": str(file_path)},
            )
            return []

        ext = Path(file_path).suffix.lower()

        if ext == ".java":
            return self._parse_java(content, file_path, ts_parser)
        elif ext in (".jsx", ".tsx"):
            return self._parse_jsx_tsx(content, file_path, ts_parser)
        elif ext == ".html":
            return self._parse_html(content, file_path, ts_parser)
        elif ext in (".cfm", ".cfc"):
            return self._parse_cfml(content, file_path, ts_parser, sql_dialect)
        elif ext == ".sql":
            return self._parse_sql(content, file_path, ts_parser, sql_dialect)

        return []

    # ------------------------------------------------------------------
    # Java
    # ------------------------------------------------------------------

    def _parse_java(
        self,
        content: str,
        file_path: Path,
        ts_parser,
    ) -> List[Code_Block]:
        """Extrai method_declaration e class_declaration.

        Inclui lista de imports, dependências injetadas, chamadas de método,
        anotações, nome da classe, herança e interfaces no metadata de cada bloco.

        Requirements: 3.1, 3.10
        """
        try:
            tree = ts_parser.parse(bytes(content, "utf-8"))
        except Exception as exc:
            logger.warning(
                "Java parse error",
                extra={"file_path": str(file_path), "error": str(exc)},
            )
            return []

        root = tree.root_node

        # Collect imports from root-level import_declaration nodes
        imports: List[str] = []
        for child in root.children:
            if child.type == "import_declaration":
                imports.append(content[child.start_byte:child.end_byte].strip())

        target_types = {"method_declaration", "class_declaration"}
        blocks: List[Code_Block] = []

        try:
            self._walk_java(root, content, imports, target_types, blocks, file_path)
        except Exception as exc:
            logger.warning(
                "Java partial parse error — returning blocks extracted so far",
                extra={"file_path": str(file_path), "error": str(exc)},
            )

        return blocks

    # ------------------------------------------------------------------
    # Java — dependency extraction helpers
    # ------------------------------------------------------------------

    def _java_node_text(self, node, content: str) -> str:
        """Return the source text for a tree-sitter node."""
        return content[node.start_byte:node.end_byte]

    def _java_extract_annotations(self, node, content: str) -> List[str]:
        """Collect annotation names from direct children of a node."""
        annotations = []
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type == "annotation":
                        annotations.append(self._java_node_text(mod, content).strip())
            elif child.type == "annotation":
                annotations.append(self._java_node_text(child, content).strip())
        return annotations

    def _java_extract_class_meta(self, class_node, content: str) -> dict:
        """Extract class_name, extends, implements from a class_declaration node."""
        meta: dict = {}
        for child in class_node.children:
            if child.type == "identifier":
                meta["class_name"] = self._java_node_text(child, content)
            elif child.type == "superclass":
                # superclass → "extends" keyword + type_identifier
                for sc in child.children:
                    if sc.type == "type_identifier":
                        meta["extends"] = self._java_node_text(sc, content)
            elif child.type == "super_interfaces":
                ifaces = []
                for si in child.children:
                    if si.type in ("type_list", "interface_type_list"):
                        for t in si.children:
                            if t.type == "type_identifier":
                                ifaces.append(self._java_node_text(t, content))
                    elif si.type == "type_identifier":
                        ifaces.append(self._java_node_text(si, content))
                if ifaces:
                    meta["implements"] = ifaces
        return meta

    def _java_extract_injects(self, class_node, content: str) -> List[str]:
        """Extract types of fields annotated with @Inject inside a class body."""
        injects = []
        for child in class_node.children:
            if child.type == "class_body":
                for member in child.children:
                    if member.type == "field_declaration":
                        has_inject = False
                        field_type = None
                        for fc in member.children:
                            if fc.type == "modifiers":
                                for mod in fc.children:
                                    if mod.type == "annotation":
                                        ann_text = self._java_node_text(mod, content)
                                        if "@Inject" in ann_text:
                                            has_inject = True
                            elif fc.type in ("type_identifier", "generic_type"):
                                field_type = self._java_node_text(fc, content)
                        if has_inject and field_type:
                            injects.append(field_type)
        return injects

    def _java_extract_method_meta(self, method_node, content: str) -> dict:
        """Extract method_name, return_type, param_types from a method_declaration."""
        meta: dict = {}
        param_types = []
        for child in method_node.children:
            if child.type == "identifier":
                meta["method_name"] = self._java_node_text(child, content)
            elif child.type in (
                "void_type", "type_identifier", "integral_type",
                "floating_point_type", "boolean_type", "array_type", "generic_type",
            ):
                if "return_type" not in meta:
                    meta["return_type"] = self._java_node_text(child, content)
            elif child.type == "formal_parameters":
                for param in child.children:
                    if param.type == "formal_parameter":
                        for pt in param.children:
                            if pt.type in ("type_identifier", "generic_type", "array_type"):
                                param_types.append(self._java_node_text(pt, content))
                                break
        if param_types:
            meta["param_types"] = param_types
        return meta

    def _java_extract_calls(self, node, content: str) -> List[str]:
        """Recursively collect method_invocation expressions inside a node."""
        calls = []
        for child in node.children:
            if child.type == "method_invocation":
                calls.append(self._java_node_text(child, content).split("(")[0].strip())
            calls.extend(self._java_extract_calls(child, content))
        # Deduplicate preserving order
        seen = set()
        unique = []
        for c in calls:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique

    def _walk_java(self, node, content, imports, target_types, blocks, file_path):
        """Recursively walk the tree collecting target node types with full dependency metadata."""
        for child in node.children:
            if child.type == "class_declaration":
                block_content = content[child.start_byte:child.end_byte]
                start_line = child.start_point[0] + 1
                end_line = child.end_point[0] + 1

                class_meta = self._java_extract_class_meta(child, content)
                annotations = self._java_extract_annotations(child, content)
                injects = self._java_extract_injects(child, content)

                metadata: dict = {"imports": imports}
                metadata.update(class_meta)
                if annotations:
                    metadata["annotations"] = annotations
                if injects:
                    metadata["injects"] = injects

                blocks.append(
                    Code_Block(
                        node_type="class_declaration",
                        language="java",
                        content=block_content,
                        start_line=start_line,
                        end_line=end_line,
                        metadata=metadata,
                    )
                )
                # Recurse into class body for nested methods/classes
                self._walk_java(child, content, imports, target_types, blocks, file_path)

            elif child.type == "method_declaration":
                block_content = content[child.start_byte:child.end_byte]
                start_line = child.start_point[0] + 1
                end_line = child.end_point[0] + 1

                method_meta = self._java_extract_method_meta(child, content)
                annotations = self._java_extract_annotations(child, content)
                calls = self._java_extract_calls(child, content)

                metadata = {"imports": imports}
                metadata.update(method_meta)
                if annotations:
                    metadata["annotations"] = annotations
                if calls:
                    metadata["calls"] = calls

                blocks.append(
                    Code_Block(
                        node_type="method_declaration",
                        language="java",
                        content=block_content,
                        start_line=start_line,
                        end_line=end_line,
                        metadata=metadata,
                    )
                )
                # Recurse for nested classes inside methods (rare but valid)
                self._walk_java(child, content, imports, target_types, blocks, file_path)

            else:
                self._walk_java(child, content, imports, target_types, blocks, file_path)

    # ------------------------------------------------------------------
    # JSX / TSX
    # ------------------------------------------------------------------

    def _parse_jsx_tsx(
        self,
        content: str,
        file_path: Path,
        ts_parser,
    ) -> List[Code_Block]:
        """Extrai function_declaration, arrow_function, jsx_element.

        Inclui component_name, imports e hooks no metadata.

        Requirements: 3.2
        """
        try:
            tree = ts_parser.parse(bytes(content, "utf-8"))
        except Exception as exc:
            logger.warning(
                "JSX/TSX parse error",
                extra={"file_path": str(file_path), "error": str(exc)},
            )
            return []

        root = tree.root_node

        # Collect import statements from root level
        jsx_imports: List[str] = []
        for child in root.children:
            if child.type == "import_statement":
                jsx_imports.append(content[child.start_byte:child.end_byte].strip())

        target_types = {"function_declaration", "arrow_function", "jsx_element"}
        blocks: List[Code_Block] = []

        try:
            self._walk_jsx(root, content, jsx_imports, target_types, blocks, file_path)
        except Exception as exc:
            logger.warning(
                "JSX/TSX partial parse error — returning blocks extracted so far",
                extra={"file_path": str(file_path), "error": str(exc)},
            )

        return blocks

    # ------------------------------------------------------------------
    # JSX/TSX — dependency extraction helpers
    # ------------------------------------------------------------------

    def _jsx_extract_hooks(self, node, content: str) -> List[str]:
        """Collect React hook names (call_expression starting with 'use') inside a node."""
        import re
        hooks = []
        raw = content[node.start_byte:node.end_byte]
        for m in re.finditer(r'\b(use[A-Z]\w*)\s*\(', raw):
            hooks.append(m.group(1))
        seen = set()
        return [h for h in hooks if not (h in seen or seen.add(h))]

    def _jsx_function_name(self, node, content: str) -> str:
        """Extract the identifier name from a function_declaration node."""
        for child in node.children:
            if child.type == "identifier":
                return content[child.start_byte:child.end_byte]
        return ""

    def _walk_jsx(self, node, content, jsx_imports, target_types, blocks, file_path):
        """Recursively walk JSX/TSX tree collecting targets with dependency metadata."""
        for child in node.children:
            if child.type in target_types:
                block_content = content[child.start_byte:child.end_byte]
                start_line = child.start_point[0] + 1
                end_line = child.end_point[0] + 1

                metadata: dict = {}
                if jsx_imports:
                    metadata["imports"] = jsx_imports

                if child.type == "function_declaration":
                    name = self._jsx_function_name(child, content)
                    if name:
                        metadata["component_name"] = name
                    hooks = self._jsx_extract_hooks(child, content)
                    if hooks:
                        metadata["hooks"] = hooks

                elif child.type == "arrow_function":
                    # Arrow functions are often assigned: const Foo = () => ...
                    # The name lives in the parent variable_declarator
                    hooks = self._jsx_extract_hooks(child, content)
                    if hooks:
                        metadata["hooks"] = hooks

                blocks.append(
                    Code_Block(
                        node_type=child.type,
                        language="jsx",
                        content=block_content,
                        start_line=start_line,
                        end_line=end_line,
                        metadata=metadata,
                    )
                )
                self._walk_jsx(child, content, jsx_imports, target_types, blocks, file_path)
            else:
                self._walk_jsx(child, content, jsx_imports, target_types, blocks, file_path)

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    def _parse_html(
        self,
        content: str,
        file_path: Path,
        ts_parser,
    ) -> List[Code_Block]:
        """Extrai elementos de nível superior.

        Retorna apenas elementos de nível superior, sem incluir filhos como
        blocos independentes.

        Requirements: 3.3
        """
        try:
            tree = ts_parser.parse(bytes(content, "utf-8"))
        except Exception as exc:
            logger.warning(
                "HTML parse error",
                extra={"file_path": str(file_path), "error": str(exc)},
            )
            return []

        blocks: List[Code_Block] = []

        try:
            # Only look at direct children of root (document node)
            root = tree.root_node
            for child in root.children:
                if child.type == "element":
                    block_content = content[child.start_byte:child.end_byte]
                    start_line = child.start_point[0] + 1
                    end_line = child.end_point[0] + 1
                    blocks.append(
                        Code_Block(
                            node_type="element",
                            language="html",
                            content=block_content,
                            start_line=start_line,
                            end_line=end_line,
                            metadata={},
                        )
                    )
        except Exception as exc:
            logger.warning(
                "HTML partial parse error — returning blocks extracted so far",
                extra={"file_path": str(file_path), "error": str(exc)},
            )

        return blocks

    # ------------------------------------------------------------------
    # CFML
    # ------------------------------------------------------------------

    def _parse_cfml(
        self,
        content: str,
        file_path: Path,
        ts_parser,
        sql_dialect: str,
    ) -> List[Code_Block]:
        """Extrai cfcomponent, cffunction, cfquery e sql_injection.

        Para cada cfquery, extrai conteúdo SQL interno como Code_Block adicional
        do tipo sql_injection com sql_dialect e injection_source_line no metadata.

        Requirements: 3.4, 3.5, 3b.2
        """
        try:
            tree = ts_parser.parse(bytes(content, "utf-8"))
        except Exception as exc:
            logger.warning(
                "CFML parse error",
                extra={"file_path": str(file_path), "error": str(exc)},
            )
            return []

        cfml_target_types = {"cfcomponent", "cffunction", "cfquery"}
        blocks: List[Code_Block] = []

        try:
            self._walk_cfml(
                tree.root_node,
                content,
                cfml_target_types,
                blocks,
                file_path,
                sql_dialect,
                component_name=Path(str(file_path)).stem,
            )
        except Exception as exc:
            logger.warning(
                "CFML partial parse error — returning blocks extracted so far",
                extra={"file_path": str(file_path), "error": str(exc)},
            )

        return blocks

    # ------------------------------------------------------------------
    # CFML — dependency extraction helpers
    # ------------------------------------------------------------------

    def _cfml_attr(self, node, content: str, attr_name: str) -> str:
        """Return the value of a CFML tag attribute by name (case-insensitive)."""
        for child in node.children:
            if child.type in ("attribute", "tag_attribute"):
                name_node = None
                value_node = None
                for ac in child.children:
                    if ac.type in ("attribute_name", "identifier"):
                        name_node = ac
                    elif ac.type in ("attribute_value", "quoted_attribute_value", "string"):
                        value_node = ac
                if name_node and value_node:
                    name = self._java_node_text(name_node, content).strip().lower()
                    if name == attr_name.lower():
                        val = self._java_node_text(value_node, content).strip()
                        return val.strip('"\'')
        return ""

    def _cfml_extract_calls_components(self, node, content: str) -> List[str]:
        """Collect component names from cfinvoke tags inside a node."""
        import re
        calls = []
        raw = content[node.start_byte:node.end_byte]
        # Match cfinvoke component="..." or cfinvoke component='...'
        for m in re.finditer(r'<cfinvoke[^>]+component\s*=\s*["\']([^"\']+)["\']', raw, re.IGNORECASE):
            calls.append(m.group(1))
        # Also match cfset new ComponentName() patterns
        for m in re.finditer(r'\bnew\s+([\w.]+)\s*\(', raw):
            calls.append(m.group(1))
        seen = set()
        return [c for c in calls if not (c in seen or seen.add(c))]

    def _cfml_extract_tables(self, sql_text: str) -> List[str]:
        """Extract table names referenced in a SQL string (FROM / JOIN / INTO / UPDATE)."""
        import re
        tables = []
        pattern = re.compile(
            r'\b(?:FROM|JOIN|INTO|UPDATE)\s+([\w#]+)',
            re.IGNORECASE,
        )
        for m in pattern.finditer(sql_text):
            tables.append(m.group(1).upper())
        seen = set()
        return [t for t in tables if not (t in seen or seen.add(t))]

    def _walk_cfml(self, node, content, target_types, blocks, file_path, sql_dialect,
                   component_name: str = ""):
        """Recursively walk CFML tree, collecting target nodes and sql_injection."""
        for child in node.children:
            if child.type in target_types:
                block_content = content[child.start_byte:child.end_byte]
                start_line = child.start_point[0] + 1
                end_line = child.end_point[0] + 1

                metadata: dict = {}

                if child.type == "cfcomponent":
                    comp_name = self._cfml_attr(child, content, "displayname") \
                                or self._cfml_attr(child, content, "hint") \
                                or Path(str(file_path)).stem
                    metadata["component_name"] = comp_name
                    component_name = comp_name

                elif child.type == "cffunction":
                    fn_name = self._cfml_attr(child, content, "name")
                    if fn_name:
                        metadata["function_name"] = fn_name
                    if component_name:
                        metadata["component_name"] = component_name
                    return_type = self._cfml_attr(child, content, "returntype")
                    if return_type:
                        metadata["return_type"] = return_type
                    calls_comps = self._cfml_extract_calls_components(child, content)
                    if calls_comps:
                        metadata["calls_components"] = calls_comps

                blocks.append(
                    Code_Block(
                        node_type=child.type,
                        language="cfml",
                        content=block_content,
                        start_line=start_line,
                        end_line=end_line,
                        metadata=metadata,
                    )
                )

                # For cfquery nodes, extract inner SQL as sql_injection block
                if child.type == "cfquery":
                    sql_text = self._extract_cfquery_sql(child, content)
                    if sql_text and sql_text.strip():
                        tables = self._cfml_extract_tables(sql_text)
                        sql_meta: dict = {
                            "sql_dialect": sql_dialect,
                            "injection_source_line": start_line,
                        }
                        if tables:
                            sql_meta["tables"] = tables
                        if component_name:
                            sql_meta["component_name"] = component_name
                        blocks.append(
                            Code_Block(
                                node_type="sql_injection",
                                language="sql",
                                content=sql_text.strip(),
                                start_line=start_line,
                                end_line=end_line,
                                metadata=sql_meta,
                            )
                        )

                # Recurse into children, propagating component_name
                self._walk_cfml(child, content, target_types, blocks, file_path,
                                 sql_dialect, component_name)
            else:
                self._walk_cfml(child, content, target_types, blocks, file_path,
                                 sql_dialect, component_name)

    def _extract_cfquery_sql(self, cfquery_node, content: str) -> str:
        """Extract the SQL text content from inside a cfquery node."""
        sql_parts = []
        for child in cfquery_node.children:
            # Text/content nodes inside cfquery contain the SQL
            if child.type in ("text", "raw_text", "content"):
                sql_parts.append(content[child.start_byte:child.end_byte])
            elif child.type not in (
                "cfquery_tag",
                "cfquery_end_tag",
                "start_tag",
                "end_tag",
                "tag",
            ):
                # Include any other non-tag content
                child_text = content[child.start_byte:child.end_byte]
                # Only include if it looks like SQL (not a tag)
                stripped = child_text.strip()
                if stripped and not stripped.startswith("<"):
                    sql_parts.append(child_text)

        if sql_parts:
            return "".join(sql_parts)

        # Fallback: extract text between opening and closing tags
        raw = content[cfquery_node.start_byte:cfquery_node.end_byte]
        # Find content between > and </cfquery
        import re
        match = re.search(r">(.*?)</cfquery", raw, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1)

        return ""

    # ------------------------------------------------------------------
    # SQL
    # ------------------------------------------------------------------

    def _parse_sql(
        self,
        content: str,
        file_path: Path,
        ts_parser,
        sql_dialect: str,
    ) -> List[Code_Block]:
        """Extrai statements com classificação DDL/DML e sql_dialect.

        Classifica cada statement como ddl_statement ou dml_statement no
        metadata['block_type']. Inclui sql_dialect no metadata de cada bloco.

        Requirements: 3.6, 3b.1, 3b.5, 3b.6
        """
        try:
            tree = ts_parser.parse(bytes(content, "utf-8"))
        except Exception as exc:
            logger.warning(
                "SQL parse error",
                extra={"file_path": str(file_path), "error": str(exc)},
            )
            return []

        blocks: List[Code_Block] = []

        try:
            root = tree.root_node
            for child in root.children:
                if child.type == "statement":
                    block_content = content[child.start_byte:child.end_byte]
                    start_line = child.start_point[0] + 1
                    end_line = child.end_point[0] + 1
                    block_type = self._classify_sql(block_content)
                    blocks.append(
                        Code_Block(
                            node_type="statement",
                            language="sql",
                            content=block_content,
                            start_line=start_line,
                            end_line=end_line,
                            metadata={
                                "sql_dialect": sql_dialect,
                                "block_type": block_type,
                            },
                        )
                    )
        except Exception as exc:
            logger.warning(
                "SQL partial parse error — returning blocks extracted so far",
                extra={"file_path": str(file_path), "error": str(exc)},
            )

        return blocks

    def _classify_sql(self, statement_text: str) -> str:
        """Classify a SQL statement as ddl_statement or dml_statement."""
        upper = statement_text.strip().upper()
        for kw in _DDL_KEYWORDS:
            if upper.startswith(kw):
                return "ddl_statement"
        for kw in _DML_KEYWORDS:
            if upper.startswith(kw):
                return "dml_statement"
        # Default to dml if unknown
        return "dml_statement"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _walk_collect(self, node, content, target_types, language, blocks):
        """Generic recursive walker that collects nodes of target_types."""
        for child in node.children:
            if child.type in target_types:
                block_content = content[child.start_byte:child.end_byte]
                start_line = child.start_point[0] + 1
                end_line = child.end_point[0] + 1
                blocks.append(
                    Code_Block(
                        node_type=child.type,
                        language=language,
                        content=block_content,
                        start_line=start_line,
                        end_line=end_line,
                        metadata={},
                    )
                )
                # Recurse to find nested targets
                self._walk_collect(child, content, target_types, language, blocks)
            else:
                self._walk_collect(child, content, target_types, language, blocks)
