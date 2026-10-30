"""Tests for LiveEngine."""

from __future__ import annotations

from decimal import Decimal

import pytest

from quantrex.core.models.orders import Order, OrderSide, OrderStatus, OrderType
from quantrex.core.models.signals import Signal, SignalType

from quantrex.engine.live_engine.engine import LiveEngine


def _make_signal() -> Signal:
    return Signal(
        symbol="RELIANCE",
        signal_type=SignalType.ENTRY_LONG,
        price=Decimal("100"),
        quantity=Decimal("1"),
    )


class TestLiveEngine:
    """Tests for LiveEngine."""

    def test_execute_signal_creates_order(self) -> None:
        engine = LiveEngine()
        signal = _make_signal()
        order = engine.execute_signal(signal)

        assert isinstance(order, Order)
        assert order.symbol == "RELIANCE"
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.MARKET
        assert order.quantity == Decimal("1")
        assert order.status == OrderStatus.PENDING

    def test_execute_signal_exit_long_maps_to_sell(self) -> None:
        engine = LiveEngine()
        signal = Signal(
            symbol="RELIANCE",
            signal_type=SignalType.EXIT_LONG,
            price=Decimal("105"),
            quantity=Decimal("1"),
        )
        order = engine.execute_signal(signal)
        assert order.side == OrderSide.SELL

    def test_get_pending_fills_default_empty(self) -> None:
        engine = LiveEngine()
        assert engine.get_pending_fills() == []

    def test_inherits_base_engine(self) -> None:
        from quantrex.engine.base import BaseEngine

        engine = LiveEngine()
        assert isinstance(engine, BaseEngine)
