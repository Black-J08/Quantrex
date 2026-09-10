"""Position lifecycle management using a FIFO lot ledger.

The :class:`PositionManager` is the authoritative owner of order audit trail,
current net positions, and completed trade records for a trading session
(backtest, live, or paper). It supports the full position lifecycle using an
**industry-standard FIFO lot accounting** model:

1. **Open** — first order for a symbol enqueues a fresh :class:`Lot` whose
   ``open_timestamp`` and ``open_price`` come from the order.
2. **Scale-in** — adding to an existing same-side position enqueues a new
   :class:`Lot` at the new order's price/time. No ``TradeRecord`` is emitted.
3. **Scale-out / partial close** — reducing an existing same-side position
   consumes the head of the FIFO lot deque, emitting **one
   :class:`~quantrex_core.models.trade.TradeRecord` per consumed lot-leg**
   (i.e. one row per lot the close actually consumed). Each row's
   ``entry_timestamp`` / ``entry_price`` point to the specific lot that was
   matched — never a weighted average or the position's first order.
4. **Full close** — a close that drives net quantity to zero consumes all
   remaining lots FIFO, emitting one ``TradeRecord`` per lot, and removes
   the symbol from the position map.
5. **Flip** — an order whose delta crosses zero (e.g. Long 10 → Sell 15)
   first consumes all prior-side lots FIFO (emitting one ``TradeRecord``
   per lot) and then enqueues a fresh :class:`Lot` for the residual
   opposite-side quantity whose entry basis is the flip order's price/time.

Why FIFO (over weighted-average or first-order attribution):
    * **Causality per matched leg**: every row's P&L is computed against the
      lot that was actually sold. A Sell 3 against Buy 2@₹10 + Buy 2@₹20
      produces a row with ``entry_price=10, quantity=2`` and a row with
      ``entry_price=20, quantity=1`` — never a row claiming
      ``entry_price=10, quantity=3``.
    * **Performance attribution honesty**: win rate, R-multiple, profit
      factor decompose by entry lot so researchers can ask "do ₹10 fills
      outperform ₹20 fills?".
    * **Reproducibility**: the emitted trade list carries every input
      needed to reconstruct the lot → close mapping.
    * **Industry alignment**: broker / IRS tax-lot accounting defaults to
      FIFO; Backtrader's ``Trade`` object and vectorbt's
      ``trades.records`` both track per-fill entry/exit.

Per-row ``TradeRecord`` contract:
    * ``quantity`` is the absolute quantity of this row's matched leg.
    * ``entry_timestamp`` / ``entry_price`` equal the matched lot's
      ``open_timestamp`` / ``open_price`` — never a weighted average.
    * ``partial_entries`` is a one-element tuple equal to the row's entry
      fields (always populated, never empty for a valid row).
    * ``partial_exits`` is a one-element tuple equal to the row's exit
      fields in the current single-fill-per-order scope; the field is
      symmetric so multi-fill OMS support can land later without schema
      migration.

Derived net ``Position`` view:
    The ``Position`` model is kept as a **derived snapshot** for the
    ``StrategyContext.get_position()`` API. For multi-lot positions the
    snapshot reports the **weighted-average entry price** and the
    **earliest open-lot timestamp** so the snapshot is well-defined; the
    lot deque remains the source of truth for attribution.

Validation rejects orders with non-positive quantity or non-finite price
(``NaN`` / ``±inf``). Rejected orders are returned with
``status=REJECTED`` AND recorded in the audit trail so the trail is
complete.

PnL formula: ``(exit_price - entry_price) * quantity * side_multiplier``,
where ``side_multiplier`` is ``+1`` for LONG and ``-1`` for SHORT.

Performance note: per-candle worst case is O(closes × lots). For most
strategies this is O(1) per candle because each close consumes O(1) lots
at the head of the deque.
"""

import math
from collections import deque
from datetime import datetime
from typing import Deque, Dict, List, Optional

