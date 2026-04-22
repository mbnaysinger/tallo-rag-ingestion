"""
Property-based tests for mcp/server.py tools.

Properties covered:
  - Property 1: Embedding gerado para qualquer query não-vazia
  - Property 5: Limite inválido é rejeitado com erro descritivo
"""
import sys
import json
import types
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings as hyp_settings, strategies as st

# Garante que a raiz do repositório está no sys.path
_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings_mock():
    s = MagicMock()
    s.openai_api_key = "test-key"
    s.azure_openai_endpoint = None
    s.azure_openai_api_version = "2023-05-15"
    s.azure_openai_deployment = "text-embedding-3-large"
    return s


def _make_fastmcp_mock():
    """Cria um módulo fastmcp falso com FastMCP que registra tools via decorator."""
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
    """
    Carrega mcp.server com todas as dependências externas mockadas.
    Retorna o módulo recarregado.
    """
    settings_mock = _make_settings_mock()
    fastmcp_mock = _make_fastmcp_mock()

    for key in list(sys.modules.keys()):
        if key in ("tallo_mcp.server",):
            del sys.modules[key]

    # Injeta fastmcp falso no sys.modules
    sys.modules["fastmcp"] = fastmcp_mock

    with (
        patch("tallo_mcp.config.load_mcp_settings", return_value=settings_mock),
        patch("tallo_mcp.db.MCP_VectorStore", return_value=vector_store_mock),
        patch("pipeline.embedding_client.Embedding_Client", return_value=embedding_client_mock),
    ):
        import tallo_mcp.server as server_mod
        importlib.reload(server_mod)
        # Substitui instâncias de módulo pelos mocks
        server_mod._embedding_client = embedding_client_mock
        server_mod._vector_store = vector_store_mock

    return server_mod


# ---------------------------------------------------------------------------
# Property 1: Embedding gerado para qualquer query não-vazia
# ---------------------------------------------------------------------------

@hyp_settings(max_examples=100, deadline=None)
@given(query=st.text(min_size=1))
def test_property_1_embedding_called_once_for_any_nonempty_query(query):
    """
    **Validates: Requirements 1.2**

    Property 1: Para qualquer string não-vazia fornecida como query ao search_code,
    o Embedding_Client deve ser invocado exatamente uma vez e o vetor resultante
    deve ter exatamente 3072 dimensões.
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

    server_mod = _load_server_with_mocks(embedding_client_mock, vector_store_mock)

    server_mod.search_code(query=query, limit=10)

    # embed_batch deve ter sido chamado exatamente uma vez com a query
    embedding_client_mock.embed_batch.assert_called_once_with([query])

    # O vetor passado para cosine_search deve ter 3072 dimensões
    call_args = vector_store_mock.cosine_search.call_args
    passed_vector = call_args[0][1]  # segundo argumento posicional
    assert len(passed_vector) == 3072, (
        f"Expected vector with 3072 dims, got {len(passed_vector)}"
    )


# ---------------------------------------------------------------------------
# Property 5: Limite inválido é rejeitado com erro descritivo
# ---------------------------------------------------------------------------

@hyp_settings(max_examples=100, deadline=None)
@given(limit=st.one_of(st.integers(max_value=0), st.integers(min_value=51)))
def test_property_5_invalid_limit_raises_value_error(limit):
    """
    **Validates: Requirements 1.8**

    Property 5: Para qualquer inteiro limit menor que 1 ou maior que 50,
    search_code deve levantar ValueError sem executar a busca no banco.
    """
    embedding_client_mock = MagicMock()
    vector_store_mock = MagicMock()

    server_mod = _load_server_with_mocks(embedding_client_mock, vector_store_mock)

    with pytest.raises(ValueError):
        server_mod.search_code(query="some query", limit=limit)

    # A busca no banco NÃO deve ter sido executada
    vector_store_mock.cosine_search.assert_not_called()
    # O embedding NÃO deve ter sido gerado
    embedding_client_mock.embed_batch.assert_not_called()
