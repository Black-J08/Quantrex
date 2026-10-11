"""Quantrex algorithmic trading framework.

This package loads environment variables from .env on import,
ensuring configuration is available whenever the framework is used.
"""

from __future__ import annotations

from dotenv import load_dotenv

# Load environment variables from .env file
# This runs on every import, ensuring fresh environment
load_dotenv()

__version__ = "0.2.0"
