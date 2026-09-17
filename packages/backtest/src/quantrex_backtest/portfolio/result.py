"""Portfolio backtest result for Quantrex."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from quantrex_core.models.position import Position
from quantrex_core.models.trade import TradeRecord


@dataclass(frozen=True, slots=True)
class SymbolResult:
    """Backtest result for a single symbol."""
    symbol: str
    trades: List[TradeRecord]
    final_position: Position
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: Optional[float] = None


@dataclass(frozen=True, slots=True)
class PortfolioResult:
    """Aggregated portfolio backtest result.

    Contains both portfolio-level metrics and per-symbol breakdowns.
    """
    # Portfolio-level
    initial_cash: float
    final_equity: float
    total_return: float
    total_return_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: Optional[float]
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: Optional[float]

    # Per-symbol results
    per_symbol: Dict[str, SymbolResult] = field(default_factory=dict)

    # Equity curve (timestamp, equity)
    equity_curve: List[tuple[datetime, float]] = field(default_factory=list)

    # Metadata
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    symbols: List[str] = field(default_factory=list)

    @classmethod
    def empty(cls, initial_cash: float = 0.0) -> 'PortfolioResult':
        """Create an empty result."""
        return cls(
            initial_cash=initial_cash,
            final_equity=initial_cash,
            total_return=0.0,
            total_return_pct=0.0,
            max_drawdown=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=None,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            profit_factor=None,
        )

    def combine(self, other: 'PortfolioResult') -> 'PortfolioResult':
        """Combine two portfolio results (for parallel execution)."""
        # This is a simplified combination - in practice would need proper
        # time-series merging of equity curves
        combined_symbols = {**self.per_symbol, **other.per_symbol}

        return PortfolioResult(
            initial_cash=self.initial_cash,
            final_equity=self.final_equity + other.final_equity - self.initial_cash,
            total_return=self.total_return + other.total_return,
            total_return_pct=0.0,  # Would need recalculation
            max_drawdown=max(self.max_drawdown, other.max_drawdown),
            max_drawdown_pct=0.0,
            sharpe_ratio=None,
            total_trades=self.total_trades + other.total_trades,
            winning_trades=self.winning_trades + other.winning_trades,
            losing_trades=self.losing_trades + other.losing_trades,
            win_rate=0.0,
            profit_factor=None,
            per_symbol=combined_symbols,
            equity_curve=self.equity_curve + other.equity_curve,
            start_date=self.start_date,
            end_date=other.end_date,
            symbols=list(set(self.symbols + other.symbols)),
        )