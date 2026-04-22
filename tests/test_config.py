"""Tests for config.py — Settings dataclass and load_settings()."""
import os
import pytest
from unittest.mock import patch

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from config import REQUIRED_VARS, Settings, load_settings


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_settings_is_frozen():
    s = Settings(
        openai_api_key="key",
        db_host="localhost",
        db_port=5432,
        db_name="db",
        db_user="user",
        db_password="pass",
        sql_dialect="unknown",
    )
    with pytest.raises((AttributeError, TypeError)):
        s.openai_api_key = "other"  # type: ignore[misc]


def test_load_settings_success(monkeypatch):
    env = {
        "OPENAI_API_KEY": "sk-test",
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "mydb",
        "DB_USER": "admin",
        "DB_PASSWORD": "secret",
    }
    with patch.dict(os.environ, env, clear=True):
        s = load_settings()
    assert s.openai_api_key == "sk-test"
    assert s.db_port == 5432
    assert s.sql_dialect == "unknown"


def test_load_settings_with_sql_dialect(monkeypatch):
    env = {
        "OPENAI_API_KEY": "sk-test",
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "mydb",
        "DB_USER": "admin",
        "DB_PASSWORD": "secret",
        "SQL_DIALECT": "sybase",
    }
    with patch.dict(os.environ, env, clear=True):
        s = load_settings()
    assert s.sql_dialect == "sybase"


def test_load_settings_missing_all_raises():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(EnvironmentError) as exc_info:
            load_settings()
    msg = str(exc_info.value)
    for var in REQUIRED_VARS:
        assert var in msg


# ---------------------------------------------------------------------------
# Property 18: Variáveis obrigatórias ausentes causam EnvironmentError descritivo
# Validates: Requirements 6.2, 6.3
# ---------------------------------------------------------------------------

@h_settings(max_examples=100)
@given(st.frozensets(st.sampled_from(REQUIRED_VARS), min_size=1))
def test_property_18_missing_required_vars_raise_descriptive_error(missing_vars):
    """**Validates: Requirements 6.2, 6.3**

    For any non-empty subset of required variables that are absent,
    load_settings() must raise EnvironmentError whose message lists
    every missing variable.
    """
    # Build an env that has all required vars present, then remove the missing ones
    full_env = {
        "OPENAI_API_KEY": "sk-test",
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "mydb",
        "DB_USER": "admin",
        "DB_PASSWORD": "secret",
    }
    for var in missing_vars:
        full_env.pop(var, None)

    with patch.dict(os.environ, full_env, clear=True):
        with pytest.raises(EnvironmentError) as exc_info:
            load_settings()

    error_message = str(exc_info.value)
    for var in missing_vars:
        assert var in error_message, (
            f"Expected '{var}' to appear in error message, got: {error_message!r}"
        )
