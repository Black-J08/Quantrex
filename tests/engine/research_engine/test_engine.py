"""Tests for ResearchEngine."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from quantrex.core.models.orders import Order, OrderSide, OrderStatus, OrderType
from quantrex.core.models.signals import Signal, SignalType

from quantrex.engine.research_engine.engine import ResearchEngine


def _make_signal() -> Signal:
    return Signal(
        symbol="RELIANCE",
        signal_type=SignalType.ENTRY_LONG,
        price=Decimal("100"),
        quantity=Decimal("1"),
    )


class TestResearchEngine:
    """Tests for ResearchEngine."""

    def test_execute_signal_creates_order(self) -> None:
        engine = ResearchEngine()
        signal = _make_signal()
        order = engine.execute_signal(signal)

        assert isinstance(order, Order)
        assert order.symbol == "RELIANCE"
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.MARKET
        assert order.quantity == Decimal("1")
        assert order.status == OrderStatus.FILLED

    def test_execute_signal_exit_long_maps_to_sell(self) -> None:
        engine = ResearchEngine()
        signal = Signal(
            symbol="RELIANCE",
            signal_type=SignalType.EXIT_LONG,
            price=Decimal("105"),
            quantity=Decimal("1"),
        )
        order = engine.execute_signal(signal)
        assert order.side == OrderSide.SELL

    def test_get_pending_fills_default_empty(self) -> None:
        engine = ResearchEngine()
        assert engine.get_pending_fills() == []

    def test_register_component(self) -> None:
        engine = ResearchEngine()
        component = object()
        engine.register_component(component)
        assert component in engine.get_components()

    def test_emit_event_and_get_events(self) -> None:
        engine = ResearchEngine()
        ts = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        engine.emit_event("RELIANCE", "long", ts, {"key": "value"})

        events = engine.get_events()
        assert len(events) == 1
        assert events[0]["symbol"] == "RELIANCE"
        assert events[0]["direction"] == "long"
        assert events[0]["timestamp"] == ts
        assert events[0]["metadata"] == {"key": "value"}

    def test_inherits_base_engine(self) -> None:
        from quantrex.engine.base import BaseEngine

        engine = ResearchEngine()
        assert isinstance(engine, BaseEngine)
