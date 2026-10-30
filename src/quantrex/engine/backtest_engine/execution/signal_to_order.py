"""Signal → Order processing for backtesting.

Converts a strategy Signal into a broker Order using backtest-specific
logic (e.g., default order type, quantity handling).
"""

from __future__ import annotations

from decimal import Decimal

from quantrex.core.models.orders import Order, OrderSide, OrderType
from quantrex.core.models.signals import Signal, SignalType


def signal_to_order(signal: Signal) -> Order:
    """Convert a Signal to an Order for backtest execution.

    Args:
        signal: The trading signal from the strategy.

    Returns:
        An Order ready for submission.
    """
    side_map = {
        SignalType.ENTRY_LONG: OrderSide.BUY,
        SignalType.ENTRY_SHORT: OrderSide.SELL,
        SignalType.EXIT_LONG: OrderSide.SELL,
        SignalType.EXIT_SHORT: OrderSide.BUY,
    }

    return Order(
        symbol=signal.symbol,
        side=side_map[signal.signal_type],
        type=OrderType.MARKET,
        quantity=signal.quantity or Decimal(1),
        price=signal.price,
    )
