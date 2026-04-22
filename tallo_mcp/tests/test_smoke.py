"""
Smoke tests for mcp/server.py.

Verifica que:
  - mcp.server é importável com mocks
  - As 3 tools estão registradas (search_code, get_file_blocks, list_indexed_files)
  - O nome do servidor é 'tallo-rag'
  - A versão é '1.0.0'
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


def _load_server():
    settings_mock = _make_settings_mock()
    fastmcp_mock = _make_fastmcp_mock()
    embedding_client_mock = MagicMock()
    vector_store_mock = MagicMock()

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


def test_server_is_importable():
    """mcp.server deve ser importável sem erros quando as dependências são mockadas."""
    server_mod = _load_server()
    assert server_mod is not None


def test_server_name_is_tallo_rag():
    """O nome do servidor MCP deve ser 'tallo-rag'."""
    server_mod = _load_server()
    assert server_mod.mcp.name == "tallo-rag"


def test_server_version_is_1_0_0():
    """A versão do servidor MCP deve ser '1.0.0'."""
    server_mod = _load_server()
    assert server_mod.mcp.version == "1.0.0"


def test_three_tools_are_registered():
    """As 3 tools (search_code, get_file_blocks, list_indexed_files) devem estar registradas."""
    server_mod = _load_server()
    registered = set(server_mod.mcp._tools.keys())
    expected = {"search_code", "get_file_blocks", "list_indexed_files"}
    assert expected == registered, (
        f"Tools registradas: {registered}, esperadas: {expected}"
    )


def test_search_code_tool_is_callable():
    """A tool search_code deve ser callable."""
    server_mod = _load_server()
    assert callable(server_mod.mcp._tools["search_code"])


def test_get_file_blocks_tool_is_callable():
    """A tool get_file_blocks deve ser callable."""
    server_mod = _load_server()
    assert callable(server_mod.mcp._tools["get_file_blocks"])


def test_list_indexed_files_tool_is_callable():
    """A tool list_indexed_files deve ser callable."""
    server_mod = _load_server()
    assert callable(server_mod.mcp._tools["list_indexed_files"])
