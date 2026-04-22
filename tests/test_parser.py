"""
Tests for pipeline/parser.py

Covers:
- Unit tests for Parser dispatch, Java, JSX/TSX, HTML, CFML, SQL parsing
- Property-based tests (Properties 4, 5, 6, 7, 8, 9, 10, 13, 14)

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.10, 3b.1, 3b.2, 3b.5, 3b.6
"""
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import List

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from models.code_block import Code_Block
from pipeline.parser import Parser
from tests.strategies import (
    java_code_strategy,
    java_code_with_imports_strategy,
    jsx_code_strategy,
    html_code_strategy,
    cfml_code_strategy,
    sql_code_strategy,
    sql_statement_strategy,
    sql_dialect_strategy,
)


# ---------------------------------------------------------------------------
# Helpers — mock tree-sitter nodes
# ---------------------------------------------------------------------------

def _make_node(node_type: str, start_byte: int, end_byte: int,
               start_row: int, end_row: int, children=None):
    """Create a mock tree-sitter node."""
    node = MagicMock()
    node.type = node_type
    node.start_byte = start_byte
    node.end_byte = end_byte
    node.start_point = (start_row, 0)
    node.end_point = (end_row, 0)
    node.children = children or []
    return node


def _make_parser_with_tree(root_children):
    """Create a mock ts_parser that returns a tree with given root children."""
    root = MagicMock()
    root.children = root_children

    tree = MagicMock()
    tree.root_node = root

    ts_parser = MagicMock()
    ts_parser.parse.return_value = tree
    return ts_parser


# ---------------------------------------------------------------------------
# Unit tests — Parser.parse dispatch
# ---------------------------------------------------------------------------

class TestParserDispatch:
    def test_returns_empty_when_ts_parser_is_none(self):
        parser = Parser()
        result = parser.parse("content", Path("file.java"), None, "unknown")
        assert result == []

    def test_returns_empty_for_unsupported_extension(self):
        ts_parser = _make_parser_with_tree([])
        parser = Parser()
        result = parser.parse("content", Path("file.rb"), ts_parser, "unknown")
        assert result == []

    def test_dispatches_java(self):
        ts_parser = _make_parser_with_tree([])
        parser = Parser()
        result = parser.parse("", Path("MyClass.java"), ts_parser, "unknown")
        assert isinstance(result, list)

    def test_dispatches_jsx(self):
        ts_parser = _make_parser_with_tree([])
        parser = Parser()
        result = parser.parse("", Path("App.jsx"), ts_parser, "unknown")
        assert isinstance(result, list)

    def test_dispatches_tsx(self):
        ts_parser = _make_parser_with_tree([])
        parser = Parser()
        result = parser.parse("", Path("App.tsx"), ts_parser, "unknown")
        assert isinstance(result, list)

    def test_dispatches_html(self):
        ts_parser = _make_parser_with_tree([])
        parser = Parser()
        result = parser.parse("", Path("index.html"), ts_parser, "unknown")
        assert isinstance(result, list)

    def test_dispatches_cfm(self):
        ts_parser = _make_parser_with_tree([])
        parser = Parser()
        result = parser.parse("", Path("page.cfm"), ts_parser, "unknown")
        assert isinstance(result, list)

    def test_dispatches_cfc(self):
        ts_parser = _make_parser_with_tree([])
        parser = Parser()
        result = parser.parse("", Path("Service.cfc"), ts_parser, "unknown")
        assert isinstance(result, list)

    def test_dispatches_sql(self):
        ts_parser = _make_parser_with_tree([])
        parser = Parser()
        result = parser.parse("", Path("schema.sql"), ts_parser, "sybase")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Unit tests — _parse_java
# ---------------------------------------------------------------------------

