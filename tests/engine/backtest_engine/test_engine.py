"""Tests for BacktestEngine."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.orders import Order, OrderSide, OrderStatus, OrderType
from quantrex.core.models.signals import Signal, SignalType
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit
from quantrex.core.models.trades import Trade

from quantrex.engine.backtest_engine.engine import BacktestEngine


def _make_signal() -> Signal:
    return Signal(
        symbol="RELIANCE",
        signal_type=SignalType.ENTRY_LONG,
        price=Decimal("100"),
        quantity=Decimal("1"),
    )


class TestBacktestEngine:
    """Tests for BacktestEngine."""

    def test_execute_signal_creates_order(self) -> None:
        engine = BacktestEngine()
        signal = _make_signal()
        order = engine.execute_signal(signal)

        assert isinstance(order, Order)
        assert order.symbol == "RELIANCE"
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.MARKET
        assert order.quantity == Decimal("1")
        assert order.status == OrderStatus.FILLED

    def test_execute_signal_exit_long_maps_to_sell(self) -> None:
        engine = BacktestEngine()
        signal = Signal(
            symbol="RELIANCE",
            signal_type=SignalType.EXIT_LONG,
            price=Decimal("105"),
            quantity=Decimal("1"),
        )
        order = engine.execute_signal(signal)
        assert order.side == OrderSide.SELL

    def test_get_pending_fills_returns_and_clears(self) -> None:
        engine = BacktestEngine()
        trade = Trade(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            exit_price=Decimal("101"),
            entry_time=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            exit_time=datetime(2024, 1, 1, 10, 1, tzinfo=UTC),
            pnl=Decimal("1"),
        )
        engine.add_fill(trade)

        fills = engine.get_pending_fills()
        assert len(fills) == 1
        assert fills[0] is trade

        # Second call should be empty
        assert engine.get_pending_fills() == []

    def test_inherits_base_engine(self) -> None:
        from quantrex.engine.base import BaseEngine

        engine = BacktestEngine()
        assert isinstance(engine, BaseEngine)
