"""Quantrex algorithmic trading framework.

Call :func:`initialize` at application startup to load environment
variables from ``.env``. Environment loading is intentionally not
performed at import time so that importing the package does not have
side effects.
"""

from __future__ import annotations

from dotenv import load_dotenv

__version__ = "0.2.0"


def initialize() -> None:
    """Load environment variables from the ``.env`` file.

    Call this once at application startup. Safe to call multiple times.
    """
    load_dotenv()
