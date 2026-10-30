"""Simulated broker execution for backtesting.

Fills orders at bar open/close prices and produces Trade fills.
"""

from __future__ import annotations

from decimal import Decimal

from quantrex.core.models.orders import Order, OrderStatus
from quantrex.core.models.trades import Trade


class Simulator:
    """Simulated broker that fills orders at bar prices.

    For simplicity, market orders are filled at the bar's close price.
    """

    def __init__(self, engine) -> None:
        self._engine = engine

    def submit_order(self, order: Order) -> Order:
        """Simulate order submission and produce a fill.

        Args:
            order: The order to simulate.

        Returns:
            The order with status set to FILLED.
        """
        filled_order = Order(
            symbol=order.symbol,
            side=order.side,
            type=order.type,
            quantity=order.quantity,
            price=order.price,
            status=OrderStatus.FILLED,
        )
        trade = Trade(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            entry_price=order.price or Decimal(0),
            exit_price=order.price or Decimal(0),
            entry_time=order.created_at,
            exit_time=order.updated_at,
            pnl=Decimal(0),
        )
        self._engine.add_fill(trade)
        return filled_order
