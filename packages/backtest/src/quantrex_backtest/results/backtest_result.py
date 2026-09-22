"""Minimal backtest result for Quantrex - trade log + equity curve only."""

from dataclasses import dataclass
from datetime import datetime
from typing import List

from quantrex_core.models.trade import TradeRecord


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Minimal backtest result containing only trade log and equity curve.

    No analytics, no per-symbol breakdowns, no factory methods.
    Compute derived metrics post-hoc from trades + equity_curve if needed.
    """
    trades: List[TradeRecord]
    equity_curve: List[tuple[datetime, float]]
    initial_cash: float
    final_equity: float
    symbols: List[str]

    @property
    def total_return(self) -> float:
        """Total P&L from initial cash."""
        return self.final_equity - self.initial_cash

    @property
    def total_return_pct(self) -> float:
        """Total return as percentage."""
        return (self.total_return / self.initial_cash * 100) if self.initial_cash > 0 else 0.0

    @classmethod
    def empty(cls, initial_cash: float = 0.0, symbols: List[str] = None) -> 'BacktestResult':
        """Create an empty result for no-data scenarios."""
        return cls(
            trades=[],
            equity_curve=[],
            initial_cash=initial_cash,
            final_equity=initial_cash,
            symbols=symbols or [],
        )

    @staticmethod
    def merge_equity_curves(
        curves: List[List[tuple[datetime, float]]],
        initial_cash: float
    ) -> List[tuple[datetime, float]]:
        """Merge multiple equity curves by time-aligning and summing.

        Each curve represents absolute equity starting from initial_cash.
        We convert to incremental (P&L), merge, then convert back.
        """
        if not curves:
            return []

        if len(curves) == 1:
            return curves[0]

        # Convert each curve to incremental P&L (equity - initial_cash)
        incremental_curves = []
        for curve in curves:
            incremental = [(ts, equity - initial_cash) for ts, equity in curve]
            incremental_curves.append(incremental)

        # Merge incrementally
        merged_incremental = incremental_curves[0]
        for curve in incremental_curves[1:]:
            merged_incremental = BacktestResult._merge_two_curves(merged_incremental, curve)

        # Convert back to absolute equity
        return [(ts, equity + initial_cash) for ts, equity in merged_incremental]

    @staticmethod
    def _merge_two_curves(
        curve1: List[tuple[datetime, float]],
        curve2: List[tuple[datetime, float]]
    ) -> List[tuple[datetime, float]]:
        """Merge two incremental equity curves in time order."""
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