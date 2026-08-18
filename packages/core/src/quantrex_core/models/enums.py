from enum import Enum

class PositionSide(Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"


class OrderStatus(Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"