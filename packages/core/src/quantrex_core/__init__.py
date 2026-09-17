"""Quantrex Core - Shared abstractions and domain models."""

from .exceptions.strategy_error import StrategyError
from .models.candle import Candle
from .models.enums import OrderSide, OrderType, OrderStatus
from .models.order import Order
from .models.position import Position
from .models.portfolio import PortfolioState
from .order import OrderManagementSystem
from .portfolio import InstrumentSpec, PortfolioConfig, PositionSizer
from .portfolio.context import PortfolioContext, EmptyPortfolioContext
from .protocols import DataProvider, DataAdapter
from .strategy.base import Strategy
from .strategy.context import StrategyContext

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
    "PortfolioState",
    # Portfolio
    "InstrumentSpec",
    "PortfolioConfig",
    "PositionSizer",
    "PortfolioContext",
    "EmptyPortfolioContext",
    # Order management
    "OrderManagementSystem",
    # Protocols
    "StrategyContext",
]