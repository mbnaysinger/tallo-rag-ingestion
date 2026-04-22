"""
Edge case tests for empty/invalid inputs.

Verifica:
  - query vazia → ValueError
  - file_path vazio → ValueError
  - DB vazio → lista vazia
"""
import sys
import types
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


def _make_server():
    embedding_client_mock = MagicMock()
    vector_store_mock = MagicMock()

    conn_mock = MagicMock()
    conn_mock.__enter__ = MagicMock(return_value=conn_mock)
    conn_mock.__exit__ = MagicMock(return_value=False)
    vector_store_mock.get_connection.return_value = conn_mock

    return _load_server_with_mocks(embedding_client_mock, vector_store_mock), vector_store_mock


# ---------------------------------------------------------------------------
# query vazia → ValueError (Requirement 1.7)
# ---------------------------------------------------------------------------

def test_search_code_empty_query_raises_value_error():
    """search_code com query vazia deve levantar ValueError."""
    server_mod, _ = _make_server()
    with pytest.raises(ValueError, match="query"):
        server_mod.search_code(query="")


def test_search_code_whitespace_only_query_does_not_raise():
    """search_code com query de espaços não levanta ValueError (apenas string vazia é rejeitada)."""
    embedding_client_mock = MagicMock()
    embedding_client_mock.embed_batch.return_value = [[0.0] * 3072]

    vector_store_mock = MagicMock()
    conn_mock = MagicMock()
    conn_mock.__enter__ = MagicMock(return_value=conn_mock)
    conn_mock.__exit__ = MagicMock(return_value=False)
    vector_store_mock.get_connection.return_value = conn_mock
    vector_store_mock.cosine_search.return_value = []

    server_mod = _load_server_with_mocks(embedding_client_mock, vector_store_mock)
    # Whitespace-only query is not explicitly rejected — only empty string is
    result = server_mod.search_code(query="   ")
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# file_path vazio → ValueError (Requirement 2.5)
# ---------------------------------------------------------------------------

def test_get_file_blocks_empty_file_path_raises_value_error():
    """get_file_blocks com file_path vazio deve levantar ValueError."""
    server_mod, _ = _make_server()
    with pytest.raises(ValueError, match="file_path"):
        server_mod.get_file_blocks(file_path="")


# ---------------------------------------------------------------------------
# DB vazio → lista vazia (Requirement 3.4)
# ---------------------------------------------------------------------------

def test_list_indexed_files_empty_db_returns_empty_list():
    """list_indexed_files com DB vazio deve retornar lista vazia."""
    server_mod, vector_store_mock = _make_server()
    vector_store_mock.list_indexed_files.return_value = []

    result = server_mod.list_indexed_files()

    assert result == [], f"Esperado lista vazia, got: {result}"


def test_get_file_blocks_nonexistent_path_returns_empty_list():
    """get_file_blocks com file_path inexistente deve retornar lista vazia."""
    server_mod, vector_store_mock = _make_server()
    vector_store_mock.get_file_blocks.return_value = []

    result = server_mod.get_file_blocks(file_path="/nonexistent/path.py")

    assert result == [], f"Esperado lista vazia, got: {result}"


def test_search_code_empty_db_returns_empty_list():
    """search_code com DB vazio deve retornar lista vazia."""
    embedding_client_mock = MagicMock()
    embedding_client_mock.embed_batch.return_value = [[0.0] * 3072]

    vector_store_mock = MagicMock()
    conn_mock = MagicMock()
    conn_mock.__enter__ = MagicMock(return_value=conn_mock)
    conn_mock.__exit__ = MagicMock(return_value=False)
    vector_store_mock.get_connection.return_value = conn_mock
    vector_store_mock.cosine_search.return_value = []

    server_mod = _load_server_with_mocks(embedding_client_mock, vector_store_mock)

    result = server_mod.search_code(query="some query", limit=10)

    assert result == [], f"Esperado lista vazia, got: {result}"
