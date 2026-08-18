from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from ..models.enums import OrderSide, OrderType, OrderStatus, PositionSide
from ..models.order import Order
from ..models.position import Position


class PositionManager:
    """Authoritative order/position state and behavior. Immediate acceptance, no fill simulation."""

    def __init__(self) -> None:
        self._orders: Dict[str, Order] = {}      # Audit trail: order_id -> Order
        self._positions: Dict[str, Position] = {} # Current exposure: symbol -> Position
        self._order_counter: int = 0

    def _make_position(
        self,
        symbol: str,
        quantity: float,
        entry_timestamp: datetime,
        entry_price: float,
        side: OrderSide,
    ) -> Position:
        """Helper to create a Position with all required fields.

        Determines position_side from quantity sign:
        - quantity > 0  -> LONG
        - quantity < 0  -> SHORT
        - quantity == 0 -> LONG (default, represents flat)
        """
        if quantity > 0:
            position_side = PositionSide.LONG
        elif quantity < 0:
            position_side = PositionSide.SHORT
        else:
            position_side = PositionSide.LONG

        return Position(
            entry_timestamp=entry_timestamp,
            entry_price=entry_price,
            symbol=symbol,
            quantity=quantity,
            position_side=position_side,
        )

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType,
        timestamp: datetime,
    ) -> Order:
        """Process order immediately: validate, record for audit, update position, return Order.
        Order recording serves ONLY as audit trail — does not imply fill/execution semantics."""
        self._order_counter += 1
        order_id = str(self._order_counter)

        # Validate (basic MVP validation)
        if quantity <= 0:
            return Order(
                id=order_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                status=OrderStatus.REJECTED,
                timestamp=timestamp,
            )

        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            status=OrderStatus.ACCEPTED,
            timestamp=timestamp,
        )
        self._orders[order_id] = order  # Record for audit trail only

        # Update net position synchronously (no fill simulation)
        current = self._positions.get(symbol)
        delta = quantity if side == OrderSide.BUY else -quantity

        if current is None:
            # New position: set entry_timestamp and entry_price from the order
            new_qty = delta
            self._positions[symbol] = self._make_position(
                symbol=symbol,
                quantity=new_qty,
                entry_timestamp=timestamp,
                entry_price=0.0,  # MARKET order price not known at submission
                side=side,
            )
        else:
            # Update existing position
            new_qty = current.quantity + delta
            # Preserve original entry_timestamp and entry_price
            self._positions[symbol] = self._make_position(
                symbol=symbol,
                quantity=new_qty,
                entry_timestamp=current.entry_timestamp,
                entry_price=current.entry_price,
                side=side,
            )

        return order
    
    def get_position(self, symbol: str) -> Position:
        """Return current net position for symbol. Returns zero Position if none."""
        if symbol not in self._positions:
            return Position.zero(symbol)
        return self._positions[symbol]

    def get_all_positions(self) -> List[Position]:
        """Return a list of all current positions."""
        return list(self._positions.values())