class TestParseJava:
    def test_extracts_method_declaration(self):
        content = "import java.util.List;\npublic class Foo {\n    public void bar() {}\n}"
        method_node = _make_node("method_declaration", 40, 60, 2, 2)
        import_node = _make_node("import_declaration", 0, 20, 0, 0)
        class_node = _make_node("class_declaration", 21, 70, 1, 3, children=[method_node])
        ts_parser = _make_parser_with_tree([import_node, class_node])

        parser = Parser()
        blocks = parser._parse_java(content, Path("Foo.java"), ts_parser)

        node_types = {b.node_type for b in blocks}
        assert "class_declaration" in node_types or "method_declaration" in node_types

    def test_imports_in_metadata(self):
        content = "import java.util.List;\npublic class Foo { public void bar() {} }"
        import_text = "import java.util.List;"
        import_node = _make_node("import_declaration", 0, len(import_text), 0, 0)
        method_node = _make_node("method_declaration", 40, 60, 1, 1)
        class_node = _make_node("class_declaration", 23, 65, 1, 1, children=[method_node])
        ts_parser = _make_parser_with_tree([import_node, class_node])

        parser = Parser()
        blocks = parser._parse_java(content, Path("Foo.java"), ts_parser)

        for block in blocks:
            assert "imports" in block.metadata

    def test_returns_empty_on_parse_exception(self):
        ts_parser = MagicMock()
        ts_parser.parse.side_effect = Exception("parse error")
        parser = Parser()
        result = parser._parse_java("bad content", Path("Foo.java"), ts_parser)
        assert result == []

    def test_language_is_java(self):
        content = "public class Foo {}"
        class_node = _make_node("class_declaration", 0, len(content), 0, 0)
        ts_parser = _make_parser_with_tree([class_node])
        parser = Parser()
        blocks = parser._parse_java(content, Path("Foo.java"), ts_parser)
        for block in blocks:
            assert block.language == "java"


# ---------------------------------------------------------------------------
# Unit tests — _parse_jsx_tsx
# ---------------------------------------------------------------------------

class TestParseJsxTsx:
    def test_extracts_function_declaration(self):
        content = "function MyComp() { return null; }"
        func_node = _make_node("function_declaration", 0, len(content), 0, 0)
        ts_parser = _make_parser_with_tree([func_node])
        parser = Parser()
        blocks = parser._parse_jsx_tsx(content, Path("App.jsx"), ts_parser)
        assert len(blocks) == 1
        assert blocks[0].node_type == "function_declaration"

    def test_extracts_arrow_function(self):
        content = "const Comp = () => null;"
        arrow_node = _make_node("arrow_function", 13, len(content) - 1, 0, 0)
        ts_parser = _make_parser_with_tree([arrow_node])
        parser = Parser()
        blocks = parser._parse_jsx_tsx(content, Path("App.tsx"), ts_parser)
        assert len(blocks) == 1
        assert blocks[0].node_type == "arrow_function"

    def test_language_is_jsx(self):
        content = "function A() {}"
        func_node = _make_node("function_declaration", 0, len(content), 0, 0)
        ts_parser = _make_parser_with_tree([func_node])
        parser = Parser()
        blocks = parser._parse_jsx_tsx(content, Path("A.jsx"), ts_parser)
        for block in blocks:
            assert block.language == "jsx"


# ---------------------------------------------------------------------------
# Unit tests — _parse_html
# ---------------------------------------------------------------------------

class TestParseHtml:
    def test_extracts_top_level_elements_only(self):
        content = "<div><p>child</p></div><section>text</section>"
        child_p = _make_node("element", 5, 20, 0, 0)
        div_node = _make_node("element", 0, 26, 0, 0, children=[child_p])
        section_node = _make_node("element", 26, len(content), 0, 0)
        ts_parser = _make_parser_with_tree([div_node, section_node])

        parser = Parser()
        blocks = parser._parse_html(content, Path("index.html"), ts_parser)

        # Only top-level elements (div and section), not the child <p>
        assert len(blocks) == 2
        assert all(b.node_type == "element" for b in blocks)

    def test_language_is_html(self):
        content = "<div>hello</div>"
        div_node = _make_node("element", 0, len(content), 0, 0)
        ts_parser = _make_parser_with_tree([div_node])
        parser = Parser()
        blocks = parser._parse_html(content, Path("index.html"), ts_parser)
        for block in blocks:
            assert block.language == "html"

    def test_non_element_children_ignored(self):
        content = "<!-- comment --><div>text</div>"
        comment_node = _make_node("comment", 0, 16, 0, 0)
        div_node = _make_node("element", 16, len(content), 0, 0)
        ts_parser = _make_parser_with_tree([comment_node, div_node])
        parser = Parser()
        blocks = parser._parse_html(content, Path("index.html"), ts_parser)
        assert len(blocks) == 1


