"""Core models package for the Quantrex trading framework.

This package provides the essential data models for an event-driven
algorithmic trading framework. All models are generic, reusable,
and engine-agnostic.
"""

from quantrex.core.models.base import Event
from quantrex.core.models.instruments import (
    AssetClass,
    ContractSpec,
    ContractType,
    InstrumentSpec,
    OptionType,
)
from quantrex.core.models.market_data import OHLCVCandle, Tick
from quantrex.core.models.orders import Order, OrderSide, OrderStatus, OrderType
from quantrex.core.models.positions import Position, PositionSide
from quantrex.core.models.signals import Signal, SignalType
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit
from quantrex.core.models.trades import Trade

__all__ = [
    "AssetClass",
    "ContractSpec",
    "ContractType",
    "Event",
    "InstrumentSpec",
    "OHLCVCandle",
    "OptionType",
    "Order",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "PositionSide",
    "Signal",
    "SignalType",
    "Tick",
    "Timeframe",
    "TimeframeUnit",
    "Trade",
]

__version__ = "0.1.0"