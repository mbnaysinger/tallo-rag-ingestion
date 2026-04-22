"""
Property-based tests for Embedding_Client.

Property 15: embed_batch faz exatamente uma chamada à API para N blocos
Property 16: Vetores retornados têm dimensão 3072
"""
from unittest.mock import MagicMock, patch
from hypothesis import given, settings, strategies as st

from pipeline.embedding_client import Embedding_Client


def _make_mock_response(texts: list) -> MagicMock:
    """Build a mock OpenAI embeddings response with 3072-dim vectors."""
    response = MagicMock()
    response.data = [
        MagicMock(embedding=[0.0] * 3072) for _ in texts
    ]
    return response


# ---------------------------------------------------------------------------
# Property 15: embed_batch faz exatamente uma chamada à API para N blocos
# Validates: Requirements 4.1
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(st.lists(st.text(min_size=1), min_size=1, max_size=50))
def test_property_15_single_api_call(texts: list) -> None:
    """**Validates: Requirements 4.1**

    Property 15: embed_batch faz exatamente uma chamada à API para N blocos.
    Independentemente do tamanho da lista, a API deve ser chamada exatamente 1 vez.
    """
    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.embeddings.create.return_value = _make_mock_response(texts)

        client = Embedding_Client(api_key="test-key")
        client.embed_batch(texts)

        mock_client.embeddings.create.assert_called_once()


# ---------------------------------------------------------------------------
# Property 16: Vetores retornados têm dimensão 3072
# Validates: Requirements 4.2
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(st.lists(st.text(min_size=1), min_size=1, max_size=10))
def test_property_16_vector_dimension(texts: list) -> None:
    """**Validates: Requirements 4.2**

    Property 16: Vetores retornados têm dimensão 3072.
    Cada embedding retornado deve ter exatamente 3072 dimensões.
    """
    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.embeddings.create.return_value = _make_mock_response(texts)

        client = Embedding_Client(api_key="test-key")
        embeddings = client.embed_batch(texts)

        assert len(embeddings) == len(texts)
        for embedding in embeddings:
            assert len(embedding) == 3072
