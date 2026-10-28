"""Broker-level exceptions for Quantrex.

These exceptions are owned by the broker module and are raised when
vendor-specific symbol resolution fails.
"""

from __future__ import annotations

from typing import Any


class SymbolNotFoundError(Exception):
    """Raised when a symbol cannot be resolved by the broker layer."""

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
