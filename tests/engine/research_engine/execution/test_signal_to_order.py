"""Tests for signal_to_order (research)."""

from __future__ import annotations

from decimal import Decimal

from quantrex.core.models.orders import OrderSide, OrderType
from quantrex.core.models.signals import Signal, SignalType

from quantrex.engine.research_engine.execution.signal_to_order import signal_to_order


class TestSignalToOrder:
    """Tests for signal_to_order."""

    def test_entry_long_maps_to_buy(self) -> None:
        signal = Signal(
            symbol="RELIANCE",
            signal_type=SignalType.ENTRY_LONG,
            price=Decimal("100"),
            quantity=Decimal("10"),
        )
        order = signal_to_order(signal)

        assert order.symbol == "RELIANCE"
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.MARKET
        assert order.quantity == Decimal("10")
        assert order.price == Decimal("100")

    def test_entry_short_maps_to_sell(self) -> None:
        signal = Signal(
            symbol="RELIANCE",
            signal_type=SignalType.ENTRY_SHORT,
            price=Decimal("100"),
            quantity=Decimal("10"),
        )
        order = signal_to_order(signal)
        assert order.side == OrderSide.SELL

    def test_exit_long_maps_to_sell(self) -> None:
        signal = Signal(
            symbol="RELIANCE",
            signal_type=SignalType.EXIT_LONG,
            price=Decimal("105"),
            quantity=Decimal("5"),
        )
        order = signal_to_order(signal)
        assert order.side == OrderSide.SELL

    def test_exit_short_maps_to_buy(self) -> None:
        signal = Signal(
            symbol="RELIANCE",
            signal_type=SignalType.EXIT_SHORT,
            price=Decimal("95"),
            quantity=Decimal("5"),
        )
        order = signal_to_order(signal)
        assert order.side == OrderSide.BUY

    def test_default_quantity_when_none(self) -> None:
        signal = Signal(
            symbol="RELIANCE",
            signal_type=SignalType.ENTRY_LONG,
            price=Decimal("100"),
            quantity=None,
        )
        order = signal_to_order(signal)
        assert order.quantity == Decimal(1)