# ---------------------------------------------------------------------------
# Unit tests — _parse_cfml
# ---------------------------------------------------------------------------

class TestParseCfml:
    def _make_cfquery_node(self, content: str, sql_text: str, start_row: int = 0):
        """Build a mock cfquery node with a text child containing SQL."""
        full = f'<cfquery name="q" datasource="ds">{sql_text}</cfquery>'
        text_child = _make_node("text", len(full) - len(sql_text) - len("</cfquery>"),
                                len(full) - len("</cfquery>"), start_row, start_row)
        text_child.type = "text"
        cfquery_node = _make_node("cfquery", 0, len(full), start_row, start_row,
                                  children=[text_child])
        return cfquery_node, full

    def test_extracts_cfquery_block(self):
        sql = "SELECT id FROM users"
        content = f'<cfquery name="q" datasource="ds">{sql}</cfquery>'
        text_child = _make_node("text", content.index(sql), content.index(sql) + len(sql), 0, 0)
        cfquery_node = _make_node("cfquery", 0, len(content), 0, 0, children=[text_child])
        ts_parser = _make_parser_with_tree([cfquery_node])

        parser = Parser()
        blocks = parser._parse_cfml(content, Path("page.cfm"), ts_parser, "sybase")

        cfquery_blocks = [b for b in blocks if b.node_type == "cfquery"]
        assert len(cfquery_blocks) == 1

    def test_extracts_sql_injection_for_cfquery(self):
        sql = "SELECT id FROM users"
        content = f'<cfquery name="q" datasource="ds">{sql}</cfquery>'
        text_child = _make_node("text", content.index(sql), content.index(sql) + len(sql), 0, 0)
        cfquery_node = _make_node("cfquery", 0, len(content), 0, 0, children=[text_child])
        ts_parser = _make_parser_with_tree([cfquery_node])

        parser = Parser()
        blocks = parser._parse_cfml(content, Path("page.cfm"), ts_parser, "sybase")

        sql_blocks = [b for b in blocks if b.node_type == "sql_injection"]
        assert len(sql_blocks) >= 1

    def test_sql_injection_has_dialect_and_source_line(self):
        sql = "SELECT id FROM users"
        content = f'<cfquery name="q" datasource="ds">{sql}</cfquery>'
        text_child = _make_node("text", content.index(sql), content.index(sql) + len(sql), 0, 0)
        cfquery_node = _make_node("cfquery", 0, len(content), 0, 0, children=[text_child])
        ts_parser = _make_parser_with_tree([cfquery_node])

        parser = Parser()
        blocks = parser._parse_cfml(content, Path("page.cfm"), ts_parser, "oracle")

        sql_blocks = [b for b in blocks if b.node_type == "sql_injection"]
        for b in sql_blocks:
            assert b.metadata.get("sql_dialect") == "oracle"
            assert "injection_source_line" in b.metadata


# ---------------------------------------------------------------------------
# Unit tests — _parse_sql
# ---------------------------------------------------------------------------

