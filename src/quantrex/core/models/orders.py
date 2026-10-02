"""Order models for the trading framework."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum

from quantrex.core.models.base import Event


class OrderType(Enum):
    """Order type enumeration."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderSide(Enum):
    """Order side enumeration."""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Order status enumeration."""

    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass(slots=True, kw_only=True, frozen=True)
class Order(Event):
    """Order model representing a trading order.

    Attributes:
        id: Unique order identifier.
        symbol: Instrument symbol.
        side: Order side (BUY/SELL).
        type: Order type (MARKET, LIMIT, STOP, STOP_LIMIT).
        quantity: Order quantity.
        price: Limit price (required for LIMIT and STOP_LIMIT orders).
        status: Current order status.
        created_at: Order creation timestamp.
        updated_at: Last update timestamp.
    """

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: Decimal
    price: Decimal | None = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(
        default_factory=lambda: datetime.now().astimezone()
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now().astimezone()
    )

    def __post_init__(self) -> None:
        """Validate order fields."""
        if not self.symbol:
            raise ValueError("symbol cannot be empty")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and self.price is None:
            raise ValueError(f"price is required for {self.type.value} orders")
        if self.price is not None and self.price < 0:
            raise ValueError("price cannot be negative")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")