"""
Testes de configuração Azure OpenAI.

Verifica que Embedding_Client usa AzureOpenAI quando AZURE_OPENAI_ENDPOINT está definido.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Garante que a raiz do repositório está no sys.path
_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import openai
from pipeline.embedding_client import Embedding_Client


def test_embedding_client_uses_azure_when_endpoint_is_set():
    """Embedding_Client deve usar AzureOpenAI quando azure_endpoint está definido."""
    with patch("openai.AzureOpenAI") as mock_azure:
        client = Embedding_Client(
            api_key="test-key",
            azure_endpoint="https://my-resource.openai.azure.com/",
            api_version="2023-05-15",
            deployment_name="text-embedding-3-large",
        )
        mock_azure.assert_called_once_with(
            api_key="test-key",
            azure_endpoint="https://my-resource.openai.azure.com/",
            api_version="2023-05-15",
        )


def test_embedding_client_uses_openai_when_no_endpoint():
    """Embedding_Client deve usar OpenAI padrão quando azure_endpoint não está definido."""
    with patch("openai.OpenAI") as mock_openai:
        client = Embedding_Client(
            api_key="test-key",
            azure_endpoint=None,
        )
        mock_openai.assert_called_once_with(api_key="test-key")


def test_embedding_client_uses_openai_when_endpoint_is_empty_string():
    """Embedding_Client deve usar OpenAI padrão quando azure_endpoint é string vazia."""
    with patch("openai.OpenAI") as mock_openai:
        client = Embedding_Client(
            api_key="test-key",
            azure_endpoint="",
        )
        mock_openai.assert_called_once_with(api_key="test-key")


def test_embedding_client_azure_uses_default_api_version_when_none():
    """Embedding_Client Azure deve usar versão padrão quando api_version é None."""
    with patch("openai.AzureOpenAI") as mock_azure:
        client = Embedding_Client(
            api_key="test-key",
            azure_endpoint="https://my-resource.openai.azure.com/",
            api_version=None,
        )
        mock_azure.assert_called_once_with(
            api_key="test-key",
            azure_endpoint="https://my-resource.openai.azure.com/",
            api_version="2023-05-15",
        )