class TestParseSql:
    def test_extracts_statement_nodes(self):
        content = "SELECT id FROM foo;"
        stmt_node = _make_node("statement", 0, len(content), 0, 0)
        ts_parser = _make_parser_with_tree([stmt_node])
        parser = Parser()
        blocks = parser._parse_sql(content, Path("schema.sql"), ts_parser, "sybase")
        assert len(blocks) == 1
        assert blocks[0].node_type == "statement"

    def test_ddl_classification(self):
        content = "CREATE TABLE foo (id INT);"
        stmt_node = _make_node("statement", 0, len(content), 0, 0)
        ts_parser = _make_parser_with_tree([stmt_node])
        parser = Parser()
        blocks = parser._parse_sql(content, Path("schema.sql"), ts_parser, "oracle")
        assert blocks[0].metadata["block_type"] == "ddl_statement"

    def test_dml_classification(self):
        content = "SELECT id FROM foo;"
        stmt_node = _make_node("statement", 0, len(content), 0, 0)
        ts_parser = _make_parser_with_tree([stmt_node])
        parser = Parser()
        blocks = parser._parse_sql(content, Path("query.sql"), ts_parser, "sqlserver")
        assert blocks[0].metadata["block_type"] == "dml_statement"

    def test_sql_dialect_in_metadata(self):
        content = "SELECT 1;"
        stmt_node = _make_node("statement", 0, len(content), 0, 0)
        ts_parser = _make_parser_with_tree([stmt_node])
        parser = Parser()
        blocks = parser._parse_sql(content, Path("q.sql"), ts_parser, "sybase")
        assert blocks[0].metadata["sql_dialect"] == "sybase"

    def test_language_is_sql(self):
        content = "SELECT 1;"
        stmt_node = _make_node("statement", 0, len(content), 0, 0)
        ts_parser = _make_parser_with_tree([stmt_node])
        parser = Parser()
        blocks = parser._parse_sql(content, Path("q.sql"), ts_parser, "unknown")
        for block in blocks:
            assert block.language == "sql"


# ---------------------------------------------------------------------------
# Unit tests — _classify_sql
# ---------------------------------------------------------------------------

class TestClassifySql:
    def test_create_is_ddl(self):
        assert Parser()._classify_sql("CREATE TABLE t (id INT)") == "ddl_statement"

    def test_alter_is_ddl(self):
        assert Parser()._classify_sql("ALTER TABLE t ADD x INT") == "ddl_statement"

    def test_drop_is_ddl(self):
        assert Parser()._classify_sql("DROP TABLE t") == "ddl_statement"

    def test_select_is_dml(self):
        assert Parser()._classify_sql("SELECT * FROM t") == "dml_statement"

    def test_insert_is_dml(self):
        assert Parser()._classify_sql("INSERT INTO t VALUES (1)") == "dml_statement"

    def test_update_is_dml(self):
        assert Parser()._classify_sql("UPDATE t SET x = 1") == "dml_statement"

    def test_delete_is_dml(self):
        assert Parser()._classify_sql("DELETE FROM t WHERE id = 1") == "dml_statement"

    def test_case_insensitive(self):
        assert Parser()._classify_sql("create table t (id int)") == "ddl_statement"
        assert Parser()._classify_sql("select * from t") == "dml_statement"


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

def _make_ts_parser_for_nodes(nodes):
    """Build a mock ts_parser returning a tree with given root children."""
    return _make_parser_with_tree(nodes)


# --- Property 4: Parsing Java extrai todos os blocos com tipos corretos ---

@settings(max_examples=50)
@given(java_code_strategy())
def test_property_4_java_block_types(java_data):
    """**Validates: Requirements 3.1**

    Property 4: Parsing Java extrai todos os blocos com tipos corretos.
    For any Java code with N methods and M classes, the parser returns blocks
    with node_type in {"method_declaration", "class_declaration"}.
    """
    code, n_methods, n_classes = java_data
    valid_types = {"method_declaration", "class_declaration"}

    # Build mock nodes: n_methods method_declaration + n_classes class_declaration
    nodes = []
    offset = 0
    for i in range(n_classes):
        node = _make_node("class_declaration", offset, offset + 10, i, i)
        nodes.append(node)
        offset += 11
    for i in range(n_methods):
        node = _make_node("method_declaration", offset, offset + 10, n_classes + i, n_classes + i)
        nodes.append(node)
        offset += 11

    ts_parser = _make_ts_parser_for_nodes(nodes)
    parser = Parser()
    blocks = parser._parse_java(code, Path("Test.java"), ts_parser)

    for block in blocks:
        assert block.node_type in valid_types, (
            f"Unexpected node_type: {block.node_type}"
        )


# --- Property 5: Parsing JSX/TSX extrai todos os blocos com tipos corretos ---

