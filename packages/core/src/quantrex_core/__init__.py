"""Quantrex Core - Shared abstractions and domain models."""

from .exceptions.strategy_error import StrategyError
from .models.candle import Candle
from .models.enums import OrderSide, OrderType, OrderStatus
from .models.order import Order
from .models.position import Position
from .protocols import DataProvider, DataAdapter, StrategyContext
from .strategy.base import Strategy

__all__ = [
    "Candle",
    "DataProvider",
    "DataAdapter",
    "Strategy",
    "StrategyError",
    # Enums
    "OrderSide",
    "OrderType",
    "OrderStatus",
    # Models
    "Order",
    "Position",
    # Protocols
    "StrategyContext",
]