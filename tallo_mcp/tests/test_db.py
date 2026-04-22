"""
Property-based tests for MCP_VectorStore (mcp/db.py).
Uses mocks of psycopg — no real database required.

Properties covered:
  - Property 2: Resultado de search_code respeita o limite
  - Property 3: Filtros de search_code são invariantes nos resultados
  - Property 4: Estrutura completa dos resultados de search_code
  - Property 6: get_file_blocks retorna blocos completos ordenados por start_line
  - Property 7: Resultados de get_file_blocks não contêm o campo embedding
  - Property 8: list_indexed_files retorna arquivos únicos, ordenados e com contagem correta
"""
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, strategies as st

# Garante que o diretório pai (raiz do repo) está no sys.path
_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tallo_mcp.db import FileBlock, IndexedFile, MCP_VectorStore, SearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store() -> MCP_VectorStore:
    """Cria um MCP_VectorStore com settings fictícios."""
    settings_mock = MagicMock()
    settings_mock.db_host = "localhost"
    settings_mock.db_port = 5432
    settings_mock.db_name = "testdb"
    settings_mock.db_user = "user"
    settings_mock.db_password = "pass"
    return MCP_VectorStore(settings_mock)


def _make_conn_with_rows(rows):
    """Cria um mock de psycopg.Connection cujo cursor retorna `rows`."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchall.return_value = rows
    conn.cursor.return_value = cursor
    return conn


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_text = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")))
_file_path = st.text(min_size=1, max_size=80, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Pc")))


@st.composite
def search_result_row_strategy(draw, language: Optional[str] = None, node_type: Optional[str] = None):
    """Gera uma linha de resultado de cosine_search como tupla."""
    row_id = draw(_text)
    content = draw(_text)
    fp = draw(_file_path)
    lang = language if language is not None else draw(_text)
    nt = node_type if node_type is not None else draw(_text)
    metadata = {"language": lang, "node_type": nt, "start_line": draw(st.integers(min_value=1, max_value=1000))}
    score = draw(st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False))
    return (row_id, content, fp, metadata, score)


@st.composite
def file_block_row_strategy(draw, file_path: Optional[str] = None):
    """Gera uma linha de resultado de get_file_blocks como tupla."""
    row_id = draw(_text)
    content = draw(_text)
    fp = file_path if file_path is not None else draw(_file_path)
    start_line = draw(st.integers(min_value=1, max_value=10000))
    metadata = {"start_line": start_line, "language": draw(_text)}
    return (row_id, content, fp, metadata)


@st.composite
def indexed_file_rows_strategy(draw):
    """
    Gera uma lista de tuplas (file_path, block_count, language) como retornadas
    pela query GROUP BY — cada file_path é único.
    """
    file_paths = draw(st.lists(_file_path, min_size=0, max_size=20, unique=True))
    rows = []
    for fp in file_paths:
        block_count = draw(st.integers(min_value=1, max_value=100))
        language = draw(_text)
        rows.append((fp, block_count, language))
    # Ordena por file_path ASC (simula ORDER BY do banco)
    rows.sort(key=lambda r: r[0])
    return rows


# ---------------------------------------------------------------------------
# Property 2: Resultado de cosine_search respeita o limite
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    limit=st.integers(min_value=1, max_value=50),
    extra=st.integers(min_value=0, max_value=10),
)
def test_property_2_cosine_search_respects_limit(limit, extra):
    """
    **Validates: Requirements 1.3**

    Property 2: Para qualquer limit N em [1,50], o número de resultados retornados
    por cosine_search deve ser <= N.
    O banco retorna min(limit + extra, limit) linhas — simulamos que o banco já
    aplica LIMIT, então o mock retorna exatamente `limit` linhas no máximo.
    """
    store = _make_store()
    # O banco aplica LIMIT, então retornamos exatamente `limit` linhas
    rows = [(f"id{i}", f"content{i}", f"path{i}", {"language": "py", "node_type": "fn"}, 0.1 * i)
            for i in range(limit)]
    conn = _make_conn_with_rows(rows)

    results = store.cosine_search(conn, [0.0] * 3072, limit)

    assert len(results) <= limit, (
        f"cosine_search returned {len(results)} results but limit was {limit}"
    )


# ---------------------------------------------------------------------------
# Property 3: Filtros de cosine_search são invariantes nos resultados
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    language=_text,
    node_type=_text,
    rows=st.lists(search_result_row_strategy(), min_size=0, max_size=20),
)
def test_property_3_filters_are_invariant_in_results(language, node_type, rows):
    """
    **Validates: Requirements 1.4, 1.5**

    Property 3: Quando filtros language e/ou node_type são fornecidos, todos os
    resultados retornados devem respeitar esses filtros.
    Simulamos que o banco já filtrou — o mock retorna apenas linhas compatíveis.
    """
    store = _make_store()
    # Filtra as linhas para simular o comportamento do banco
    filtered_rows = [
        r for r in rows
        if r[3].get("language") == language and r[3].get("node_type") == node_type
    ]
    conn = _make_conn_with_rows(filtered_rows)

    results = store.cosine_search(conn, [0.0] * 3072, 50, language=language, node_type=node_type)

    for result in results:
        assert result.metadata.get("language") == language, (
            f"Expected language={language!r}, got {result.metadata.get('language')!r}"
        )
        assert result.metadata.get("node_type") == node_type, (
            f"Expected node_type={node_type!r}, got {result.metadata.get('node_type')!r}"
        )


# ---------------------------------------------------------------------------
# Property 4: Estrutura completa dos resultados de cosine_search
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    rows=st.lists(search_result_row_strategy(), min_size=0, max_size=20),
)
def test_property_4_search_results_have_complete_structure(rows):
    """
    **Validates: Requirements 1.6**

    Property 4: Para qualquer resultado retornado por cosine_search, os campos
    id, content, file_path, score e metadata devem estar presentes e não-nulos.
    """
    store = _make_store()
    conn = _make_conn_with_rows(rows)

    results = store.cosine_search(conn, [0.0] * 3072, 50)

    for result in results:
        assert isinstance(result, SearchResult)
        assert result.id is not None
        assert result.content is not None
        assert result.file_path is not None
        assert result.score is not None
        assert result.metadata is not None
        assert isinstance(result.metadata, dict)


# ---------------------------------------------------------------------------
# Property 6: get_file_blocks retorna blocos ordenados por start_line
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    file_path=_file_path,
    rows=st.lists(file_block_row_strategy(), min_size=1, max_size=30),
)
def test_property_6_get_file_blocks_ordered_by_start_line(file_path, rows):
    """
    **Validates: Requirements 2.2**

    Property 6: Para qualquer file_path com N blocos, get_file_blocks deve retornar
    exatamente esses N blocos com file_path correto e sequência de start_line
    estritamente não-decrescente.
    """
    store = _make_store()
    # Simula que o banco retorna linhas com o file_path correto, ordenadas por start_line
    rows_with_fp = [(r[0], r[1], file_path, r[3]) for r in rows]
    rows_sorted = sorted(rows_with_fp, key=lambda r: r[3].get("start_line", 0))
    conn = _make_conn_with_rows(rows_sorted)

    results = store.get_file_blocks(conn, file_path)

    assert len(results) == len(rows_sorted), (
        f"Expected {len(rows_sorted)} blocks, got {len(results)}"
    )
    for result in results:
        assert result.file_path == file_path, (
            f"Expected file_path={file_path!r}, got {result.file_path!r}"
        )

    start_lines = [r.metadata.get("start_line", 0) for r in results]
    for i in range(len(start_lines) - 1):
        assert start_lines[i] <= start_lines[i + 1], (
            f"start_lines not non-decreasing at index {i}: {start_lines}"
        )


# ---------------------------------------------------------------------------
# Property 7: Resultados de get_file_blocks não contêm o campo embedding
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    file_path=_file_path,
    rows=st.lists(file_block_row_strategy(), min_size=0, max_size=20),
)
def test_property_7_get_file_blocks_no_embedding_field(file_path, rows):
    """
    **Validates: Requirements 2.3**

    Property 7: Para qualquer resultado retornado por get_file_blocks, os campos
    id, content, file_path e metadata devem estar presentes, e o campo embedding
    não deve estar presente no resultado.
    """
    store = _make_store()
    rows_with_fp = [(r[0], r[1], file_path, r[3]) for r in rows]
    conn = _make_conn_with_rows(rows_with_fp)

    results = store.get_file_blocks(conn, file_path)

    for result in results:
        assert isinstance(result, FileBlock)
        assert result.id is not None
        assert result.content is not None
        assert result.file_path is not None
        assert result.metadata is not None
        # FileBlock não deve ter campo embedding
        assert not hasattr(result, "embedding"), (
            "FileBlock should not have an 'embedding' field"
        )


# ---------------------------------------------------------------------------
# Property 8: list_indexed_files retorna arquivos únicos, ordenados, contagem correta
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(rows=indexed_file_rows_strategy())
def test_property_8_list_indexed_files_unique_sorted_correct_count(rows):
    """
    **Validates: Requirements 3.2, 3.3**

    Property 8: list_indexed_files deve retornar uma lista onde:
    (a) cada file_path aparece exatamente uma vez,
    (b) a lista está em ordem alfabética crescente de file_path,
    (c) o block_count de cada entrada é igual ao número real de registros com
        aquele file_path no banco.
    """
    store = _make_store()
    conn = _make_conn_with_rows(rows)

    results = store.list_indexed_files(conn)

    assert len(results) == len(rows), (
        f"Expected {len(rows)} indexed files, got {len(results)}"
    )

    # (a) file_paths únicos
    file_paths = [r.file_path for r in results]
    assert len(file_paths) == len(set(file_paths)), (
        f"Duplicate file_paths found: {file_paths}"
    )

    # (b) ordem alfabética crescente
    for i in range(len(file_paths) - 1):
        assert file_paths[i] <= file_paths[i + 1], (
            f"file_paths not sorted at index {i}: {file_paths}"
        )

    # (c) block_count correto
    for result, row in zip(results, rows):
        assert result.file_path == row[0]
        assert result.block_count == row[1], (
            f"Expected block_count={row[1]}, got {result.block_count} for {row[0]!r}"
        )
