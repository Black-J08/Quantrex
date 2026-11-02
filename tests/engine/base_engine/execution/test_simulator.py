"""Tests for Simulator."""

from __future__ import annotations

from decimal import Decimal

from quantrex.core.models.orders import Order, OrderSide, OrderStatus, OrderType
from quantrex.core.models.trades import Trade
from quantrex.engine.base_engine.base import BaseEngine
from quantrex.engine.base_engine.simulator import Simulator


class _ConcreteEngine(BaseEngine):
    """Minimal concrete engine for simulator tests."""

    def __init__(self) -> None:
        super().__init__()
        self._fills: list = []

    def create_kernel(self, strategy):
        return None  # type: ignore[return-value]

    def data_iterator(self):
        return iter([])

    def on_signal(self, signal):
        pass

    def add_fill(self, trade) -> None:
        self._fills.append(trade)

    def get_pending_fills(self) -> list:
        fills = list(self._fills)
        self._fills.clear()
        return fills


class TestSimulator:
    """Tests for Simulator."""

    def test_submit_order_fills_at_price(self) -> None:
        engine = _ConcreteEngine()
        simulator = Simulator(engine)

        order = Order(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal(1),
            price=Decimal(100),
        )

        filled = simulator.submit_order(order)

        assert filled.status == OrderStatus.FILLED
        assert filled.symbol == "RELIANCE"

        # A fill should have been added to the engine
        fills = engine.get_pending_fills()
        assert len(fills) == 1
        assert isinstance(fills[0], Trade)
        assert fills[0].symbol == "RELIANCE"
