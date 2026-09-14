"""Logging configuration driven by ``LOG_LEVEL``.

Uses the standard library ``logging`` so no extra dependency is required.
Uvicorn's loggers are left to propagate to the root handler we configure.
Logs never include secrets: callers must pass sanitized/redacted values.
"""

from __future__ import annotations

import logging
import sys

from app.core.config import settings

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

# Loggers owned by uvicorn that should reuse our root handler.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def configure_logging(level: str | None = None) -> None:
    """Configure the root logger with the level from settings (or an override).

    Safe to call more than once; reconfiguration replaces the root handler.
    """
    level_name = (level or settings.log_level).upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))

    root = logging.getLogger()
    root.setLevel(level_name)
    root.handlers = [handler]

    # Let uvicorn's loggers bubble up to our root handler.
    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger for ``name`` (typically ``__name__``)."""
    return logging.getLogger(name)
