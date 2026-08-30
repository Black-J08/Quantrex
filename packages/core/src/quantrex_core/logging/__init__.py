"""Centralized logging facade for the Quantrex framework.

This module is a thin wrapper around the standard library :mod:`logging`
package. It exposes a small, researcher-facing API:

- :func:`get_logger` — return a module-scoped logger.
- :func:`setup_logging` — apply a one-shot configuration to the root logger.

The module is **import-safe**: importing it never configures logging and
never installs handlers on the root logger. A single :class:`NullHandler`
is attached to the ``"quantrex"`` package logger on first import so that
library code can call ``logger.info(...)`` without producing the standard
"no handlers could be found" warning. This is the recipe recommended by
the Python ``logging`` HOWTO for libraries that don't own the application's
logging configuration.
"""

from __future__ import annotations

import logging
from logging.config import dictConfig
from pathlib import Path
from typing import Final

__all__ = [
    "DEFAULT_LEVEL",
    "get_logger",
    "setup_logging",
]

DEFAULT_LEVEL: Final[str] = "INFO"

# ---------------------------------------------------------------------------
# NullHandler attached to the "quantrex" package logger — library convention.
# See https://docs.python.org/3/howto/logging.html#configuring-logging-for-a-library
# ---------------------------------------------------------------------------

_quantrex_pkg_logger = logging.getLogger("quantrex")
if not any(isinstance(h, logging.NullHandler) for h in _quantrex_pkg_logger.handlers):
    _quantrex_pkg_logger.addHandler(logging.NullHandler())


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a stdlib logger scoped to *name* (or the ``quantrex`` package).

    Args:
        name: Logger name. ``None`` (the default) returns the ``"quantrex"``
            package logger. Pass ``__name__`` to get a module-scoped logger
            (e.g. ``"quantrex_backtest.core.engine"``) for hierarchical
            filtering and per-module level overrides.
    """
    if name is None:
        return logging.getLogger("quantrex")
    return logging.getLogger(name)


def setup_logging(
    *,
    level: str | int = DEFAULT_LEVEL,
    log_file: str | Path | None = None,
) -> None:
    """Configure the root logger with a stderr handler and (optionally) a file handler.

    Idempotent: a second call replaces the previous configuration cleanly
    because :func:`logging.config.dictConfig` removes existing handlers on
    the configured loggers before applying the new ones. Library loggers
    (urllib3, httpx, etc.) are preserved via
    ``disable_existing_loggers=False``.

    Args:
        level: Root log level. Accepts a string (``"DEBUG"``, ``"INFO"``,
            ``"WARNING"``, ...) or a numeric level.
        log_file: Optional path to a log file. When provided, a
            :class:`RotatingFileHandler` (10 MB × 5 backups, stdlib defaults)
            is attached in addition to the stderr handler.
    """
    handlers: dict[str, dict] = {
        "console": {
            "class": "logging.StreamHandler",
            "level": level,
            "formatter": "standard",
            "stream": "ext://sys.stderr",
        },
    }

    if log_file is not None:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": level,
            "formatter": "standard",
            "filename": str(Path(log_file).resolve()),
            "encoding": "utf-8",
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
        }

    config: dict = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            },
        },
        "handlers": handlers,
        "root": {
            "level": level,
            "handlers": list(handlers.keys()),
        },
    }

    dictConfig(config)
