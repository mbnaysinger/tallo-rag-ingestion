"""
Property-based tests for MCP server logging.

Properties covered:
  - Property 10: Logs de invocação de tool são JSON válido com campos obrigatórios
"""
import sys
import json
import types
import logging
import importlib
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings as hyp_settings

# Garante que a raiz do repositório está no sys.path
_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tallo_mcp.tests.strategies import tool_invocation_strategy
from tallo_mcp.db import SearchResult, FileBlock, IndexedFile


# ---------------------------------------------------------------------------
# Helpers (mesmo padrão de test_server.py)
# ---------------------------------------------------------------------------

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


def _invoke_tool(server_mod, invocation: dict):
    """Invoca a tool correta com os parâmetros gerados pela estratégia."""
    tool_name = invocation["tool_name"]
    params = invocation["params"]

    if tool_name == "search_code":
        return server_mod.search_code(**params)
    elif tool_name == "get_file_blocks":
        return server_mod.get_file_blocks(**params)
    else:
        return server_mod.list_indexed_files()


# ---------------------------------------------------------------------------
# Property 10: Logs de invocação de tool são JSON válido com campos obrigatórios
# ---------------------------------------------------------------------------

@hyp_settings(max_examples=100, deadline=None)
@given(invocation=tool_invocation_strategy())
def test_property_10_tool_logs_are_valid_json_with_required_fields(invocation):
    """
    **Validates: Requirements 6.1, 6.2**

    Property 10: Para qualquer invocação de tool (search_code, get_file_blocks,
    list_indexed_files), a linha emitida para stderr deve ser um JSON válido e
    parseável contendo os campos tool_name, params e execution_ms.
    """
    fake_vector = [0.0] * 3072
    embedding_client_mock = MagicMock()
    embedding_client_mock.embed_batch.return_value = [fake_vector]

    conn_mock = MagicMock()
    conn_mock.__enter__ = MagicMock(return_value=conn_mock)
    conn_mock.__exit__ = MagicMock(return_value=False)

    vector_store_mock = MagicMock()
    vector_store_mock.get_connection.return_value = conn_mock
    vector_store_mock.cosine_search.return_value = []
    vector_store_mock.get_file_blocks.return_value = []
    vector_store_mock.list_indexed_files.return_value = []

    server_mod = _load_server_with_mocks(embedding_client_mock, vector_store_mock)

    # Captura o output do logger para stderr
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG)

    server_logger = logging.getLogger("tallo_mcp.server")
    original_handlers = server_logger.handlers[:]
    original_propagate = server_logger.propagate
    server_logger.handlers = [handler]
    server_logger.propagate = False
    server_logger.setLevel(logging.DEBUG)

    try:
        _invoke_tool(server_mod, invocation)
    finally:
        server_logger.handlers = original_handlers
        server_logger.propagate = original_propagate

    log_output = log_stream.getvalue().strip()
    assert log_output, "Nenhuma linha de log foi emitida para stderr"

    # Pega a última linha de log (pode haver múltiplas)
    last_line = log_output.split("\n")[-1].strip()
    assert last_line, "Última linha de log está vazia"

    # Deve ser JSON parseável
    try:
        record = json.loads(last_line)
    except json.JSONDecodeError as e:
        pytest.fail(
            f"Log não é JSON válido: {e!r}\nConteúdo: {last_line!r}"
        )

    # Deve conter os campos obrigatórios
    for field in ("tool_name", "params", "execution_ms"):
        assert field in record, (
            f"Campo obrigatório '{field}' ausente no log JSON.\n"
            f"Log: {record}"
        )

    # tool_name deve corresponder ao nome da tool invocada
    assert record["tool_name"] == invocation["tool_name"], (
        f"tool_name no log ({record['tool_name']!r}) não corresponde "
        f"ao esperado ({invocation['tool_name']!r})"
    )

    # execution_ms deve ser numérico e não-negativo
    assert isinstance(record["execution_ms"], (int, float)), (
        f"execution_ms deve ser numérico, got: {type(record['execution_ms'])}"
    )
    assert record["execution_ms"] >= 0, (
        f"execution_ms deve ser não-negativo, got: {record['execution_ms']}"
    )

    # params deve ser um dict
    assert isinstance(record["params"], dict), (
        f"params deve ser um dict, got: {type(record['params'])}"
    )
