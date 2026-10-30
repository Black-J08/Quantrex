"""Real broker execution adapter for live trading.

Submits orders to a real broker (e.g., Zerodha) and produces fills.
"""

from __future__ import annotations

from quantrex.core.models.orders import Order, OrderStatus


class BrokerAdapter:
    """Real broker adapter that submits orders to a live broker.

    This is a placeholder adapter; a real implementation would integrate
    with the vendor's order placement API.
    """

    def __init__(self, engine) -> None:
        self._engine = engine

    def submit_order(self, order: Order) -> Order:
        """Submit an order to the live broker.

        Args:
            order: The order to submit.

        Returns:
            The order with status set to reflect broker acceptance.
        """
        filled_order = Order(
            symbol=order.symbol,
            side=order.side,
            type=order.type,
            quantity=order.quantity,
            price=order.price,
            status=OrderStatus.PENDING,
        )
        # In a real implementation, the broker would asynchronously
        # report fills. Here we record a pending fill placeholder.
        return filled_order