from ..models.enums import OrderSide, OrderType, OrderStatus, PositionSide
from ..models.lot import Lot, PartialLeg
from ..models.order import Order
from ..models.position import Position
from ..models.trade import TradeRecord


def _same_sign(a: float, b: float) -> bool:
    """Return True if ``a`` and ``b`` share the same sign (or are both zero)."""
    return (a >= 0 and b >= 0) or (a <= 0 and b <= 0)


class PositionManager:
    """Authoritative order/position state and behavior. Immediate acceptance, no fill simulation.

    The FIFO lot ledger is the single source of truth for attribution.
    The :class:`Position` returned by :meth:`get_position` is a derived
    snapshot (net quantity + weighted-average price + oldest open
    timestamp) computed from the lot deque on every read.
    """

    def __init__(self) -> None:
        self._orders: Dict[str, Order] = {}                       # Audit trail: order_id -> Order
        self._lots: Dict[str, Deque[Lot]] = {}                    # FIFO lots: symbol -> deque[Lot]
        self._closed_trades: List[TradeRecord] = []               # Completed trade records (FIFO-matched)
        self._order_counter: int = 0

    # ------------------------------------------------------------------
    # Lot ledger helpers (the source of truth for attribution)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_trade_for_lot(
        lot: Lot,
        quantity: float,
        exit_timestamp: datetime,
        exit_price: float,
    ) -> TradeRecord:
        """Build a single ``TradeRecord`` for one consumed lot slice.

        ``quantity`` is the absolute quantity of THIS matched leg (a
        sub-slice of ``lot``). PnL is computed against ``lot``'s basis
        (the actual unit closed), not a weighted average. ``partial_entries``
        is always one element equal to the consumed lot's basis; even when
        a single close event emits multiple ``TradeRecord`` rows, each
        row's ``partial_entries`` reflects only the lot it consumed.
        ``partial_exits`` is one element equal to the row's exit fields
        in single-fill scope.
        """
        side_multiplier = 1.0 if lot.side == PositionSide.LONG else -1.0
        pnl = (exit_price - lot.open_price) * quantity * side_multiplier
        return TradeRecord(
            symbol=lot.symbol,
            side=lot.side,
            quantity=quantity,
            entry_timestamp=lot.open_timestamp,
            entry_price=lot.open_price,
            exit_timestamp=exit_timestamp,
            exit_price=exit_price,
            pnl=pnl,
            partial_entries=(PartialLeg(lot.open_timestamp, lot.open_price, quantity),),
            partial_exits=(PartialLeg(exit_timestamp, exit_price, quantity),),
        )

    def _total_quantity(self, symbol: str) -> float:
        """Return the signed net quantity for ``symbol`` (sum of lot quantities × side sign)."""
        lots = self._lots.get(symbol)
        if not lots:
            return 0.0
        sign = 1.0 if lots[0].side == PositionSide.LONG else -1.0
        return sign * sum(lot.quantity for lot in lots)

    def _oldest_open_timestamp(self, symbol: str) -> Optional[datetime]:
        """Return the open timestamp of the head lot, or ``None`` if no lots."""
        lots = self._lots.get(symbol)
        if not lots:
            return None
        return lots[0].open_timestamp

    def _oldest_open_price(self, symbol: str) -> float:
        """Return the open price of the head (oldest) lot, or ``0.0`` if no lots.

        Used as the derived ``Position.entry_price`` snapshot. Choosing
        the **oldest lot's open price** (not a weighted average) keeps
        the snapshot identical to the legacy single-Position semantics
        for single-lot positions, which is what most existing
        researcher code and the legacy tests expect. For multi-lot
        positions the snapshot reports the basis of the *first* lot —
        consistent with how most broker UIs and the Backtrader "position
        entry" convention display a position's entry. Lot-level
        attribution (what the user actually sold) is in
        :meth:`get_closed_trades` and :meth:`get_open_lots`.
        """
        lots = self._lots.get(symbol)
        if not lots:
            return 0.0
        return lots[0].open_price

    def _derive_position(self, symbol: str) -> Position:
        """Build a derived :class:`Position` snapshot from the lot deque.

        For a symbol with no open lots returns :meth:`Position.zero` —
        this matches the legacy fast-path of :meth:`get_position`. For
        symbols with open lots, the snapshot carries:

        * ``quantity`` = signed net quantity (sum across lots).
        * ``entry_price`` = oldest open lot's ``open_price`` (first-order
          basis, NOT a weighted average — see :meth:`_oldest_open_price`).
        * ``entry_timestamp`` = oldest open lot's ``open_timestamp``.

        ``position_side`` is derived from the sign of ``quantity`` in
        :meth:`Position.__post_init__`.
        """
        lots = self._lots.get(symbol)
        if not lots:
            return Position.zero(symbol)
        side = lots[0].side
        sign = 1.0 if side == PositionSide.LONG else -1.0
        net_qty = sign * sum(lot.quantity for lot in lots)
        return Position(
            entry_timestamp=self._oldest_open_timestamp(symbol) or datetime.min,
            entry_price=self._oldest_open_price(symbol),
            symbol=symbol,
            quantity=net_qty,
        )

    def _consume_lots_fifo(
        self,
        symbol: str,
        close_qty: float,
        exit_timestamp: datetime,
        exit_price: float,
    ) -> None:
        """Consume ``close_qty`` units from the head of the lot deque FIFO.

        Emits one ``TradeRecord`` per consumed lot-leg, with the matched
        lot's basis reflected in the row's entry fields. Mutates the
        head lot's ``quantity`` as it is partially consumed; pops the
        lot from the deque when its quantity reaches zero.

        Precondition: the symbol's net quantity and side match the
        close direction; the deque has enough quantity to satisfy the
        close. Caller (``apply``) is responsible for the flip / open
        transitions.
        """
        lots = self._lots[symbol]
        remaining = close_qty
        while remaining > 0:
            head = lots[0]
            take = min(head.quantity, remaining)
            self._closed_trades.append(
                self._build_trade_for_lot(
                    lot=head,
                    quantity=take,
                    exit_timestamp=exit_timestamp,
                    exit_price=exit_price,
                )
            )
            if head.quantity == take:
                # Lot fully consumed — drop it.
                lots.popleft()
            else:
                # Partial slice — replace head with a residual lot of the
                # same basis but reduced quantity. We need a NEW ``Lot``
                # because ``Lot`` is frozen+slots.
                lots[0] = Lot(
                    symbol=head.symbol,
                    side=head.side,
                    open_timestamp=head.open_timestamp,
                    open_price=head.open_price,
                    quantity=head.quantity - take,
                )
            remaining -= take
        if not lots:
            # All lots consumed — drop the empty deque entry to preserve
            # the legacy invariant "no zero-quantity phantom position".
            del self._lots[symbol]

    def _enqueue_lot(
        self,
        symbol: str,
        side: PositionSide,
        open_timestamp: datetime,
        open_price: float,
        quantity: float,
    ) -> None:
        """Append a new :class:`Lot` to the FIFO deque for ``symbol``.

        The deque is created on first use. Quantrex is single-fill-per-order,
        so each accepted order that opens or scales in produces exactly
        one new lot. No ``TradeRecord`` is emitted by an enqueue.
        """
        lot = Lot(
            symbol=symbol,
            side=side,
            open_timestamp=open_timestamp,
            open_price=open_price,
            quantity=quantity,
        )
        if symbol not in self._lots:
            self._lots[symbol] = deque()
        self._lots[symbol].append(lot)

    # ------------------------------------------------------------------
    # Order audit trail
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Core state machine
    # ------------------------------------------------------------------

    def apply(
        self,
        symbol: str,
        delta: float,
        timestamp: datetime,
        price: float,
    ) -> None:
        """Apply a signed position delta at the given price and time.

        This is the core 5-case position state machine, re-expressed
        in terms of the FIFO lot deque:

            1. No prior position → enqueue a fresh lot.
            2. Same-side update where |qty| grew → enqueue a new lot.
            3. Same-side update where |qty| shrank → consume head lots FIFO.
            4. Delta drives net quantity to zero → consume head lots FIFO
               until empty, then drop the symbol.
            5. Delta crosses zero (e.g. Long 10 → Sell 15) → consume all
               prior-side lots FIFO, then enqueue a fresh lot for the
               residual opposite side.

        Called by :meth:`submit_order` for immediately-filled orders and
        by :class:`quantrex_backtest.core.engine.BacktestEngine` for T+1
        drained orders.
        """
        current_qty = self._total_quantity(symbol)

        if current_qty == 0.0:
            # Case 1: open fresh.
            side = PositionSide.LONG if delta >= 0 else PositionSide.SHORT
            self._enqueue_lot(
                symbol=symbol,
                side=side,
                open_timestamp=timestamp,
                open_price=price,
                quantity=abs(delta),
            )
            return

        new_qty = current_qty + delta

        if new_qty == 0:
            # Case 4: full close (consume everything, drop symbol).
            self._consume_lots_fifo(
                symbol=symbol,
                close_qty=abs(current_qty),
                exit_timestamp=timestamp,
                exit_price=price,
            )
            return

        if not _same_sign(current_qty, new_qty):
            # Case 5: flip. Close the entire prior side, then open the
            # residual opposite side as a fresh lot.
            self._consume_lots_fifo(
                symbol=symbol,
                close_qty=abs(current_qty),
                exit_timestamp=timestamp,
                exit_price=price,
            )
            new_side = PositionSide.LONG if new_qty > 0 else PositionSide.SHORT
            self._enqueue_lot(
                symbol=symbol,
                side=new_side,
                open_timestamp=timestamp,
                open_price=price,
                quantity=abs(new_qty),
            )
            return

        # Cases 2 and 3 share a sign (same-side update). Distinguish by
        # whether |qty| grew (scale-in) or scale-out.
        if abs(new_qty) > abs(current_qty):
            # Case 2: scale-in — enqueue a new lot at the new order's basis.
            self._enqueue_lot(
                symbol=symbol,
                side=PositionSide.LONG if new_qty > 0 else PositionSide.SHORT,
                open_timestamp=timestamp,
                open_price=price,
                quantity=abs(new_qty - current_qty),
            )
        else:
            # Case 3: scale-out / partial close — consume head lots FIFO.
            self._consume_lots_fifo(
                symbol=symbol,
                close_qty=abs(current_qty - new_qty),
                exit_timestamp=timestamp,
                exit_price=price,
            )

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def get_position(self, symbol: str) -> Position:
        """Return a derived ``Position`` snapshot for ``symbol``.

        The snapshot reports net quantity, the **oldest open-lot entry
        price** (first-order basis — see :meth:`_oldest_open_price` for
        rationale), and the oldest open-lot timestamp. Returns
        :meth:`Position.zero` if the symbol has no open lots.

        Note: the snapshot is a *research convenience* and must NOT be
        used for P&L attribution. Lot-level attribution lives in
        :meth:`get_closed_trades` (per-row) and :meth:`get_open_lots`
        (current exposure).
        """
        return self._derive_position(symbol)

    def get_all_positions(self) -> List[Position]:
        """Return a list of derived ``Position`` snapshots for all symbols with open lots."""
        return [self._derive_position(symbol) for symbol in self._lots.keys()]

    def get_open_lots(self, symbol: str) -> List[Lot]:
        """Return a copy of the FIFO open-lot list for ``symbol`` (oldest first).

        Empty list if the symbol has no open lots. Useful for advanced
        post-run analysis without bloating the trade CSV with every
        individual lot.
        """
        lots = self._lots.get(symbol)
        if not lots:
            return []
        return list(lots)

    def get_closed_trades(self) -> List[TradeRecord]:
        """Return a copy of all closed trade records, in insertion (FIFO-emission) order.

        Each ``TradeRecord`` represents one (consumed lot, exit fill)
        pair. A single close order that consumes N lots yields N
        consecutive ``TradeRecord`` rows in this list (in FIFO order).
        """
        return list(self._closed_trades)
