"""
Hypothesis strategies customizadas para os testes de propriedade do
Tallo RAG Ingestion Service.
"""
from hypothesis import strategies as st

from pipeline.grammar_router import SUPPORTED_EXTENSIONS


def unsupported_ext_strategy():
    """Gera extensões de arquivo que NÃO estão no conjunto suportado."""
    supported_set = set(SUPPORTED_EXTENSIONS)
    return (
        st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="._-"),
            min_size=1,
            max_size=10,
        )
        .map(lambda s: "." + s if not s.startswith(".") else s)
        .filter(lambda ext: ext not in supported_set and len(ext) >= 2)
    )


def sql_dialect_strategy():
    """Gera dialetos SQL válidos."""
    return st.sampled_from(["sybase", "oracle", "sqlserver", "unknown"])


def java_method_strategy():
    """Gera um método Java simples com nome válido."""
    return st.from_regex(r"[a-z][a-zA-Z0-9]{1,10}", fullmatch=True)


def java_code_strategy():
    """Gera código Java com N métodos e M classes (N+M >= 1).

    Retorna (code_str, expected_method_count, expected_class_count).
    """
    method_name = st.from_regex(r"[a-z][a-zA-Z0-9]{1,8}", fullmatch=True)
    class_name = st.from_regex(r"[A-Z][a-zA-Z0-9]{1,8}", fullmatch=True)

    @st.composite
    def _build(draw):
        n_methods = draw(st.integers(min_value=0, max_value=3))
        n_classes = draw(st.integers(min_value=0, max_value=2))
        # Ensure at least one block
        if n_methods == 0 and n_classes == 0:
            n_methods = 1

        lines = []
        # Top-level methods (inside a wrapper class so Java is valid)
        wrapper = draw(class_name)
        lines.append(f"public class {wrapper} {{")
        for _ in range(n_methods):
            mname = draw(method_name)
            lines.append(f"    public void {mname}() {{ }}")
        lines.append("}")

        # Additional top-level classes
        for _ in range(n_classes):
            cname = draw(class_name)
            lines.append(f"class {cname} {{ }}")

        code = "\n".join(lines)
        # n_methods are inside wrapper class (method_declaration nodes)
        # n_classes are top-level + 1 wrapper = n_classes + 1 class_declaration nodes
        return code, n_methods, n_classes + 1

    return _build()


def java_code_with_imports_strategy():
    """Gera código Java com imports e pelo menos um método ou classe."""
    import_name = st.from_regex(r"[a-z][a-z]{1,5}\.[A-Z][a-zA-Z]{1,8}", fullmatch=True)

    @st.composite
    def _build(draw):
        n_imports = draw(st.integers(min_value=1, max_value=4))
        imports = [draw(import_name) for _ in range(n_imports)]
        import_lines = "\n".join(f"import {imp};" for imp in imports)
        code = f"{import_lines}\npublic class MyClass {{\n    public void myMethod() {{ }}\n}}"
        return code, imports

    return _build()


def jsx_code_strategy():
    """Gera código JSX com function_declaration e/ou arrow_function."""
    func_name = st.from_regex(r"[A-Z][a-zA-Z0-9]{1,8}", fullmatch=True)

    @st.composite
    def _build(draw):
        n_funcs = draw(st.integers(min_value=1, max_value=3))
        lines = []
        for _ in range(n_funcs):
            fname = draw(func_name)
            lines.append(f"function {fname}() {{ return null; }}")
        code = "\n".join(lines)
        return code, n_funcs

    return _build()


def html_code_strategy():
    """Gera documentos HTML com N elementos de nível superior."""
    tag_name = st.sampled_from(["div", "p", "section", "article", "header", "footer", "main"])

    @st.composite
    def _build(draw):
        n_elements = draw(st.integers(min_value=1, max_value=4))
        lines = []
        for _ in range(n_elements):
            tag = draw(tag_name)
            lines.append(f"<{tag}>content</{tag}>")
        code = "\n".join(lines)
        return code, n_elements

    return _build()


def cfml_code_strategy():
    """Gera arquivos CFML com N tags cfquery."""

    @st.composite
    def _build(draw):
        n_queries = draw(st.integers(min_value=1, max_value=3))
        lines = []
        for i in range(n_queries):
            lines.append(f'<cfquery name="q{i}" datasource="ds">SELECT id FROM table{i}</cfquery>')
        code = "\n".join(lines)
        return code, n_queries

    return _build()


def sql_code_strategy():
    """Gera arquivos SQL com N statements DDL ou DML."""
    ddl_statements = [
        "CREATE TABLE foo (id INT)",
        "ALTER TABLE foo ADD COLUMN name VARCHAR(100)",
        "DROP TABLE foo",
    ]
    dml_statements = [
        "SELECT id FROM foo",
        "INSERT INTO foo (id) VALUES (1)",
        "UPDATE foo SET id = 2",
        "DELETE FROM foo WHERE id = 1",
    ]

    @st.composite
    def _build(draw):
        n_stmts = draw(st.integers(min_value=1, max_value=4))
        all_stmts = ddl_statements + dml_statements
        stmts = [draw(st.sampled_from(all_stmts)) for _ in range(n_stmts)]
        code = ";\n".join(stmts) + ";"
        return code, n_stmts

    return _build()


