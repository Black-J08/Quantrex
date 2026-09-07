"""Lot model for FIFO lot accounting.

A :class:`Lot` is the canonical ledger entry for an open portion of a
position. The :class:`quantrex_core.position.PositionManager` keeps one
FIFO queue of :class:`Lot` objects per symbol. Each filled BUY or SELL
order that opens (or scales into) exposure appends a fresh
:class:`Lot`; each order that reduces exposure consumes open
:class:`Lot` instances in FIFO order, emitting one
:class:`quantrex_core.models.trade.TradeRecord` per consumed lot.

Using lot-level (rather than position-level) state is the
industry-standard approach for multi-lot, partial-close scenarios. It
lets every realized trade carry the exact cost basis of the lot it
actually consumed, which is what brokers, IRS tax reporting, and
institutional backtesting frameworks (Backtrader, vectorbt) do by
default. Without lot-level state, a Sell 3 against Buy 2@₹10 +
Buy 2@₹20 cannot distinguish the ₹10 portion from the ₹20 portion in
the resulting P&L.

This module deliberately does NOT depend on :mod:`position` to avoid
circular imports; the manager composes them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

from .enums import PositionSide


class PartialLeg(NamedTuple):
    """A single (timestamp, price, quantity) leg of a partial allocation.

    Used to enumerate the per-lot FIFO allocations inside a
    :class:`quantrex_core.models.trade.TradeRecord` when a single close
    order consumes more than one open lot. Each leg records the
    timestamp and price of one side (entry or exit) of one matched
    quantity unit.

    Attributes:
        timestamp: Timestamp of the leg (open time for an entry leg,
            close time for an exit leg).
        price: Price of the leg.
        quantity: Absolute quantity of the leg (always positive).
    """

    timestamp: datetime
    price: float
    quantity: float


@dataclass(frozen=True, slots=True)
class Lot:
    """An open lot in the FIFO ledger for a single symbol/side.

    A :class:`Lot` represents the portion of a position opened by one
    filled order (a single price + timestamp). Lots for the same symbol
    and side are stored in a FIFO deque inside
    :class:`quantrex_core.position.PositionManager`. As reduce-orders
    consume lots, the consumed quantity is removed (and the lot is
    dropped from the deque when its remaining quantity reaches zero).

    Attributes:
        symbol: Trading symbol (e.g. "COPPER").
        side: LONG or SHORT.
        open_timestamp: When the lot was opened (order fill time).
        open_price: Price at which the lot was opened.
        quantity: Positive absolute quantity remaining in this lot.
            Strictly greater than zero; ``__post_init__`` rejects
            non-positive values and non-finite prices.
    """

    symbol: str
    side: PositionSide
    open_timestamp: datetime
    open_price: float
    quantity: float

    def __post_init__(self) -> None:
        """Validate that ``quantity > 0`` and ``open_price`` is finite.

        Uses :func:`object.__setattr__` is NOT needed because we raise
        rather than correct — the frozen+slots guard already prevents
        any later mutation, and an invalid :class:`Lot` would corrupt
        the ledger. ``__post_init__`` raising keeps the constructor
        contract strict.
        """
        if self.quantity <= 0:
            raise ValueError(
                f"Lot quantity must be > 0, got {self.quantity} for {self.symbol}"
            )
        if not math.isfinite(self.open_price):
            raise ValueError(
                f"Lot open_price must be finite, got {self.open_price} for {self.symbol}"
            )
