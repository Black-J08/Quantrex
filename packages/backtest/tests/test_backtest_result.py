"""Tests for BacktestResult - minimal trade log + equity curve."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from quantrex_core.models.position import Position
from quantrex_core.models.trade import TradeRecord
from quantrex_core.models.enums import PositionSide
from quantrex_backtest.results import BacktestResult


class TestBacktestResult:
    """Tests for BacktestResult."""

    def test_backtest_result_empty(self):
        """Test creating an empty BacktestResult."""
        result = BacktestResult.empty(initial_cash=1_000_000.0, symbols=["RELIANCE"])

        assert result.initial_cash == 1_000_000.0
        assert result.final_equity == 1_000_000.0
        assert result.trades == []
        assert result.equity_curve == []
        assert result.symbols == ["RELIANCE"]
        assert result.total_return == 0.0
        assert result.total_return_pct == 0.0

    def test_backtest_result_with_trades_and_equity_curve(self):
        """Test BacktestResult with trades and equity curve."""
        trade = TradeRecord(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=10.0,
            entry_timestamp=datetime(2026, 1, 1),
            entry_price=100.0,
            exit_timestamp=datetime(2026, 1, 2),
            exit_price=105.0,
            pnl=50.0,
        )

        equity_curve = [
            (datetime(2026, 1, 1), 1_000_000.0),
            (datetime(2026, 1, 2), 1_000_050.0),
        ]

        result = BacktestResult(
            trades=[trade],
            equity_curve=equity_curve,
            initial_cash=1_000_000.0,
            final_equity=1_000_050.0,
            symbols=["RELIANCE"],
        )

        assert result.initial_cash == 1_000_000.0
        assert result.final_equity == 1_000_050.0
        assert len(result.trades) == 1
        assert result.trades[0].pnl == 50.0
        assert len(result.equity_curve) == 2
        assert result.equity_curve[0][1] == 1_000_000.0
        assert result.equity_curve[1][1] == 1_000_050.0
        assert result.symbols == ["RELIANCE"]
        assert result.total_return == 50.0
        assert result.total_return_pct == 0.005

    def test_backtest_result_multiple_symbols(self):
        """Test BacktestResult with multiple symbols."""
        trade1 = TradeRecord(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=10.0,
            entry_timestamp=datetime(2026, 1, 1),
            entry_price=100.0,
            exit_timestamp=datetime(2026, 1, 2),
            exit_price=105.0,
            pnl=50.0,
        )
        trade2 = TradeRecord(
            symbol="TCS",
            side=PositionSide.LONG,
            quantity=5.0,
            entry_timestamp=datetime(2026, 1, 1),
            entry_price=200.0,
            exit_timestamp=datetime(2026, 1, 2),
            exit_price=210.0,
            pnl=50.0,
        )

        equity_curve = [
            (datetime(2026, 1, 1), 1_000_000.0),
            (datetime(2026, 1, 2), 1_000_100.0),
        ]

        result = BacktestResult(
            trades=[trade1, trade2],
            equity_curve=equity_curve,
            initial_cash=1_000_000.0,
            final_equity=1_000_100.0,
            symbols=["RELIANCE", "TCS"],
        )

        assert len(result.trades) == 2
        assert result.symbols == ["RELIANCE", "TCS"]
        assert result.total_return == 100.0
        assert result.total_return_pct == 0.01

    def test_merge_equity_curves_single(self):
        """Test merging a single equity curve."""
        curve = [
            (datetime(2026, 1, 1), 1_000_000.0),
            (datetime(2026, 1, 2), 1_000_050.0),
        ]
        merged = BacktestResult.merge_equity_curves([curve], 1_000_000.0)
        assert merged == curve

    def test_merge_equity_curves_multiple(self):
        """Test merging multiple equity curves."""
        curve1 = [
            (datetime(2026, 1, 1), 1_000_000.0),
            (datetime(2026, 1, 2), 1_000_050.0),
        ]
        curve2 = [
            (datetime(2026, 1, 1), 1_000_000.0),
            (datetime(2026, 1, 2), 1_000_050.0),
        ]

        merged = BacktestResult.merge_equity_curves([curve1, curve2], 1_000_000.0)

        # Each curve starts at initial_cash, so incremental is 0 then 50
        # Merged incremental: 0 then 100
        # Absolute: 1_000_000 then 1_000_100
        assert len(merged) == 2
        assert merged[0][1] == 1_000_000.0
        assert merged[1][1] == 1_000_100.0

    def test_merge_equity_curves_different_timestamps(self):
        """Test merging equity curves with different timestamps."""
        curve1 = [
            (datetime(2026, 1, 1), 1_000_000.0),
            (datetime(2026, 1, 2), 1_000_050.0),
            (datetime(2026, 1, 3), 1_000_060.0),
        ]
        curve2 = [
            (datetime(2026, 1, 1), 1_000_000.0),
            (datetime(2026, 1, 3), 1_000_030.0),
        ]

        merged = BacktestResult.merge_equity_curves([curve1, curve2], 1_000_000.0)

        # Should have all timestamps: 1/1, 1/2, 1/3
        assert len(merged) == 3
        # 1/1: 0 + 0 = 0 -> 1_000_000
        assert merged[0][1] == 1_000_000.0
        # 1/2: 50 + 0 = 50 -> 1_000_050
        assert merged[1][1] == 1_000_050.0
        # 1/3: 60 + 30 = 90 -> 1_000_090
        assert merged[2][1] == 1_000_090.0

    def test_merge_equity_curves_empty(self):
        """Test merging empty list of curves."""
        merged = BacktestResult.merge_equity_curves([], 1_000_000.0)
        assert merged == []

    def test_merge_equity_curves_with_empty_curve(self):
        """Test merging with one empty curve."""
        curve1 = [
            (datetime(2026, 1, 1), 1_000_000.0),
            (datetime(2026, 1, 2), 1_000_050.0),
        ]
        merged = BacktestResult.merge_equity_curves([curve1, []], 1_000_000.0)
        assert merged == curve1

    def test_frozen_dataclass(self):
        """Test that BacktestResult is frozen (immutable)."""
        result = BacktestResult.empty(1_000_000.0)
        with pytest.raises(AttributeError):
            result.initial_cash = 2_000_000.0

    def test_slots(self):
        """Test that BacktestResult uses slots."""
        result = BacktestResult.empty(1_000_000.0)
        # Should not have __dict__
        assert not hasattr(result, '__dict__')