def sql_statement_strategy():
    """Gera um único statement SQL com seu tipo esperado (ddl ou dml)."""
    ddl = [
        ("CREATE TABLE t (id INT)", "ddl_statement"),
        ("ALTER TABLE t ADD COLUMN x INT", "ddl_statement"),
        ("DROP TABLE t", "ddl_statement"),
    ]
    dml = [
        ("SELECT * FROM t", "dml_statement"),
        ("INSERT INTO t (id) VALUES (1)", "dml_statement"),
        ("UPDATE t SET id = 2", "dml_statement"),
        ("DELETE FROM t WHERE id = 1", "dml_statement"),
    ]
    return st.sampled_from(ddl + dml)


def code_block_list_strategy():
    """Gera listas de Code_Blocks com embeddings mock de 3072 dims."""
    from models.code_block import Code_Block

    @st.composite
    def _build(draw):
        n = draw(st.integers(min_value=1, max_value=5))
        blocks = []
        for i in range(n):
            start = draw(st.integers(min_value=1, max_value=100))
            end = draw(st.integers(min_value=start, max_value=start + 50))
            blocks.append(
                Code_Block(
                    node_type="method_declaration",
                    language="java",
                    content=f"void method{i}() {{}}",
                    start_line=start,
                    end_line=end,
                    metadata={},
                )
            )
        embeddings = [[0.0] * 3072 for _ in range(n)]
        return blocks, embeddings

    return _build()


def directory_structure_strategy():
    """Gera estruturas de diretório com arquivos suportados e não suportados.

    Retorna (supported_files: list[str], unsupported_files: list[str]) —
    caminhos relativos a serem criados no tmp_path do pytest.
    """
    supported_ext = st.sampled_from(SUPPORTED_EXTENSIONS)
    unsupported_ext = st.from_regex(r"\.[a-z]{2,5}", fullmatch=True).filter(
        lambda e: e not in set(SUPPORTED_EXTENSIONS)
    )
    filename = st.from_regex(r"[a-z][a-z0-9]{1,8}", fullmatch=True)
    subdir = st.from_regex(r"[a-z][a-z0-9]{1,6}", fullmatch=True)

    @st.composite
    def _build(draw):
        n_supported = draw(st.integers(min_value=0, max_value=5))
        n_unsupported = draw(st.integers(min_value=0, max_value=3))

        supported_files = []
        for _ in range(n_supported):
            depth = draw(st.integers(min_value=0, max_value=2))
            parts = [draw(subdir) for _ in range(depth)] + [
                draw(filename) + draw(supported_ext)
            ]
            supported_files.append("/".join(parts))

        unsupported_files = []
        for _ in range(n_unsupported):
            depth = draw(st.integers(min_value=0, max_value=2))
            parts = [draw(subdir) for _ in range(depth)] + [
                draw(filename) + draw(unsupported_ext)
            ]
            unsupported_files.append("/".join(parts))

        return supported_files, unsupported_files

    return _build()


def job_summary_strategy():
    """Gera sumários de job com contagens variadas para verificar consistência interna.

    Retorna um dict com as métricas do job.
    """

    @st.composite
    def _build(draw):
        files_processed = draw(st.integers(min_value=0, max_value=100))
        files_skipped = draw(st.integers(min_value=0, max_value=100))
        files_failed = draw(st.integers(min_value=0, max_value=100))
        # files_discovered >= files_processed + files_skipped + files_failed
        total = files_processed + files_skipped + files_failed
        extra = draw(st.integers(min_value=0, max_value=20))
        files_discovered = total + extra
        blocks_inserted = draw(st.integers(min_value=0, max_value=500))
        elapsed_seconds = draw(st.floats(min_value=0.0, max_value=3600.0, allow_nan=False))

        return {
            "files_discovered": files_discovered,
            "files_processed": files_processed,
            "files_skipped": files_skipped,
            "files_failed": files_failed,
            "blocks_inserted": blocks_inserted,
            "elapsed_seconds": elapsed_seconds,
        }

    return _build()


def any_log_event_strategy():
    """Gera eventos de log variados: (level_name, message, extra_dict)."""
    level_strategy = st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    message_strategy = st.text(min_size=0, max_size=200)
    extra_strategy = st.fixed_dictionaries({}).flatmap(
        lambda _: st.dictionaries(
            keys=st.text(min_size=1, max_size=20).filter(
                lambda k: k.isidentifier() and k not in {
                    "name", "msg", "args", "levelname", "levelno", "pathname",
                    "filename", "module", "exc_info", "exc_text", "stack_info",
                    "lineno", "funcName", "created", "msecs", "relativeCreated",
                    "thread", "threadName", "processName", "process", "message",
                    "taskName",
                }
            ),
            values=st.one_of(st.text(max_size=50), st.integers(), st.floats(allow_nan=False)),
            max_size=5,
        )
    )
    return st.tuples(level_strategy, message_strategy, extra_strategy)


def file_processing_event_strategy():
    """Gera eventos de processamento de arquivo com campos obrigatórios."""
    return st.fixed_dictionaries({
        "file_path": st.text(min_size=1, max_size=200),
        "blocks_extracted": st.integers(min_value=0, max_value=1000),
        "embeddings_generated": st.integers(min_value=0, max_value=1000),
        "status": st.sampled_from(["success", "skipped", "failed"]),
    })
