"""Tests for BrokerAdapter."""

from __future__ import annotations

from decimal import Decimal

from quantrex.core.models.orders import Order, OrderSide, OrderStatus, OrderType

from quantrex.engine.live_engine.execution.broker import BrokerAdapter


class TestBrokerAdapter:
    """Tests for BrokerAdapter."""

    def test_submit_order_returns_pending_order(self) -> None:
        engine = object()
        broker = BrokerAdapter(engine)

        order = Order(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("1"),
            price=Decimal("100"),
        )

        result = broker.submit_order(order)

        assert result.status == OrderStatus.PENDING
        assert result.symbol == "RELIANCE"
        assert result.side == OrderSide.BUY
