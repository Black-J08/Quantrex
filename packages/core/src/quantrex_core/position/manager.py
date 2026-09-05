"""Position lifecycle management.

The :class:`PositionManager` is the authoritative owner of order audit trail,
current net positions, and completed trade records for a trading session
(backtest, live, or paper). It supports the full position lifecycle:

1. **Open** — first order for a symbol creates a new ``Position`` whose
   ``entry_timestamp`` and ``entry_price`` come from the order.
2. **Scale-in** — adding to an existing same-side position preserves the
   original entry basis (no new ``TradeRecord`` is emitted; the open is
   purely additive).
3. **Scale-out / partial close** — reducing an existing same-side position
   emits one ``TradeRecord`` for the closed portion; the remaining
   ``Position`` keeps the original entry basis.
4. **Full close** — an order that drives net quantity to zero emits one
   ``TradeRecord`` for the full closed quantity and **removes** the symbol
   from the position map (no zero-quantity phantom position is kept).
5. **Flip** — an order whose delta crosses zero (e.g. Long 10 → Sell 15)
   emits one ``TradeRecord`` for the FULL closed quantity of the prior
   side and opens a fresh ``Position`` for the residual opposite-side
   quantity whose ``entry_timestamp`` and ``entry_price`` come from the
   flip order. The new side's open is NOT itself a ``TradeRecord``.

Validation rejects orders with non-positive quantity or non-finite price
(``NaN`` / ``±inf``). Rejected orders are returned with
``status=REJECTED`` AND recorded in the audit trail so the trail is
complete.

PnL formula: ``(exit_price - entry_price) * quantity * side_multiplier``,
where ``side_multiplier`` is ``+1`` for LONG and ``-1`` for SHORT.
"""

import math
from datetime import datetime
from typing import Dict, List

from ..models.enums import OrderSide, OrderType, OrderStatus, PositionSide
from ..models.order import Order
from ..models.position import Position
from ..models.trade import TradeRecord


def _same_sign(a: float, b: float) -> bool:
    """Return True if ``a`` and ``b`` share the same sign (or are both zero)."""
    return (a >= 0 and b >= 0) or (a <= 0 and b <= 0)


