"""Trade record model for Quantrex framework.

Immutable record of a completed FIFO-matched trade leg. One
``TradeRecord`` is emitted for each (consumed lot, exit fill) pair —
i.e. a partial close that spans two open lots produces two
``TradeRecord`` rows, one per lot. This preserves the lot-level
attribution that brokers, IRS tax reporting, and institutional
backtesting frameworks use by default, and makes P&L auditable
against the actual executed lots rather than against a flat
position-level basis.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Tuple

from .enums import PositionSide
from .lot import PartialLeg


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """Immutable record of one FIFO-matched close leg.

    A ``TradeRecord`` represents the matched allocation of ``quantity``
    units from one or more open lots to a single exit fill. The
    primary ``entry_timestamp`` / ``entry_price`` fields point to the
    **earliest still-open lot that was actually consumed** (i.e. the
    first element of ``partial_entries``). For single-lot closes this
    is the only consumed lot. For multi-lot closes, the sibling rows
    emitted in the same close event each carry their own lot's basis
    in their own primary entry fields.

    The ``partial_entries`` and ``partial_exits`` collections enumerate
    every leg that contributed to THIS specific ``TradeRecord`` row.
    In the current (single-fill-per-order) scope, ``partial_exits`` is
    always a one-element tuple mirroring the row's exit fields;
    ``partial_entries`` is a one-element tuple for single-lot closes
    and a multi-element tuple (in FIFO order) for multi-lot closes
    only when the close spans more than one lot AND the row consumed
    a partial slice of a later lot. See
    :class:`quantrex_core.position.PositionManager` for the precise
    emission rules.

    The collections are JSON-serializable (each ``PartialLeg`` is a
    NamedTuple of primitives) so they can be exported to CSV as
    arrays for downstream analysis in pandas / Excel.

    Attributes:
        symbol: Trading symbol (e.g. "COPPER").
        side: LONG or SHORT (direction of the position being closed).
        quantity: Absolute quantity of THIS matched leg (always positive).
        entry_timestamp: When the matched lot was originally opened
            (the earliest open lot consumed by this row).
        entry_price: Price at which the matched lot was opened.
        exit_timestamp: When the close was filled.
        exit_price: Price at which the close was filled.
        pnl: Realized P&L for this matched leg:
            ``(exit_price - entry_price) * quantity * side_multiplier``.
        partial_entries: Per-lot FIFO allocations for the entry side
            contributing to this row. Always non-empty for valid rows.
        partial_exits: Per-fill allocations for the exit side
            contributing to this row. In single-fill scope this is one
            element mirroring the row's exit fields. Empty tuple by
            default for backward compatibility.
    """

    symbol: str
    side: PositionSide
    quantity: float
    entry_timestamp: datetime
    entry_price: float
    exit_timestamp: datetime
    exit_price: float
    pnl: float
    partial_entries: Tuple[PartialLeg, ...] = field(default=())
    partial_exits: Tuple[PartialLeg, ...] = field(default=())