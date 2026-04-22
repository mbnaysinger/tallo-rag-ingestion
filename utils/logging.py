"""
Structured JSON logging for the Tallo RAG Ingestion Service.

Usage:
    from utils.logging import get_logger
    logger = get_logger(__name__)
    logger.info("File processed", extra={"file_path": "/path/to/file.java", "blocks_extracted": 5, "status": "success"})
"""

import json
import logging
import logging.config
import datetime
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Formats each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        # Base fields required by the spec
        log_entry: dict[str, Any] = {
            "timestamp": datetime.datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge any extra fields passed via extra={}
        # Standard LogRecord attributes to skip
        _skip = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in _skip:
                log_entry[key] = value

        # Append exception info if present
        if record.exc_info:
            log_entry["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str, ensure_ascii=False)


_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": _JsonFormatter,
        }
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "json",
        }
    },
    "root": {
        "handlers": ["stdout"],
        "level": "DEBUG",
    },
}

logging.config.dictConfig(_LOGGING_CONFIG)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured to emit structured JSON to stdout."""
    return logging.getLogger(name)