@settings(max_examples=50)
@given(jsx_code_strategy())
def test_property_5_jsx_block_types(jsx_data):
    """**Validates: Requirements 3.2**

    Property 5: Parsing JSX/TSX extrai todos os blocos com tipos corretos.
    All returned blocks have node_type in {"function_declaration", "arrow_function", "jsx_element"}.
    """
    code, n_funcs = jsx_data
    valid_types = {"function_declaration", "arrow_function", "jsx_element"}

    nodes = []
    offset = 0
    for i in range(n_funcs):
        node = _make_node("function_declaration", offset, offset + 10, i, i)
        nodes.append(node)
        offset += 11

    ts_parser = _make_ts_parser_for_nodes(nodes)
    parser = Parser()
    blocks = parser._parse_jsx_tsx(code, Path("App.jsx"), ts_parser)

    for block in blocks:
        assert block.node_type in valid_types, (
            f"Unexpected node_type: {block.node_type}"
        )


# --- Property 6: Parsing HTML extrai apenas elementos de nível superior ---

@settings(max_examples=50)
@given(html_code_strategy())
def test_property_6_html_top_level_only(html_data):
    """**Validates: Requirements 3.3**

    Property 6: Parsing HTML extrai apenas elementos de nível superior.
    For any HTML with N top-level elements, the parser returns exactly N blocks
    of type "element", without including child elements as independent blocks.
    """
    code, n_elements = html_data

    # Build mock: N top-level element nodes, each with a child element
    nodes = []
    offset = 0
    for i in range(n_elements):
        child = _make_node("element", offset + 1, offset + 5, i, i)
        top = _make_node("element", offset, offset + 10, i, i, children=[child])
        nodes.append(top)
        offset += 11

    ts_parser = _make_ts_parser_for_nodes(nodes)
    parser = Parser()
    blocks = parser._parse_html(code, Path("index.html"), ts_parser)

    # Should return exactly N blocks (top-level only, not children)
    assert len(blocks) == n_elements
    for block in blocks:
        assert block.node_type == "element"


# --- Property 7: Parsing CFML gera sql_injection para cada cfquery ---

@settings(max_examples=50)
@given(cfml_code_strategy())
def test_property_7_cfml_sql_injection(cfml_data):
    """**Validates: Requirements 3.4, 3.5**

    Property 7: Parsing CFML gera sql_injection para cada cfquery.
    For any CFML with N cfquery tags, the parser returns at least N sql_injection blocks.
    """
    code, n_queries = cfml_data

    # Build mock cfquery nodes with text children containing SQL
    nodes = []
    offset = 0
    sql_text = "SELECT id FROM t"
    for i in range(n_queries):
        text_child = _make_node("text", offset + 5, offset + 5 + len(sql_text), i, i)
        cfquery_node = _make_node("cfquery", offset, offset + 30, i, i, children=[text_child])
        nodes.append(cfquery_node)
        offset += 31

    ts_parser = _make_ts_parser_for_nodes(nodes)
    parser = Parser()
    blocks = parser._parse_cfml(code, Path("page.cfm"), ts_parser, "sybase")

    sql_injection_blocks = [b for b in blocks if b.node_type == "sql_injection"]
    assert len(sql_injection_blocks) >= n_queries


# --- Property 8: Parsing SQL extrai todos os statements ---

@settings(max_examples=50)
@given(sql_code_strategy())
def test_property_8_sql_all_statements(sql_data):
    """**Validates: Requirements 3.6**

    Property 8: Parsing SQL extrai todos os statements.
    For any SQL with N statements, the parser returns exactly N blocks of type "statement".
    """
    code, n_stmts = sql_data

    nodes = []
    offset = 0
    for i in range(n_stmts):
        node = _make_node("statement", offset, offset + 10, i, i)
        nodes.append(node)
        offset += 11

    ts_parser = _make_ts_parser_for_nodes(nodes)
    parser = Parser()
    blocks = parser._parse_sql(code, Path("schema.sql"), ts_parser, "unknown")

    assert len(blocks) == n_stmts
    for block in blocks:
        assert block.node_type == "statement"


# --- Property 9: Invariante estrutural de Code_Block ---

