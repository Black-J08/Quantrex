"""Tests for BacktestPortfolioContext."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from quantrex_core import PortfolioContext, Position
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide, OrderType, OrderStatus
from quantrex_core.order import OrderManagementSystem
from quantrex_core.position.manager import PositionManager
from quantrex_backtest.core import BacktestPortfolioContext


class TestBacktestPortfolioContext:
    """Tests for BacktestPortfolioContext."""

    def setup_method(self):
        """Set up test fixtures."""
        self.position_manager = PositionManager()
        self.oms = OrderManagementSystem()
        self.instruments = ["RELIANCE", "TCS"]
        self.initial_cash = 1_000_000.0
        self.margin_requirement = 1.0

        self.context = BacktestPortfolioContext(
            position_manager=self.position_manager,
            oms=self.oms,
            current_time=datetime.min,
            instruments=self.instruments,
            initial_cash=self.initial_cash,
            margin_requirement=self.margin_requirement,
        )

    def test_initialization(self):
        """Test BacktestPortfolioContext initialization."""
        assert self.context._instruments == self.instruments
        assert self.context._initial_cash == self.initial_cash
        assert self.context._cash == self.initial_cash
        assert self.context._margin_requirement == self.margin_requirement
        assert self.context._realized_pnl == 0.0
        assert self.context._position_values == {}

    def test_portfolio_context_interface(self):
        """Test that BacktestPortfolioContext implements PortfolioContext."""
        from quantrex_core.portfolio import PortfolioContext
        assert isinstance(self.context, PortfolioContext)

    def test_cash_property(self):
        """Test cash property."""
        assert self.context.cash == self.initial_cash

    def test_equity_property(self):
        """Test equity property (cash + position values)."""
        assert self.context.equity == self.initial_cash

    def test_margin_used_property(self):
        """Test margin_used property."""
        assert self.context.margin_used == 0.0

    def test_margin_available_property(self):
        """Test margin_available property."""
        assert self.context.margin_available == self.initial_cash

    def test_positions_property(self):
        """Test positions property returns dict of positions."""
        positions = self.context.positions
        assert isinstance(positions, dict)
        assert "RELIANCE" in positions
        assert "TCS" in positions
        assert positions["RELIANCE"].quantity == 0.0
        assert positions["TCS"].quantity == 0.0

    def test_unrealized_pnl_property(self):
        """Test unrealized_pnl property."""
        assert self.context.unrealized_pnl == 0.0

    def test_realized_pnl_property(self):
        """Test realized_pnl property."""
        assert self.context.realized_pnl == 0.0

    def test_get_position(self):
        """Test get_position method."""
        pos = self.context.get_position("RELIANCE")
        assert isinstance(pos, Position)
        assert pos.quantity == 0.0
        assert pos.symbol == "RELIANCE"

    def test_submit_order_rejected_when_no_candle(self):
        """Test submit_order rejects when no current candle."""
        order = self.context.submit_order("RELIANCE", OrderSide.BUY, 10.0)
        assert order.status == OrderStatus.REJECTED
        assert order.quantity == 10.0

    def test_submit_order_with_candle(self):
        """Test submit_order with current candle."""
        # Set up a current candle
        candle = Candle(
            symbol="RELIANCE",
            timestamp=datetime(2026, 1, 1, 9, 15),
            close_time=datetime(2026, 1, 1, 9, 16),
            timeframe="1M",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1000.0,
        )
        self.context.update_candle(candle)
        self.context.update_time(candle.close_time)

        order = self.context.submit_order("RELIANCE", OrderSide.BUY, 10.0)
        assert order.status == OrderStatus.PENDING
        assert order.symbol == "RELIANCE"
        assert order.side == OrderSide.BUY
        assert order.quantity == 10.0

    def test_update_position_values(self):
        """Test _update_position_values updates position values."""
        candle = Candle(
            symbol="RELIANCE",
            timestamp=datetime(2026, 1, 1, 9, 15),
            close_time=datetime(2026, 1, 1, 9, 16),
            timeframe="1M",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1000.0,
        )
        self.context._update_position_values(candle)
        assert self.context._position_values["RELIANCE"] == 100.0

    def test_update_realized_pnl(self):
        """Test _update_realized_pnl updates cash and realized P&L."""
        self.context._update_realized_pnl(100.0)
        assert self.context._realized_pnl == 100.0
        assert self.context._cash == 1_000_100.0

    def test_reset(self):
        """Test reset clears state."""
        # Modify some state
        self.context._cash = 500000.0
        self.context._realized_pnl = 100.0
        self.context._position_values["RELIANCE"] = 100.0

        self.context.reset()

        assert self.context._cash == self.initial_cash
        assert self.context._realized_pnl == 0.0
        assert self.context._position_values == {}

    def test_portfolio_property_returns_self(self):
        """Test portfolio property returns self."""
        assert self.context.portfolio is self.context

    def test_delegate_to_strategy_context(self):
        """Test delegation to strategy context for order/position operations."""
        # Test that methods delegate properly
        assert hasattr(self.context, 'submit_order')
        assert hasattr(self.context, 'get_position')
        assert hasattr(self.context, 'current_time')
        assert hasattr(self.context, 'history')
        assert hasattr(self.context, 'timeframe_history')
        assert hasattr(self.context, 'update_time')
        assert hasattr(self.context, 'update_candle')
        assert hasattr(self.context, 'record_candle')
        assert hasattr(self.context, 'reset')