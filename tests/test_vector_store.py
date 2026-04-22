"""
Testes de propriedade para pipeline/vector_store.py usando mocks de psycopg.

Property 17: insert_batch chama cur.execute exatamente N vezes para N blocos.
Property 3:  hash_exists executa a query correta (round-trip de deduplicação via mock).
"""
import json
from unittest.mock import MagicMock, patch, call

import pytest
from hypothesis import given, settings, strategies as st

from pipeline.vector_store import Vector_Store
from tests.strategies import code_block_list_strategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(**overrides):
    """Cria um objeto Settings-like simples para testes."""
    defaults = dict(
        db_host="localhost",
        db_port=5432,
        db_name="testdb",
        db_user="user",
        db_password="pass",
        openai_api_key="key",
        sql_dialect="unknown",
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


def _make_mock_conn():
    """Retorna um mock de psycopg.Connection com cursor context-manager."""
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    return mock_conn, mock_cursor


# ---------------------------------------------------------------------------
# Property 17: insert_batch chama cur.execute exatamente N vezes para N blocos
# Validates: Requirements 5.1, 5.3
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(code_block_list_strategy())
def test_property_17_insert_batch_calls_execute_n_times(blocks_and_embeddings):
    """
    **Validates: Requirements 5.1, 5.3**

    Property 17: insert_batch insere exatamente N registros para N blocos.
    Verifica via mock que cur.execute é chamado exatamente N vezes.
    """
    blocks, embeddings = blocks_and_embeddings
    n = len(blocks)

    mock_conn, mock_cursor = _make_mock_conn()
    vs = Vector_Store(_make_settings())

    vs.insert_batch(mock_conn, blocks, embeddings, "/some/file.java", "abc123")

    assert mock_cursor.execute.call_count == n, (
        f"Esperado {n} chamadas a execute, obtido {mock_cursor.execute.call_count}"
    )
    mock_conn.commit.assert_called_once()


@settings(max_examples=100)
@given(code_block_list_strategy())
def test_property_17_insert_batch_metadata_contains_sha256(blocks_and_embeddings):
    """
    **Validates: Requirements 5.1, 5.3, 5.4**

    Verifica que o metadata passado em cada INSERT contém o file_sha256 correto
    e os campos obrigatórios (node_type, language, start_line, end_line).
    """
    blocks, embeddings = blocks_and_embeddings
    sha256 = "deadbeef" * 8  # 64 chars

    mock_conn, mock_cursor = _make_mock_conn()
    vs = Vector_Store(_make_settings())

    vs.insert_batch(mock_conn, blocks, embeddings, "/repo/file.java", sha256)

    for idx, call_args in enumerate(mock_cursor.execute.call_args_list):
        # call_args.args[1] is the tuple of parameters: (content, file_path, metadata_json, embedding)
        params = call_args.args[1]
        metadata = json.loads(params[2])

        assert metadata["file_sha256"] == sha256, f"Block {idx}: file_sha256 incorreto"
        assert "node_type" in metadata, f"Block {idx}: node_type ausente"
        assert "language" in metadata, f"Block {idx}: language ausente"
        assert "start_line" in metadata, f"Block {idx}: start_line ausente"
        assert "end_line" in metadata, f"Block {idx}: end_line ausente"


def test_insert_batch_rollback_on_exception():
    """Verifica que rollback é chamado e exceção é propagada em caso de erro."""
    from models.code_block import Code_Block

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.execute.side_effect = RuntimeError("DB error")

    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=mock_cursor)

    vs = Vector_Store(_make_settings())
    block = Code_Block("method_declaration", "java", "void m(){}", 1, 1)

    with pytest.raises(RuntimeError, match="DB error"):
        vs.insert_batch(mock_conn, [block], [[0.0] * 3072], "/f.java", "abc")

    mock_conn.rollback.assert_called_once()
    mock_conn.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Property 3: round-trip de deduplicação via mock
# Validates: Requirements 2.2, 2.5
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(st.text(min_size=1, max_size=64, alphabet="0123456789abcdef"))
def test_property_3_hash_exists_executes_correct_query(sha256_hex):
    """
    **Validates: Requirements 2.2, 2.5**

    Property 3: Round-trip de deduplicação.
    Verifica que hash_exists executa a query correta com o sha256_hex fornecido.
    Quando fetchone retorna um resultado, hash_exists deve retornar True.
    """
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.return_value = (1,)  # simula registro encontrado

    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=mock_cursor)

    vs = Vector_Store(_make_settings())
    result = vs.hash_exists(mock_conn, sha256_hex)

    assert result is True

    # Verifica que a query correta foi executada com o parâmetro correto
    mock_cursor.execute.assert_called_once()
    call_args = mock_cursor.execute.call_args
    query = call_args.args[0]
    params = call_args.args[1]

    assert "metadata->>'file_sha256'" in query
    assert "code_embeddings" in query
    assert params == (sha256_hex,)


@settings(max_examples=100)
@given(st.text(min_size=1, max_size=64, alphabet="0123456789abcdef"))
def test_property_3_hash_exists_returns_false_when_not_found(sha256_hex):
    """
    **Validates: Requirements 2.2**

    Verifica que hash_exists retorna False quando fetchone retorna None.
    """
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.return_value = None  # nenhum registro encontrado

    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=mock_cursor)

    vs = Vector_Store(_make_settings())
    result = vs.hash_exists(mock_conn, sha256_hex)

    assert result is False
