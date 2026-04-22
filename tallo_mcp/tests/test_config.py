"""
Property 9: Variáveis obrigatórias ausentes causam EnvironmentError descritivo.
Validates: Requirements 4.2, 4.3
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings, strategies as st

# Garante que o diretório pai (raiz do repo) está no sys.path
_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config import REQUIRED_VARS


@settings(max_examples=100)
@given(st.frozensets(st.sampled_from(REQUIRED_VARS), min_size=1))
def test_property_9_missing_required_vars_raise_environment_error(missing_vars):
    """
    **Validates: Requirements 4.2, 4.3**

    Property 9: Para qualquer subconjunto não-vazio de variáveis obrigatórias ausentes,
    load_mcp_settings deve levantar EnvironmentError com mensagem que lista todas as
    variáveis ausentes.
    """
    # Constrói um ambiente com todas as variáveis obrigatórias presentes,
    # depois remove as que devem estar ausentes
    full_env = {
        "OPENAI_API_KEY": "test-key",
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "testdb",
        "DB_USER": "testuser",
        "DB_PASSWORD": "testpass",
    }
    env_without_missing = {k: v for k, v in full_env.items() if k not in missing_vars}

    with patch.dict(os.environ, env_without_missing, clear=True):
        # Impede que load_dotenv sobrescreva o ambiente controlado do teste
        with patch("config.load_dotenv"):
            from config import load_settings

            with pytest.raises(EnvironmentError) as exc_info:
                load_settings()

        error_message = str(exc_info.value)

        # Verifica que todas as variáveis ausentes estão mencionadas na mensagem de erro
        for var in missing_vars:
            assert var in error_message, (
                f"EnvironmentError message should mention missing variable '{var}', "
                f"but got: {error_message!r}"
            )