class PositionManager:
    """Authoritative order/position state and behavior. Immediate acceptance, no fill simulation."""

    def __init__(self) -> None:
        self._orders: Dict[str, Order] = {}           # Audit trail: order_id -> Order
        self._positions: Dict[str, Position] = {}      # Current exposure: symbol -> Position
        self._closed_trades: List[TradeRecord] = []    # Completed trade records
        self._order_counter: int = 0

    @staticmethod
    def _make_position(
        symbol: str,
        quantity: float,
        entry_timestamp: datetime,
        entry_price: float,
    ) -> Position:
        """Build a ``Position`` from a signed net quantity.

        ``position_side`` is derived from the sign of ``quantity`` in
        :meth:`Position.__post_init__` and overwrites whatever is passed
        here, so the explicit value is redundant. The manager never
        passes ``quantity=0`` at a call site, so the FLAT branch is not
        exercised; the explicit LONG/SHORT here documents intent.
        """
        position_side = PositionSide.LONG if quantity >= 0 else PositionSide.SHORT
        return Position(
            entry_timestamp=entry_timestamp,
            entry_price=entry_price,
            symbol=symbol,
            quantity=quantity,
            position_side=position_side,
        )

    @staticmethod
    def _build_trade(
        symbol: str,
        side: PositionSide,
        quantity: float,
        entry_timestamp: datetime,
        entry_price: float,
        exit_timestamp: datetime,
        exit_price: float,
    ) -> TradeRecord:
        """Build a ``TradeRecord`` for a closed portion of a position.

        ``quantity`` is always the absolute quantity closed. PnL is
        ``(exit - entry) * quantity * side_multiplier``.
        """
        side_multiplier = 1.0 if side == PositionSide.LONG else -1.0
        pnl = (exit_price - entry_price) * quantity * side_multiplier
        return TradeRecord(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_timestamp=entry_timestamp,
            entry_price=entry_price,
            exit_timestamp=exit_timestamp,
            exit_price=exit_price,
            pnl=pnl,
        )

    def _record_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType,
        timestamp: datetime,
        price: float,
    ) -> Order:
        """Validate and record an order in the audit trail (no position mutation)."""
        self._order_counter += 1
        order_id = str(self._order_counter)

        if quantity <= 0 or not math.isfinite(price):
            rejected = Order(
                id=order_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                status=OrderStatus.REJECTED,
                timestamp=timestamp,
            )
            self._orders[order_id] = rejected
            return rejected

        accepted = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            status=OrderStatus.ACCEPTED,
            timestamp=timestamp,
        )
        self._orders[order_id] = accepted
        return accepted

    def apply(
        self,
        symbol: str,
        delta: float,
        timestamp: datetime,
        price: float,
    ) -> None:
        """Apply a signed position delta at the given price and time.

        This is the core 5-case position state machine. Called by
        :meth:`submit_order` for immediately-filled orders and by
        :class:`quantrex_backtest.core.engine.BacktestEngine` for T+1
        drained orders.

        Cases:
            1. No prior position → open fresh.
            2. Same-side update where |qty| grew → scale-in (no TradeRecord).
            3. Same-side update where |qty| shrank → scale-out / partial close.
            4. Delta drives net quantity to zero → full close.
            5. Delta crosses zero (e.g. Long 10 → Sell 15) → flip.
        """
        current = self._positions.get(symbol)

        if current is None:
            # Case 1: open fresh.
            self._apply_open(symbol, delta, timestamp, price)
            return

        new_qty = current.quantity + delta

        if new_qty == 0:
            # Case 4: full close.
            self._apply_full_close(symbol, current, timestamp, price)
            return

        if not _same_sign(current.quantity, new_qty):
            # Case 5: flip.
            self._apply_flip(symbol, current, new_qty, timestamp, price)
            return

        # Cases 2 and 3 share a sign (same-side update). Distinguish by
        # whether |qty| grew (scale-in) or shrank (scale-out).
        if abs(new_qty) > abs(current.quantity):
            # Case 2: scale-in.
            self._apply_scale_in(symbol, current, new_qty)
        else:
            # Case 3: scale-out / partial close.
            self._apply_scale_out(symbol, current, new_qty, timestamp, price)

    def _apply_open(
        self,
        symbol: str,
        delta: float,
        timestamp: datetime,
        price: float,
    ) -> None:
        """Case 1: no prior position → open a fresh ``Position``.

        Entry basis (timestamp and price) comes from the order itself.
        No ``TradeRecord`` is emitted.
        """
        self._positions[symbol] = self._make_position(
            symbol=symbol,
            quantity=delta,
            entry_timestamp=timestamp,
            entry_price=price,
        )

    def _apply_full_close(
        self,
        symbol: str,
        current: Position,
        timestamp: datetime,
        price: float,
    ) -> None:
        """Case 4: order drives net quantity to zero.

        Emits one ``TradeRecord`` for the full prior-side quantity and
        removes the symbol from the position map. No zero-quantity
        phantom position is kept.
        """
        self._closed_trades.append(
            self._build_trade(
                symbol=symbol,
                side=current.position_side,
                quantity=abs(current.quantity),
                entry_timestamp=current.entry_timestamp,
                entry_price=current.entry_price,
                exit_timestamp=timestamp,
                exit_price=price,
            )
        )
        del self._positions[symbol]

    def _apply_flip(
        self,
        symbol: str,
        current: Position,
        new_qty: float,
        timestamp: datetime,
        price: float,
    ) -> None:
        """Case 5: order delta crosses zero (e.g. Long 10 → Sell 15).

        Emits one ``TradeRecord`` for the FULL prior-side quantity using
        the order's price/time as exit, then opens a fresh ``Position``
        for the residual opposite-side quantity whose entry basis
        (timestamp and price) is the flip order itself. The new side's
        open is NOT itself a ``TradeRecord``.
        """
        self._closed_trades.append(
            self._build_trade(
                symbol=symbol,
                side=current.position_side,
                quantity=abs(current.quantity),
                entry_timestamp=current.entry_timestamp,
                entry_price=current.entry_price,
                exit_timestamp=timestamp,
                exit_price=price,
            )
        )
        self._positions[symbol] = self._make_position(
            symbol=symbol,
            quantity=new_qty,
            entry_timestamp=timestamp,
            entry_price=price,
        )

    def _apply_scale_in(
        self,
        symbol: str,
        current: Position,
        new_qty: float,
    ) -> None:
        """Case 2: same-side update whose ``|qty|`` grew.

        The open is purely additive: the existing entry basis
        (timestamp and price) is preserved and no ``TradeRecord`` is
        emitted.
        """
        self._positions[symbol] = self._make_position(
            symbol=symbol,
            quantity=new_qty,
            entry_timestamp=current.entry_timestamp,
            entry_price=current.entry_price,
        )

    def _apply_scale_out(
        self,
        symbol: str,
        current: Position,
        new_qty: float,
        timestamp: datetime,
        price: float,
    ) -> None:
        """Case 3: same-side update whose ``|qty|`` shrank (partial close).

        Emits one ``TradeRecord`` for the closed portion using the
        order's price/time as exit, then writes a residual ``Position``
        that keeps the original entry basis for the remainder.
        """
        closed_qty = abs(current.quantity) - abs(new_qty)
        self._closed_trades.append(
            self._build_trade(
                symbol=symbol,
                side=current.position_side,
                quantity=closed_qty,
                entry_timestamp=current.entry_timestamp,
                entry_price=current.entry_price,
                exit_timestamp=timestamp,
                exit_price=price,
            )
        )
        self._positions[symbol] = self._make_position(
            symbol=symbol,
            quantity=new_qty,
            entry_timestamp=current.entry_timestamp,
            entry_price=current.entry_price,
        )

    def get_position(self, symbol: str) -> Position:
        """Return current net position for symbol. Returns ``Position.zero(symbol)`` if none."""
        if symbol not in self._positions:
            return Position.zero(symbol)
        return self._positions[symbol]

    def get_all_positions(self) -> List[Position]:
        """Return a list of all current (non-zero) positions."""
        return list(self._positions.values())

    def get_closed_trades(self) -> List[TradeRecord]:
        """Return a copy of all closed trade records, in insertion order."""
        return list(self._closed_trades)