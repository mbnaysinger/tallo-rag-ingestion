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

        Inclui lista de imports no metadata de cada bloco.

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

    def _walk_java(self, node, content, imports, target_types, blocks, file_path):
        """Recursively walk the tree collecting target node types."""
        for child in node.children:
            if child.type in target_types:
                block_content = content[child.start_byte:child.end_byte]
                start_line = child.start_point[0] + 1
                end_line = child.end_point[0] + 1
                blocks.append(
                    Code_Block(
                        node_type=child.type,
                        language="java",
                        content=block_content,
                        start_line=start_line,
                        end_line=end_line,
                        metadata={"imports": imports},
                    )
                )
                # Also recurse into class bodies to find nested methods/classes
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

        target_types = {"function_declaration", "arrow_function", "jsx_element"}
        blocks: List[Code_Block] = []

        try:
            self._walk_collect(tree.root_node, content, target_types, "jsx", blocks)
        except Exception as exc:
            logger.warning(
                "JSX/TSX partial parse error — returning blocks extracted so far",
                extra={"file_path": str(file_path), "error": str(exc)},
            )

        return blocks

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
            )
        except Exception as exc:
            logger.warning(
                "CFML partial parse error — returning blocks extracted so far",
                extra={"file_path": str(file_path), "error": str(exc)},
            )

        return blocks

    def _walk_cfml(self, node, content, target_types, blocks, file_path, sql_dialect):
        """Recursively walk CFML tree, collecting target nodes and sql_injection."""
        for child in node.children:
            if child.type in target_types:
                block_content = content[child.start_byte:child.end_byte]
                start_line = child.start_point[0] + 1
                end_line = child.end_point[0] + 1

                blocks.append(
                    Code_Block(
                        node_type=child.type,
                        language="cfml",
                        content=block_content,
                        start_line=start_line,
                        end_line=end_line,
                        metadata={},
                    )
                )

                # For cfquery nodes, extract inner SQL as sql_injection block
                if child.type == "cfquery":
                    sql_text = self._extract_cfquery_sql(child, content)
                    if sql_text and sql_text.strip():
                        blocks.append(
                            Code_Block(
                                node_type="sql_injection",
                                language="sql",
                                content=sql_text.strip(),
                                start_line=start_line,
                                end_line=end_line,
                                metadata={
                                    "sql_dialect": sql_dialect,
                                    "injection_source_line": start_line,
                                },
                            )
                        )

                # Recurse into children
                self._walk_cfml(child, content, target_types, blocks, file_path, sql_dialect)
            else:
                self._walk_cfml(child, content, target_types, blocks, file_path, sql_dialect)

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
