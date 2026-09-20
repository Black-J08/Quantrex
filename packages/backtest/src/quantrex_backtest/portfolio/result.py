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
class SingleInstrumentResult:
    """Backtest result for a single instrument.
    
    This is the atomic result unit produced by a single-instrument backtest.
    Multiple SingleInstrumentResults are aggregated into a PortfolioResult.
    """
    symbol: str
    trades: List[TradeRecord]
    equity_curve: List[tuple[datetime, float]]
    final_equity: float
    total_return: float
    total_return_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: Optional[float]
    final_position: Position
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    def to_portfolio_result(self, initial_cash: float) -> 'PortfolioResult':
        """Convert this single-instrument result to a PortfolioResult.
        
        Args:
            initial_cash: Initial cash for the portfolio (used for return calculations)
            
        Returns:
            PortfolioResult with this instrument's data in per_symbol
        """
        # Create SymbolResult for this instrument
        symbol_result = SymbolResult(
            symbol=self.symbol,
            trades=self.trades,
            final_position=self.final_position,
            total_trades=self.total_trades,
            winning_trades=self.winning_trades,
            losing_trades=self.losing_trades,
            total_pnl=self.total_return,  # total_return equals total_pnl for single instrument
            max_drawdown=self.max_drawdown,
            sharpe_ratio=None,
        )
        
        return PortfolioResult(
            initial_cash=initial_cash,
            final_equity=self.final_equity,
            total_return=self.total_return,
            total_return_pct=self.total_return_pct,
            max_drawdown=self.max_drawdown,
            max_drawdown_pct=self.max_drawdown_pct,
            sharpe_ratio=None,
            total_trades=self.total_trades,
            winning_trades=self.winning_trades,
            losing_trades=self.losing_trades,
            win_rate=self.win_rate,
            profit_factor=self.profit_factor,
            per_symbol={self.symbol: symbol_result},
            equity_curve=self.equity_curve,
            start_date=self.start_date,
            end_date=self.end_date,
            symbols=[self.symbol],
        )


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

    @classmethod
    def from_single_results(
        cls, 
        results: List['SingleInstrumentResult'], 
        initial_cash: float
    ) -> 'PortfolioResult':
        """Aggregate multiple single-instrument results into a portfolio result.
        
        Args:
            results: List of SingleInstrumentResult from independent backtests
            initial_cash: Initial cash for the portfolio
            
        Returns:
            Aggregated PortfolioResult with combined metrics
        """
        if not results:
            return cls.empty(initial_cash)
        
        # Combine per-symbol results
        combined_symbols = {}
        all_trades = []
        all_equity_curves = []
        
        for result in results:
            symbol_result = SymbolResult(
                symbol=result.symbol,
                trades=result.trades,
                final_position=result.final_position,
                total_trades=result.total_trades,
                winning_trades=result.winning_trades,
                losing_trades=result.losing_trades,
                total_pnl=result.total_return,
                max_drawdown=result.max_drawdown,
                sharpe_ratio=None,
            )
            combined_symbols[result.symbol] = symbol_result
            all_trades.extend(result.trades)
            all_equity_curves.append(result.equity_curve)
        
        # Merge all equity curves
        # Each single-instrument equity curve starts at initial_cash (absolute equity).
        # For portfolio, we need incremental equity (P&L) per instrument, then sum.
        # Convert each curve to incremental by subtracting initial_cash, merge, then add initial_cash back.
        incremental_curves = []
        for curve in all_equity_curves:
            incremental = [(ts, equity - initial_cash) for ts, equity in curve]
            incremental_curves.append(incremental)
        
        combined_incremental = incremental_curves[0]
        for curve in incremental_curves[1:]:
            combined_incremental = cls._merge_equity_curves(combined_incremental, curve)
        
        # Convert back to absolute portfolio equity
        combined_equity_curve = [(ts, equity + initial_cash) for ts, equity in combined_incremental]
        
        # Calculate portfolio metrics from combined equity curve
        if combined_equity_curve:
            final_equity = combined_equity_curve[-1][1]
            total_return = final_equity - initial_cash
        else:
            total_return = sum(r.total_return for r in results)
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
        
        # Combine trade statistics
        total_trades = sum(r.total_trades for r in results)
        winning_trades = sum(r.winning_trades for r in results)
        losing_trades = sum(r.losing_trades for r in results)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        # Profit factor from combined trades
        gross_profit = sum(t.pnl for t in all_trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in all_trades if t.pnl < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None
        
        # Determine date range
        start_dates = [r.start_date for r in results if r.start_date is not None]
        end_dates = [r.end_date for r in results if r.end_date is not None]
        start_date = min(start_dates) if start_dates else None
        end_date = max(end_dates) if end_dates else None
        
        return cls(
            initial_cash=initial_cash,
            final_equity=final_equity,
            total_return=total_return,
            total_return_pct=total_return_pct,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=None,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            per_symbol=combined_symbols,
            equity_curve=combined_equity_curve,
            start_date=start_date,
            end_date=end_date,
            symbols=[r.symbol for r in results],
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