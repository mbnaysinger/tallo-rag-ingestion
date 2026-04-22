"""
Edge case tests for error handling.

Verifica:
  - DB offline → RuntimeError descritivo
  - file_path inexistente → lista vazia
"""
import sys
import types
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import psycopg

# Garante que a raiz do repositório está no sys.path
_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _make_settings_mock():
    s = MagicMock()
    s.openai_api_key = "test-key"
    s.azure_openai_endpoint = None
    s.azure_openai_api_version = "2023-05-15"
    s.azure_openai_deployment = "text-embedding-3-large"
    return s


def _make_fastmcp_mock():
    fastmcp_mod = types.ModuleType("fastmcp")

    class _FakeFastMCP:
        def __init__(self, name, version=None):
            self.name = name
            self.version = version
            self._tools = {}

        def tool(self):
            def decorator(fn):
                self._tools[fn.__name__] = fn
                return fn
            return decorator

        def run(self, transport=None):
            pass

    fastmcp_mod.FastMCP = _FakeFastMCP
    return fastmcp_mod


def _load_server_with_mocks(embedding_client_mock, vector_store_mock):
    settings_mock = _make_settings_mock()
    fastmcp_mock = _make_fastmcp_mock()

    for key in list(sys.modules.keys()):
        if key in ("tallo_mcp.server",):
            del sys.modules[key]

    sys.modules["fastmcp"] = fastmcp_mock

    with (
        patch("tallo_mcp.config.load_mcp_settings", return_value=settings_mock),
        patch("tallo_mcp.db.MCP_VectorStore", return_value=vector_store_mock),
        patch("pipeline.embedding_client.Embedding_Client", return_value=embedding_client_mock),
    ):
        import tallo_mcp.server as server_mod
        importlib.reload(server_mod)
        server_mod._embedding_client = embedding_client_mock
        server_mod._vector_store = vector_store_mock

    return server_mod


# ---------------------------------------------------------------------------
# DB offline → RuntimeError descritivo (Requirement 5.4)
# ---------------------------------------------------------------------------

def test_search_code_db_offline_raises_runtime_error():
    """search_code deve propagar erro quando DB está offline."""
    embedding_client_mock = MagicMock()
    embedding_client_mock.embed_batch.return_value = [[0.0] * 3072]

    vector_store_mock = MagicMock()
    # Simula DB offline: get_connection levanta OperationalError
    vector_store_mock.get_connection.side_effect = psycopg.OperationalError(
        "connection refused"
    )

    server_mod = _load_server_with_mocks(embedding_client_mock, vector_store_mock)

    with pytest.raises(psycopg.OperationalError):
        server_mod.search_code(query="test query", limit=5)


def test_get_file_blocks_db_offline_raises_error():
    """get_file_blocks deve propagar erro quando DB está offline."""
    embedding_client_mock = MagicMock()
    vector_store_mock = MagicMock()
    vector_store_mock.get_connection.side_effect = psycopg.OperationalError(
        "connection refused"
    )

    server_mod = _load_server_with_mocks(embedding_client_mock, vector_store_mock)

    with pytest.raises(psycopg.OperationalError):
        server_mod.get_file_blocks(file_path="/some/file.py")


def test_list_indexed_files_db_offline_raises_error():
    """list_indexed_files deve propagar erro quando DB está offline."""
    embedding_client_mock = MagicMock()
    vector_store_mock = MagicMock()
    vector_store_mock.get_connection.side_effect = psycopg.OperationalError(
        "connection refused"
    )

    server_mod = _load_server_with_mocks(embedding_client_mock, vector_store_mock)

    with pytest.raises(psycopg.OperationalError):
        server_mod.list_indexed_files()


# ---------------------------------------------------------------------------
# file_path inexistente → lista vazia (Requirement 2.4)
# ---------------------------------------------------------------------------

def test_get_file_blocks_nonexistent_file_path_returns_empty_list():
    """get_file_blocks com file_path inexistente deve retornar lista vazia."""
    embedding_client_mock = MagicMock()
    vector_store_mock = MagicMock()

    conn_mock = MagicMock()
    conn_mock.__enter__ = MagicMock(return_value=conn_mock)
    conn_mock.__exit__ = MagicMock(return_value=False)
    vector_store_mock.get_connection.return_value = conn_mock
    vector_store_mock.get_file_blocks.return_value = []

    server_mod = _load_server_with_mocks(embedding_client_mock, vector_store_mock)

    result = server_mod.get_file_blocks(file_path="/nonexistent/path/file.py")

    assert result == [], f"Esperado lista vazia para file_path inexistente, got: {result}"
