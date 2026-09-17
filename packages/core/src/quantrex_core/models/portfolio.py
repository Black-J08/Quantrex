"""Portfolio-level state models for Quantrex."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict

from .position import Position


@dataclass(frozen=True, slots=True)
class PortfolioState:
    """Portfolio-level view of account state.

    This is a snapshot of the portfolio at a point in time, composed
    onto StrategyContext for strategy access via ``ctx.portfolio``.

    Attributes:
        cash: Available cash balance.
        equity: Total portfolio value (cash + sum of position market values).
        margin_used: Margin currently allocated to open positions.
        margin_available: Margin available for new positions.
        positions: Dictionary of open positions keyed by symbol.
        unrealized_pnl: Unrealized P&L across all open positions.
        realized_pnl: Realized P&L from closed trades.
    """
    cash: float
    equity: float
    margin_used: float
    margin_available: float
    positions: Dict[str, Position]
    unrealized_pnl: float
    realized_pnl: float

    @classmethod
    def empty(cls) -> 'PortfolioState':
        """Create an empty portfolio state (no positions, zero values)."""
        return cls(
            cash=0.0,
            equity=0.0,
            margin_used=0.0,
            margin_available=0.0,
            positions={},
            unrealized_pnl=0.0,
            realized_pnl=0.0,
        )