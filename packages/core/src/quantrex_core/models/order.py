from dataclasses import dataclass
from datetime import datetime
from .enums import OrderSide, OrderType, OrderStatus


@dataclass(frozen=True, slots=True)
class Order:
    id: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType
    status: OrderStatus
    timestamp: datetime