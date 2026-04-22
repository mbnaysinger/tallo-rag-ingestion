"""
Property-based tests for utils/logging.py.

Property 21: Logs são JSON válido parseável — Validates: Requirements 8.1
Property 22: Log de arquivo contém campos obrigatórios — Validates: Requirements 8.2
"""

import io
import json
import logging
import sys

import pytest
from hypothesis import given, settings, strategies as st

from utils.logging import get_logger, _JsonFormatter
from tests.strategies import any_log_event_strategy, file_processing_event_strategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _capture_log_line(level_name: str, message: str, extra: dict) -> str:
    """Emit one log record through _JsonFormatter and return the formatted line."""
    formatter = _JsonFormatter()
    level = getattr(logging, level_name)
    record = logging.LogRecord(
        name="test.logger",
        level=level,
        pathname=__file__,
        lineno=0,
        msg=message,
        args=(),
        exc_info=None,
    )
    # Attach extra fields manually (same as logging.Logger does internally)
    for k, v in extra.items():
        setattr(record, k, v)
    return formatter.format(record)


# ---------------------------------------------------------------------------
# Property 21: Logs são JSON válido parseável
# Validates: Requirements 8.1
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(any_log_event_strategy())
def test_property_21_logs_are_valid_json(event):
    """
    **Validates: Requirements 8.1**

    Property 21: For any log event, the emitted line must be valid, parseable JSON.
    """
    level_name, message, extra = event
    log_line = _capture_log_line(level_name, message, extra)

    # Must not raise
    parsed = json.loads(log_line)

    # Must be a dict (object), not an array or scalar
    assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# Property 22: Log de arquivo contém campos obrigatórios
# Validates: Requirements 8.2
# ---------------------------------------------------------------------------

REQUIRED_FILE_LOG_FIELDS = {"file_path", "blocks_extracted", "embeddings_generated", "status"}


@settings(max_examples=100)
@given(file_processing_event_strategy())
def test_property_22_file_log_contains_required_fields(event):
    """
    **Validates: Requirements 8.2**

    Property 22: When a file-processing event is logged, the emitted JSON must
    contain all required fields: file_path, blocks_extracted, embeddings_generated, status.
    """
    log_line = _capture_log_line("INFO", "File processed", event)
    parsed = json.loads(log_line)

    for field in REQUIRED_FILE_LOG_FIELDS:
        assert field in parsed, f"Required field '{field}' missing from log JSON"
        assert parsed[field] == event[field], (
            f"Field '{field}' value mismatch: expected {event[field]!r}, got {parsed[field]!r}"
        )
