"""Shared exceptions for Quantrex.

These exceptions are owned by neither the broker nor the data module.
Both modules import from here, keeping exception ownership neutral and
preserving clear module segregation.
"""

from __future__ import annotations

from typing import Any


class SymbolNotFoundError(Exception):
    """Raised when a symbol cannot be resolved."""

    def __init__(self, symbol: str, suggestions: list[str] | None = None):
        self.symbol = symbol
        self.suggestions = suggestions or []
        msg = f"Symbol not found: {symbol}"
        if self.suggestions:
            msg += f". Did you mean: {', '.join(self.suggestions[:5])}?"
        super().__init__(msg)


class AmbiguousSymbolError(Exception):
    """Raised when a tradingsymbol maps to multiple exchanges."""

    def __init__(self, tradingsymbol: str, candidates: list[Any]):
        self.tradingsymbol = tradingsymbol
        self.candidates = candidates
        exchanges = [f"{c.exchange}:{c.tradingsymbol}" for c in candidates]
        msg = f"Ambiguous symbol '{tradingsymbol}' matches multiple exchanges: {', '.join(exchanges)}"
        super().__init__(msg)
