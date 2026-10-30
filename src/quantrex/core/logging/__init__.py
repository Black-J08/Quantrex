"""Logging facade for Quantrex.

Provides a centralized logging configuration and logger factory so all
modules use consistent formatting, levels, and lazy %-formatting per
the project's logging standards in AGENTS.md.
"""

from __future__ import annotations

import logging
from typing import TextIO

_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_DEFAULT_LEVEL = logging.INFO

class _LoggingConfig:
    """Internal logging configuration state."""

    def __init__(self) -> None:
        self.configured = False


_config = _LoggingConfig()


def configure(
    level: int = _DEFAULT_LEVEL,
    format_string: str = _DEFAULT_FORMAT,
    stream: TextIO | None = None,
) -> None:
    """Configure the root logger for the Quantrex framework.

    Call this once at application startup. Safe to call multiple times —
    subsequent calls are no-ops after the first configuration.

    Args:
        level: Root logging level (default: INFO).
        format_string: Log message format string.
        stream: Output stream (default: sys.stderr).
    """
    if _config.configured:
        return

    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(format_string))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    _config.configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given module name.

    Modules should call ``get_logger(__name__)`` instead of
    ``logging.getLogger(__name__)`` so that logging configuration
    remains centralized behind this facade.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.

    Returns:
        A configured :class:`logging.Logger` instance.
    """
    return logging.getLogger(name)