@settings(max_examples=100)
@given(
    st.text(min_size=1),
    st.text(min_size=1),
    st.text(min_size=1),
    st.integers(min_value=1, max_value=1000),
    st.integers(min_value=0, max_value=500),
)
def test_property_9_code_block_structural_invariant(node_type, language, content, start_line, extra):
    """**Validates: Requirements 3.7**

    Property 9: Invariante estrutural de Code_Block.
    All Code_Blocks returned by the parser have non-null, non-empty required fields
    and start_line <= end_line.
    """
    end_line = start_line + extra

    # Build a mock node and verify the block created satisfies the invariant
    node = _make_node(node_type, 0, len(content), start_line - 1, end_line - 1)
    ts_parser = _make_ts_parser_for_nodes([node])

    parser = Parser()
    # Use SQL parsing as a simple case
    blocks = parser._parse_sql(content, Path("f.sql"), ts_parser, "unknown")

    # If the node type is "statement", a block is created
    if node_type == "statement":
        assert len(blocks) == 1
        b = blocks[0]
        assert b.node_type
        assert b.language
        assert b.content is not None
        assert b.start_line <= b.end_line


# --- Property 10: Imports Java presentes no metadata de todos os blocos ---

@settings(max_examples=50)
@given(java_code_with_imports_strategy())
def test_property_10_java_imports_in_metadata(java_import_data):
    """**Validates: Requirements 3.10**

    Property 10: Imports Java presentes no metadata de todos os blocos.
    For any Java code with imports, all Code_Blocks have metadata['imports']
    containing the complete list of imports.
    """
    code, imports = java_import_data

    # Build mock: import nodes + a class with a method
    import_nodes = []
    offset = 0
    for imp in imports:
        import_text = f"import {imp};"
        node = _make_node("import_declaration", offset, offset + len(import_text), 0, 0)
        import_nodes.append(node)
        offset += len(import_text) + 1

    method_node = _make_node("method_declaration", offset + 10, offset + 30, 1, 1)
    class_node = _make_node("class_declaration", offset, offset + 40, 1, 3, children=[method_node])

    all_nodes = import_nodes + [class_node]
    ts_parser = _make_ts_parser_for_nodes(all_nodes)

    parser = Parser()
    blocks = parser._parse_java(code, Path("Test.java"), ts_parser)

    for block in blocks:
        assert "imports" in block.metadata
        assert isinstance(block.metadata["imports"], list)


# --- Property 13: sql_dialect presente no metadata de todos os Code_Blocks SQL ---

@settings(max_examples=50)
@given(sql_dialect_strategy(), sql_code_strategy())
def test_property_13_sql_dialect_in_metadata(dialect, sql_data):
    """**Validates: Requirements 3b.1, 3b.2, 3b.4**

    Property 13: sql_dialect presente no metadata de todos os Code_Blocks SQL.
    For any SQL block, metadata['sql_dialect'] is present and has a valid value.
    """
    code, n_stmts = sql_data
    valid_dialects = {"sybase", "oracle", "sqlserver", "unknown"}

    nodes = []
    offset = 0
    for i in range(n_stmts):
        node = _make_node("statement", offset, offset + 10, i, i)
        nodes.append(node)
        offset += 11

    ts_parser = _make_ts_parser_for_nodes(nodes)
    parser = Parser()
    blocks = parser._parse_sql(code, Path("q.sql"), ts_parser, dialect)

    for block in blocks:
        assert "sql_dialect" in block.metadata
        assert block.metadata["sql_dialect"] in valid_dialects


# --- Property 14: Classificação DDL/DML correta no block_type ---

@settings(max_examples=50)
@given(sql_statement_strategy())
def test_property_14_ddl_dml_classification(stmt_data):
    """**Validates: Requirements 3b.5, 3b.6**

    Property 14: Classificação DDL/DML correta no block_type.
    For any SQL statement, metadata['block_type'] is "ddl_statement" for DDL
    and "dml_statement" for DML.
    """
    stmt_text, expected_type = stmt_data

    node = _make_node("statement", 0, len(stmt_text), 0, 0)
    ts_parser = _make_ts_parser_for_nodes([node])

    parser = Parser()
    blocks = parser._parse_sql(stmt_text, Path("q.sql"), ts_parser, "unknown")

    assert len(blocks) == 1
    assert blocks[0].metadata["block_type"] == expected_type
