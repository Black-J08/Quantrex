"""Quantrex Core Position management.

Provides the authoritative :class:`PositionManager` that owns order audit
trail, current net positions, and completed trade records for a trading
session (backtest, live, or paper).
"""

from .manager import PositionManager

__all__ = ["PositionManager"]
