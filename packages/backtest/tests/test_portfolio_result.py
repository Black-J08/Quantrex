"""Tests for PortfolioResult and SymbolResult."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from quantrex_core.models.position import Position
from quantrex_core.models.trade import TradeRecord
from quantrex_backtest.portfolio import PortfolioResult, SymbolResult


class TestSymbolResult:
    """Tests for SymbolResult."""

    def test_symbol_result_creation(self):
        """Test creating a SymbolResult."""
        pos = Position(
            entry_timestamp=datetime(2026, 1, 1),
            entry_price=100.0,
            symbol="RELIANCE",
            quantity=10.0,
        )

        result = SymbolResult(
            symbol="RELIANCE",
            trades=[],
            final_position=pos,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            total_pnl=0.0,
            max_drawdown=0.0,
        )

        assert result.symbol == "RELIANCE"
        assert result.trades == []
        assert result.final_position == pos
        assert result.total_trades == 0
        assert result.winning_trades == 0
        assert result.losing_trades == 0
        assert result.total_pnl == 0.0
        assert result.max_drawdown == 0.0

    def test_symbol_result_with_trades(self):
        """Test SymbolResult with trades."""
        from quantrex_core.models.trade import TradeRecord
        from quantrex_core.models.enums import PositionSide

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

        pos = Position(
            entry_timestamp=datetime(2026, 1, 1),
            entry_price=100.0,
            symbol="RELIANCE",
            quantity=0.0,
        )

        result = SymbolResult(
            symbol="RELIANCE",
            trades=[trade],
            final_position=pos,
            total_trades=1,
            winning_trades=1,
            losing_trades=0,
            total_pnl=50.0,
            max_drawdown=0.0,
        )

        assert result.total_trades == 1
        assert result.winning_trades == 1
        assert result.losing_trades == 0
        assert result.total_pnl == 50.0


class TestPortfolioResult:
    """Tests for PortfolioResult."""

    def test_portfolio_result_empty(self):
        """Test creating an empty PortfolioResult."""
        result = PortfolioResult.empty(initial_cash=1_000_000.0)

        assert result.initial_cash == 1_000_000.0
        assert result.final_equity == 1_000_000.0
        assert result.total_return == 0.0
        assert result.total_return_pct == 0.0
        assert result.max_drawdown == 0.0
        assert result.max_drawdown_pct == 0.0
        assert result.sharpe_ratio is None
        assert result.total_trades == 0
        assert result.winning_trades == 0
        assert result.losing_trades == 0
        assert result.win_rate == 0.0
        assert result.profit_factor is None
        assert result.per_symbol == {}
        assert result.equity_curve == []
        assert result.start_date is None
        assert result.end_date is None
        assert result.symbols == []

    def test_portfolio_result_with_values(self):
        """Test PortfolioResult with values."""
        from quantrex_core.models.trade import TradeRecord
        from quantrex_core.models.enums import PositionSide

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

        pos = Position(
            entry_timestamp=datetime(2026, 1, 1),
            entry_price=100.0,
            symbol="RELIANCE",
            quantity=0.0,
        )

        sym_result = SymbolResult(
            symbol="RELIANCE",
            trades=[trade],
            final_position=pos,
            total_trades=1,
            winning_trades=1,
            losing_trades=0,
            total_pnl=50.0,
            max_drawdown=0.0,
        )

        equity_curve = [
            (datetime(2026, 1, 1), 1_000_000.0),
            (datetime(2026, 1, 2), 1_000_050.0),
        ]

        result = PortfolioResult(
            initial_cash=1_000_000.0,
            final_equity=1_000_050.0,
            total_return=50.0,
            total_return_pct=0.005,
            max_drawdown=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=None,
            total_trades=1,
            winning_trades=1,
            losing_trades=0,
            win_rate=100.0,
            profit_factor=None,
            per_symbol={"RELIANCE": sym_result},
            equity_curve=equity_curve,
            start_date=datetime(2026, 1, 1),
            end_date=datetime(2026, 1, 2),
            symbols=["RELIANCE"],
        )

        assert result.initial_cash == 1_000_000.0
        assert result.final_equity == 1_000_050.0
        assert result.total_return == 50.0
        assert result.total_return_pct == 0.005
        assert result.max_drawdown == 0.0
        assert result.max_drawdown_pct == 0.0
        assert result.sharpe_ratio is None
        assert result.total_trades == 1
        assert result.winning_trades == 1
        assert result.losing_trades == 0
        assert result.win_rate == 100.0
        assert result.profit_factor is None
        assert "RELIANCE" in result.per_symbol
        assert len(result.equity_curve) == 2
        assert result.start_date == datetime(2026, 1, 1)
        assert result.end_date == datetime(2026, 1, 2)
        assert result.symbols == ["RELIANCE"]

    def test_portfolio_result_combine(self):
        """Test combining two PortfolioResults."""
        result1 = PortfolioResult(
            initial_cash=1_000_000.0,
            final_equity=1_000_100.0,
            total_return=100.0,
            total_return_pct=0.01,
            max_drawdown=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=None,
            total_trades=5,
            winning_trades=3,
            losing_trades=2,
            win_rate=60.0,
            profit_factor=None,
            per_symbol={},
            equity_curve=[],
            start_date=None,
            end_date=None,
            symbols=["RELIANCE"],
        )

        result2 = PortfolioResult(
            initial_cash=1_000_000.0,
            final_equity=1_000_200.0,
            total_return=200.0,
            total_return_pct=0.02,
            max_drawdown=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=None,
            total_trades=3,
            winning_trades=2,
            losing_trades=1,
            win_rate=66.67,
            profit_factor=None,
            per_symbol={},
            equity_curve=[],
            start_date=None,
            end_date=None,
            symbols=["TCS"],
        )

        combined = result1.combine(result2)

        assert combined.initial_cash == 1_000_000.0
        # final_equity = initial_cash + total_return1 + total_return2 = 1_000_000 + 100 + 200 = 1_000_300
        assert combined.final_equity == 1_000_300.0
        assert combined.total_return == 300.0  # 100 + 200
        assert combined.total_trades == 8  # 5 + 3
        assert combined.winning_trades == 5  # 3 + 2
        assert combined.losing_trades == 3  # 2 + 1
        assert "RELIANCE" in combined.symbols
        assert "TCS" in combined.symbols