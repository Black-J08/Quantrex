"""Tests for Simulator (research)."""

from __future__ import annotations

from decimal import Decimal

from quantrex.core.models.orders import Order, OrderSide, OrderStatus, OrderType
from quantrex.core.models.trades import Trade
from quantrex.engine.base_engine.simulator import Simulator
from quantrex.engine.research_engine.engine import ResearchEngine


class TestSimulator:
    """Tests for Simulator."""

    def test_submit_order_fills_at_price(self) -> None:
        engine = ResearchEngine()
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

        fills = engine.get_pending_fills()
        assert len(fills) == 1
        assert isinstance(fills[0], Trade)
        assert fills[0].symbol == "RELIANCE"
