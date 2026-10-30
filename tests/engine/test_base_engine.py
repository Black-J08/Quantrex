"""Tests for BaseEngine."""

from __future__ import annotations

from decimal import Decimal

import pytest

from quantrex.core.models.orders import Order, OrderSide, OrderType
from quantrex.core.models.signals import Signal, SignalType

from quantrex.engine.base import BaseEngine


class ConcreteEngine(BaseEngine):
    """A concrete engine for testing."""

    def __init__(self) -> None:
        self.executed_signals: list[Signal] = []
        self.submitted_orders: list[Order] = []

    def execute_signal(self, signal: Signal) -> Order:
        self.executed_signals.append(signal)
        order = Order(
            symbol=signal.symbol,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=signal.quantity or Decimal("1"),
        )
        self.submitted_orders.append(order)
        return order


class TestBaseEngine:
    """Tests for BaseEngine."""

    def test_execute_signal_is_abstract(self) -> None:
        """BaseEngine cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseEngine()  # type: ignore[abstract]

    def test_concrete_engine_implements_execute_signal(self) -> None:
        engine = ConcreteEngine()
        signal = Signal(
            symbol="RELIANCE",
            signal_type=SignalType.ENTRY_LONG,
            price=Decimal("100"),
            quantity=Decimal("1"),
        )
        order = engine.execute_signal(signal)
        assert order.symbol == "RELIANCE"
        assert len(engine.executed_signals) == 1
        assert len(engine.submitted_orders) == 1

    def test_get_pending_fills_default_empty(self) -> None:
        engine = ConcreteEngine()
        assert engine.get_pending_fills() == []

    def test_submit_order_default_returns_order(self) -> None:
        engine = ConcreteEngine()
        order = Order(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("1"),
        )
        result = engine.submit_order(order)
        assert result is order

    def test_get_position_default_returns_none(self) -> None:
        engine = ConcreteEngine()
        assert engine.get_position("RELIANCE") is None

    def test_on_start_and_on_stop_are_noops(self) -> None:
        engine = ConcreteEngine()
        # Should not raise
        engine.on_start()
        engine.on_stop()
