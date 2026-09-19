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
        """Combine two portfolio results (for parallel execution).
        
        Properly merges equity curves in time order and recalculates
        portfolio-level metrics from the combined data.
        """
        # Combine per-symbol results (no overlap expected for independent instruments)
        combined_symbols = {**self.per_symbol, **other.per_symbol}
        
        # Merge equity curves in time order
        combined_equity_curve = self._merge_equity_curves(
            self.equity_curve, other.equity_curve
        )
        
        # Recalculate portfolio metrics from combined equity curve
        initial_cash = self.initial_cash
        
        # If we have equity curve data, use it; otherwise fall back to total_return
        if combined_equity_curve:
            final_equity = combined_equity_curve[-1][1]
            total_return = final_equity - initial_cash
        else:
            # Fallback: sum total_returns (old behavior for backward compatibility)
            total_return = self.total_return + other.total_return
            final_equity = initial_cash + total_return
        
        total_return_pct = (total_return / initial_cash * 100) if initial_cash > 0 else 0.0
        
        # Calculate max drawdown from combined equity curve
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        if combined_equity_curve:
            peak = initial_cash
            for _, equity in combined_equity_curve:
                if equity > peak:
                    peak = equity
                drawdown = peak - equity
                drawdown_pct = (drawdown / peak * 100) if peak > 0 else 0.0
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                if drawdown_pct > max_drawdown_pct:
                    max_drawdown_pct = drawdown_pct
        else:
            # Fallback: max of individual drawdowns
            max_drawdown = max(self.max_drawdown, other.max_drawdown)
            max_drawdown_pct = 0.0  # Would need recalculation
        
        # Combine trade statistics
        total_trades = self.total_trades + other.total_trades
        winning_trades = self.winning_trades + other.winning_trades
        losing_trades = self.losing_trades + other.losing_trades
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        # Profit factor from combined trades
        # We need to get all trades from per_symbol results
        all_trades = []
        for sym_result in combined_symbols.values():
            all_trades.extend(sym_result.trades)
        
        gross_profit = sum(t.pnl for t in all_trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in all_trades if t.pnl < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None
        
        # Determine date range
        start_date = self.start_date
        if other.start_date and (start_date is None or other.start_date < start_date):
            start_date = other.start_date
        end_date = self.end_date
        if other.end_date and (end_date is None or other.end_date > end_date):
            end_date = other.end_date
        
        return PortfolioResult(
            initial_cash=initial_cash,
            final_equity=final_equity,
            total_return=total_return,
            total_return_pct=total_return_pct,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=None,  # Would need returns series
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            per_symbol=combined_symbols,
            equity_curve=combined_equity_curve,
            start_date=start_date,
            end_date=end_date,
            symbols=list(set(self.symbols + other.symbols)),
        )
    
    @staticmethod
    def _merge_equity_curves(
        curve1: List[tuple[datetime, float]], 
        curve2: List[tuple[datetime, float]]
    ) -> List[tuple[datetime, float]]:
        """Merge two equity curves in time order.
        
        For parallel backtests, each curve represents the equity of a subset
        of instruments. The combined equity at each timestamp is the sum of
        equities from both curves at that timestamp.
        
        Since instruments may have different timestamps, we interpolate
        by using the last known equity value for each curve at each timestamp.
        """
        if not curve1:
            return curve2
        if not curve2:
            return curve1
        
        # Collect all unique timestamps
        all_timestamps = set()
        for ts, _ in curve1:
            all_timestamps.add(ts)
        for ts, _ in curve2:
            all_timestamps.add(ts)
        
        sorted_timestamps = sorted(all_timestamps)
        
        # Build lookup for each curve
        curve1_dict = dict(curve1)
        curve2_dict = dict(curve2)
        
        # Merge by taking last known value from each curve at each timestamp
        merged = []
        last_val1 = curve1[0][1]
        last_val2 = curve2[0][1]
        
        for ts in sorted_timestamps:
            if ts in curve1_dict:
                last_val1 = curve1_dict[ts]
            if ts in curve2_dict:
                last_val2 = curve2_dict[ts]
            merged.append((ts, last_val1 + last_val2))
        
        return merged