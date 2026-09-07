"""Unit tests for :class:`quantrex_core.position.PositionManager`.

Covers all five position-lifecycle operations and their edge cases:

1. **Open** — first order for a symbol creates a new ``Position`` whose
   entry basis comes from the order.
2. **Scale-in** — adding to an existing same-side position preserves the
   original entry basis (no ``TradeRecord``).
3. **Scale-out / partial close** — reducing an existing same-side
   position emits one ``TradeRecord`` for the closed portion.
4. **Full close** — an order that drives net quantity to zero emits one
   ``TradeRecord`` and removes the symbol from the position map.
5. **Flip** — an order whose delta crosses zero emits one ``TradeRecord``
   for the full closed quantity of the prior side and opens a fresh
   ``Position`` for the residual opposite-side quantity with the flip
   order's price/time as its entry basis.

Also covers validation (rejection of non-positive quantity and non-finite
price), audit-trail completeness (rejected orders recorded), determinism
of order ids, and multi-symbol isolation.
"""

from datetime import datetime
import math

import pytest

from quantrex_core.models.enums import OrderSide, OrderStatus, OrderType, PositionSide
from quantrex_core.models.position import Position
from quantrex_core.position import PositionManager


# Test fixtures ----------------------------------------------------------

T0 = datetime(2026, 1, 1, 9, 30)
T1 = datetime(2026, 1, 1, 9, 31)
T2 = datetime(2026, 1, 1, 9, 32)
T3 = datetime(2026, 1, 1, 9, 33)


def _market(pm: PositionManager, symbol: str, side: OrderSide, qty: float,
            ts: datetime, price: float):
    """Submit a MARKET order through the manager and return the Order."""
    order = pm._record_order(symbol, side, qty, OrderType.MARKET, ts, price)
    if order.status == OrderStatus.ACCEPTED:
        delta = qty if side == OrderSide.BUY else -qty
        pm.apply(symbol, delta, ts, price)
    return order


# Case 1: Open -----------------------------------------------------------

class TestOpen:
    """Open a fresh position from a flat state."""

    def test_open_long_creates_long_position(self):
        pm = PositionManager()
        order = _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, 100.0)

        assert order.status is OrderStatus.ACCEPTED
        pos = pm.get_position("AAPL")
        assert pos.symbol == "AAPL"
        assert pos.quantity == 10.0
        assert pos.position_side is PositionSide.LONG
        assert pos.entry_price == 100.0
        assert pos.entry_timestamp == T0
        assert pm.get_closed_trades() == []

    def test_open_short_creates_short_position(self):
        pm = PositionManager()
        order = _market(pm, "MSFT", OrderSide.SELL, 7.5, T0, 200.0)

        assert order.status is OrderStatus.ACCEPTED
        pos = pm.get_position("MSFT")
        assert pos.quantity == -7.5
        assert pos.position_side is PositionSide.SHORT
        assert pos.entry_price == 200.0
        assert pos.entry_timestamp == T0


# Case 2: Scale-in -------------------------------------------------------

class TestScaleIn:
    """Add to an existing same-side position without emitting a trade."""

    def test_scale_in_long_preserves_entry_basis(self):
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, 100.0)
        _market(pm, "AAPL", OrderSide.BUY, 5.0, T1, 110.0)

        pos = pm.get_position("AAPL")
        assert pos.quantity == 15.0
        assert pos.position_side is PositionSide.LONG
        # Entry basis preserved from the FIRST order.
        assert pos.entry_price == 100.0
        assert pos.entry_timestamp == T0
        assert pm.get_closed_trades() == []

    def test_scale_in_short_preserves_entry_basis(self):
        pm = PositionManager()
        _market(pm, "MSFT", OrderSide.SELL, 10.0, T0, 200.0)
        _market(pm, "MSFT", OrderSide.SELL, 5.0, T1, 220.0)

        pos = pm.get_position("MSFT")
        assert pos.quantity == -15.0
        assert pos.position_side is PositionSide.SHORT
        assert pos.entry_price == 200.0
        assert pos.entry_timestamp == T0
        assert pm.get_closed_trades() == []


# Case 3: Scale-out / partial close --------------------------------------

class TestScaleOut:
    """Reduce an existing same-side position; emit one TradeRecord."""

    def test_scale_out_long_emits_trade_record(self):
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, 100.0)
        order = _market(pm, "AAPL", OrderSide.SELL, 4.0, T1, 110.0)

        assert order.status is OrderStatus.ACCEPTED
        pos = pm.get_position("AAPL")
        assert pos.quantity == 6.0
        assert pos.position_side is PositionSide.LONG
        # Entry basis preserved.
        assert pos.entry_price == 100.0
        assert pos.entry_timestamp == T0

        trades = pm.get_closed_trades()
        assert len(trades) == 1
        tr = trades[0]
        assert tr.symbol == "AAPL"
        assert tr.side is PositionSide.LONG
        assert tr.quantity == 4.0
        assert tr.entry_price == 100.0
        assert tr.exit_price == 110.0
        # PnL = (110 - 100) * 4 * 1 = 40.
        assert tr.pnl == pytest.approx(40.0)

    def test_scale_out_short_emits_trade_record(self):
        pm = PositionManager()
        _market(pm, "MSFT", OrderSide.SELL, 10.0, T0, 200.0)
        order = _market(pm, "MSFT", OrderSide.BUY, 4.0, T1, 190.0)

        assert order.status is OrderStatus.ACCEPTED
        pos = pm.get_position("MSFT")
        assert pos.quantity == -6.0
        assert pos.position_side is PositionSide.SHORT
        assert pos.entry_price == 200.0

        trades = pm.get_closed_trades()
        assert len(trades) == 1
        tr = trades[0]
        assert tr.side is PositionSide.SHORT
        assert tr.quantity == 4.0
        assert tr.entry_price == 200.0
        assert tr.exit_price == 190.0
        # PnL = (190 - 200) * 4 * -1 = 40.
        assert tr.pnl == pytest.approx(40.0)

    def test_multiple_partial_closes_each_emit_trade(self):
        """Three partial closes summing to the full position each emit a trade."""
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, 100.0)
        _market(pm, "AAPL", OrderSide.SELL, 3.0, T1, 110.0)
        _market(pm, "AAPL", OrderSide.SELL, 3.0, T2, 115.0)
        _market(pm, "AAPL", OrderSide.SELL, 4.0, T3, 120.0)

        # Position is fully closed and removed.
        assert "AAPL" not in pm._lots
        assert pm.get_position("AAPL").quantity == 0.0
        assert pm.get_all_positions() == []

        trades = pm.get_closed_trades()
        assert len(trades) == 3
        # Each trade references the same entry basis.
        for tr in trades:
            assert tr.entry_price == 100.0
            assert tr.entry_timestamp == T0
            assert tr.side is PositionSide.LONG
        # Closed quantities sum to 10.
        assert sum(t.quantity for t in trades) == pytest.approx(10.0)
        # PnLs: (110-100)*3=30, (115-100)*3=45, (120-100)*4=80.
        assert [t.pnl for t in trades] == pytest.approx([30.0, 45.0, 80.0])


# Case 4: Full close -----------------------------------------------------

class TestFullClose:
    """Drive net quantity to zero; remove the position from state."""

    def test_full_close_long_removes_position(self):
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, 100.0)
        order = _market(pm, "AAPL", OrderSide.SELL, 10.0, T1, 110.0)

        assert order.status is OrderStatus.ACCEPTED
        # Position is removed from the map.
        assert "AAPL" not in pm._lots
        # get_position() returns Position.zero via fast-path.
        flat = pm.get_position("AAPL")
        assert flat.quantity == 0.0
        assert flat.symbol == "AAPL"
        # No phantom position in get_all_positions().
        assert pm.get_all_positions() == []

        trades = pm.get_closed_trades()
        assert len(trades) == 1
        tr = trades[0]
        assert tr.side is PositionSide.LONG
        assert tr.quantity == 10.0
        assert tr.entry_price == 100.0
        assert tr.exit_price == 110.0
        # PnL = (110 - 100) * 10 * 1 = 100.
        assert tr.pnl == pytest.approx(100.0)

    def test_full_close_short_removes_position(self):
        pm = PositionManager()
        _market(pm, "MSFT", OrderSide.SELL, 10.0, T0, 200.0)
        order = _market(pm, "MSFT", OrderSide.BUY, 10.0, T1, 190.0)

        assert order.status is OrderStatus.ACCEPTED
        assert "MSFT" not in pm._lots
        assert pm.get_all_positions() == []

        trades = pm.get_closed_trades()
        assert len(trades) == 1
        tr = trades[0]
        assert tr.side is PositionSide.SHORT
        assert tr.quantity == 10.0
        assert tr.entry_price == 200.0
        assert tr.exit_price == 190.0
        # PnL = (190 - 200) * 10 * -1 = 100.
        assert tr.pnl == pytest.approx(100.0)

    def test_close_then_reopen_uses_new_entry_basis(self):
        """After a full close, a new open uses the NEW order's basis (not the old)."""
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, 100.0)
        _market(pm, "AAPL", OrderSide.SELL, 10.0, T1, 110.0)  # full close
        _market(pm, "AAPL", OrderSide.BUY, 5.0, T2, 120.0)    # reopen

        pos = pm.get_position("AAPL")
        assert pos.quantity == 5.0
        assert pos.position_side is PositionSide.LONG
        # New entry basis, not the old one.
        assert pos.entry_price == 120.0
        assert pos.entry_timestamp == T2
        # Only the original round-trip produced a trade.
        assert len(pm.get_closed_trades()) == 1


# Case 5: Flip -----------------------------------------------------------

class TestFlip:
    """Cross zero: full close of the old side + fresh open of the new side."""

    def test_flip_long_to_short_emits_close_and_opens_new_short(self):
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, 100.0)
        _market(pm, "AAPL", OrderSide.SELL, 15.0, T1, 110.0)

        pos = pm.get_position("AAPL")
        # Residual is a fresh SHORT, with the flip order as its entry.
        assert pos.quantity == -5.0
        assert pos.position_side is PositionSide.SHORT
        assert pos.entry_price == 110.0
        assert pos.entry_timestamp == T1

        # One TradeRecord for the FULL close of the prior long side (10).
        trades = pm.get_closed_trades()
        assert len(trades) == 1
        tr = trades[0]
        assert tr.symbol == "AAPL"
        assert tr.side is PositionSide.LONG
        assert tr.quantity == 10.0
        assert tr.entry_price == 100.0
        assert tr.entry_timestamp == T0
        assert tr.exit_price == 110.0
        assert tr.exit_timestamp == T1
        # PnL = (110 - 100) * 10 * 1 = 100.
        assert tr.pnl == pytest.approx(100.0)

    def test_flip_short_to_long_emits_close_and_opens_new_long(self):
        pm = PositionManager()
        _market(pm, "MSFT", OrderSide.SELL, 10.0, T0, 200.0)
        _market(pm, "MSFT", OrderSide.BUY, 15.0, T1, 190.0)

        pos = pm.get_position("MSFT")
        assert pos.quantity == 5.0
        assert pos.position_side is PositionSide.LONG
        assert pos.entry_price == 190.0
        assert pos.entry_timestamp == T1

        trades = pm.get_closed_trades()
        assert len(trades) == 1
        tr = trades[0]
        assert tr.side is PositionSide.SHORT
        assert tr.quantity == 10.0
        assert tr.entry_price == 200.0
        assert tr.exit_price == 190.0
        # PnL = (190 - 200) * 10 * -1 = 100.
        assert tr.pnl == pytest.approx(100.0)

    def test_flip_then_scale_out_preserves_fresh_entry_basis(self):
        """A flip opens a fresh position; subsequent scale-out uses that basis."""
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, 100.0)     # long 10 @ 100
        _market(pm, "AAPL", OrderSide.SELL, 20.0, T1, 110.0)    # flip → short 10 @ 110
        _market(pm, "AAPL", OrderSide.BUY, 5.0, T2, 120.0)      # scale-out 5 of short

        pos = pm.get_position("AAPL")
        # After scale-out: short 5, entry basis = 110 (the flip price, not 100).
        assert pos.quantity == -5.0
        assert pos.position_side is PositionSide.SHORT
        assert pos.entry_price == 110.0
        assert pos.entry_timestamp == T1

        trades = pm.get_closed_trades()
        assert len(trades) == 2
        # Trade 1: full close of original long 10 @ 100 → 110, pnl = 100.
        assert trades[0].side is PositionSide.LONG
        assert trades[0].quantity == 10.0
        assert trades[0].entry_price == 100.0
        assert trades[0].exit_price == 110.0
        assert trades[0].pnl == pytest.approx(100.0)
        # Trade 2: scale-out 5 of short 10 @ 110 → 120, pnl = (120-110)*5*-1 = -50.
        assert trades[1].side is PositionSide.SHORT
        assert trades[1].quantity == 5.0
        assert trades[1].entry_price == 110.0
        assert trades[1].exit_timestamp == T2
        assert trades[1].pnl == pytest.approx(-50.0)

    def test_flip_long_to_exact_short_closes_position(self):
        """A flip that exactly nets to short qty (delta == -2*current) closes all long, opens short."""
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 5.0, T0, 100.0)
        # Sell 10 flips long 5 to short 5.
        _market(pm, "AAPL", OrderSide.SELL, 10.0, T1, 110.0)

        pos = pm.get_position("AAPL")
        assert pos.quantity == -5.0
        assert pos.position_side is PositionSide.SHORT
        assert pos.entry_price == 110.0
        assert pos.entry_timestamp == T1
        assert len(pm.get_closed_trades()) == 1
        assert pm.get_closed_trades()[0].quantity == 5.0


# Validation ------------------------------------------------------------

class TestValidation:
    """Reject invalid orders; do not mutate state on rejection."""

    def test_rejects_zero_quantity(self):
        pm = PositionManager()
        order = _market(pm, "AAPL", OrderSide.BUY, 0.0, T0, 100.0)

        assert order.status is OrderStatus.REJECTED
        # No position created.
        assert "AAPL" not in pm._lots
        assert pm.get_all_positions() == []
        assert pm.get_closed_trades() == []

    def test_rejects_negative_quantity(self):
        pm = PositionManager()
        order = _market(pm, "AAPL", OrderSide.BUY, -5.0, T0, 100.0)

        assert order.status is OrderStatus.REJECTED
        assert "AAPL" not in pm._lots

    def test_rejects_nan_price(self):
        pm = PositionManager()
        order = _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, math.nan)

        assert order.status is OrderStatus.REJECTED
        assert "AAPL" not in pm._lots

    def test_rejects_inf_price(self):
        pm = PositionManager()
        order = _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, math.inf)

        assert order.status is OrderStatus.REJECTED
        assert "AAPL" not in pm._lots

    def test_rejects_negative_inf_price(self):
        pm = PositionManager()
        order = _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, -math.inf)

        assert order.status is OrderStatus.REJECTED
        assert "AAPL" not in pm._lots

    def test_rejected_zero_qty_does_not_pollute_audit_ids(self):
        """Counter must still advance so subsequent accepted orders get the next id."""
        pm = PositionManager()
        bad = _market(pm, "AAPL", OrderSide.BUY, 0.0, T0, 100.0)
        good = _market(pm, "AAPL", OrderSide.BUY, 5.0, T0, 100.0)

        assert bad.id == "1"
        assert good.id == "2"
        assert len(pm._orders) == 2


# Audit trail -----------------------------------------------------------

class TestAuditTrail:
    """The audit trail records every submitted order (accepted + rejected)."""

    def test_audit_trail_records_all_accepted_orders(self):
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, 100.0)
        _market(pm, "AAPL", OrderSide.SELL, 4.0, T1, 110.0)
        _market(pm, "MSFT", OrderSide.BUY, 5.0, T0, 50.0)

        assert len(pm._orders) == 3
        assert [o.id for o in pm._orders.values()] == ["1", "2", "3"]
        assert all(o.status is OrderStatus.ACCEPTED for o in pm._orders.values())

    def test_audit_trail_records_accepted_and_rejected_orders(self):
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, 100.0)        # accepted
        _market(pm, "AAPL", OrderSide.BUY, 0.0, T0, 100.0)         # rejected
        _market(pm, "AAPL", OrderSide.SELL, 4.0, T1, 110.0)        # accepted
        _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, math.nan)     # rejected
        _market(pm, "AAPL", OrderSide.SELL, 6.0, T1, 120.0)        # accepted

        assert len(pm._orders) == 5
        statuses = [o.status for o in pm._orders.values()]
        assert statuses == [
            OrderStatus.ACCEPTED,
            OrderStatus.REJECTED,
            OrderStatus.ACCEPTED,
            OrderStatus.REJECTED,
            OrderStatus.ACCEPTED,
        ]


# Determinism -----------------------------------------------------------

class TestDeterminism:
    """Order ids are sequential; trades preserve insertion order."""

    def test_order_ids_are_sequential(self):
        pm = PositionManager()
        ids = []
        for i in range(5):
            o = _market(pm, "AAPL", OrderSide.BUY, 1.0, T0, 100.0 + i)
            ids.append(o.id)
        assert ids == ["1", "2", "3", "4", "5"]

    def test_trade_records_in_order_of_close(self):
        """``get_closed_trades`` preserves chronological order of close events."""
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, 100.0)
        _market(pm, "AAPL", OrderSide.SELL, 4.0, T1, 110.0)
        _market(pm, "AAPL", OrderSide.SELL, 6.0, T2, 120.0)

        trades = pm.get_closed_trades()
        assert [t.exit_timestamp for t in trades] == [T1, T2]


# Multi-symbol isolation -----------------------------------------------

class TestMultiSymbol:
    """Operations on one symbol never affect another."""

    def test_multi_symbol_positions_isolated(self):
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, 100.0)
        _market(pm, "MSFT", OrderSide.BUY, 20.0, T0, 50.0)
        # Scale-out AAPL only.
        _market(pm, "AAPL", OrderSide.SELL, 5.0, T1, 110.0)

        aapl = pm.get_position("AAPL")
        msft = pm.get_position("MSFT")
        assert aapl.quantity == 5.0
        assert msft.quantity == 20.0
        # Only AAPL has a trade.
        trades = pm.get_closed_trades()
        assert len(trades) == 1
        assert trades[0].symbol == "AAPL"
        assert trades[0].quantity == 5.0

    def test_get_all_positions_lists_all_open_symbols(self):
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 5.0, T0, 100.0)
        _market(pm, "MSFT", OrderSide.SELL, 8.0, T0, 50.0)
        _market(pm, "GOOG", OrderSide.BUY, 2.0, T0, 1000.0)
        # Close AAPL fully.
        _market(pm, "AAPL", OrderSide.SELL, 5.0, T1, 110.0)

        symbols = {p.symbol for p in pm.get_all_positions()}
        assert symbols == {"MSFT", "GOOG"}


# Round-trip parity with backtest fixtures -----------------------------

class TestRoundTripParity:
    """Behavior compatible with the existing backtest integration tests.

    These reproduce the order sequences from ``PartialCloseStrategy`` and
    ``TradeRecordingStrategy`` in ``packages/backtest/tests/test_engine.py``
    to guarantee the rewritten manager produces the same trade records.
    """

    def test_partial_close_strategy_emits_two_trades(self):
        """BUY 20 @ 100, SELL 10 @ 100.50, SELL 10 @ 101.00 → 2 trades."""
        pm = PositionManager()
        _market(pm, "COPPER", OrderSide.BUY, 20.0, T0, 100.00)
        _market(pm, "COPPER", OrderSide.SELL, 10.0, T1, 100.50)
        _market(pm, "COPPER", OrderSide.SELL, 10.0, T2, 101.00)

        assert pm.get_position("COPPER").quantity == 0.0
        assert "COPPER" not in pm._lots

        trades = pm.get_closed_trades()
        assert len(trades) == 2
        # Trade 1: partial close of 10 @ 100 → 100.50, pnl = 5.
        assert trades[0].quantity == 10.0
        assert trades[0].entry_price == 100.0
        assert trades[0].exit_price == 100.50
        assert trades[0].pnl == pytest.approx(5.0)
        # Trade 2: full close of remaining 10 @ 100 → 101.00, pnl = 10.
        assert trades[1].quantity == 10.0
        assert trades[1].entry_price == 100.0
        assert trades[1].exit_price == 101.0
        assert trades[1].pnl == pytest.approx(10.0)

    def test_trade_recording_strategy_emits_one_trade(self):
        """BUY 10 @ 100, SELL 10 @ 101.00 → 1 trade, pnl = 10."""
        pm = PositionManager()
        _market(pm, "COPPER", OrderSide.BUY, 10.0, T0, 100.00)
        _market(pm, "COPPER", OrderSide.SELL, 10.0, T2, 101.00)

        assert "COPPER" not in pm._lots
        trades = pm.get_closed_trades()
        assert len(trades) == 1
        assert trades[0].quantity == 10.0
        assert trades[0].entry_price == 100.0
        assert trades[0].exit_price == 101.0
        assert trades[0].pnl == pytest.approx(10.0)

    def test_short_round_trip_emits_short_trade(self):
        """SELL 10 @ 100, BUY 10 @ 101.00 → 1 SHORT trade, pnl = -10."""
        pm = PositionManager()
        _market(pm, "COPPER", OrderSide.SELL, 10.0, T0, 100.00)
        _market(pm, "COPPER", OrderSide.BUY, 10.0, T2, 101.00)

        assert "COPPER" not in pm._lots
        trades = pm.get_closed_trades()
        assert len(trades) == 1
        assert trades[0].side is PositionSide.SHORT
        assert trades[0].quantity == 10.0
        assert trades[0].entry_price == 100.0
        assert trades[0].exit_price == 101.0
        # PnL = (101 - 100) * 10 * -1 = -10.
        assert trades[0].pnl == pytest.approx(-10.0)


# Position invariant: position_side derived from quantity sign ----------

class TestPositionSideInvariant:
    """Regression tests for the ``position_side`` ↔ ``quantity`` invariant.

    Locked in by the discovery observation of 2026-09-02:
    ``Position.zero()`` previously hardcoded ``PositionSide.LONG`` for any
    flat symbol, and the ``Position`` dataclass stored both ``quantity``
    (signed) and ``position_side`` independently, allowing them to
    disagree.

    After the fix:
    * ``position_side`` is derived from the sign of ``quantity`` in
      :meth:`Position.__post_init__` and overwrites whatever the caller
      passed.
    * The zero-quantity sentinel (``Position.zero(symbol)`` and the
      ``PositionManager.get_position`` fast-path) now reports
      :attr:`PositionSide.FLAT`, not :attr:`PositionSide.LONG`.
    * The constructor cannot produce a ``Position`` whose
      ``position_side`` disagrees with the sign of its ``quantity``.
    """

    def test_position_zero_reports_flat_not_long(self):
        """``Position.zero(symbol).position_side`` is ``FLAT`` (regression).

        Reproduces the original defect: before the fix, ``Position.zero``
        hardcoded ``position_side=PositionSide.LONG`` for any flat
        symbol, which misrepresented "no exposure" as a long position.
        """
        z = Position.zero("COPPER")
        assert z.quantity == 0.0
        assert z.position_side is PositionSide.FLAT

    def test_constructor_corrects_mismatched_position_side_to_long(self):
        """Passing ``SHORT`` with ``quantity > 0`` is corrected to ``LONG``."""
        p = Position(T0, 100.0, "AAPL", 5.0, PositionSide.SHORT)
        assert p.quantity == 5.0
        assert p.position_side is PositionSide.LONG

    def test_constructor_corrects_mismatched_position_side_to_short(self):
        """Passing ``LONG`` with ``quantity < 0`` is corrected to ``SHORT``."""
        p = Position(T0, 100.0, "AAPL", -5.0, PositionSide.LONG)
        assert p.quantity == -5.0
        assert p.position_side is PositionSide.SHORT

    def test_constructor_with_zero_quantity_reports_flat(self):
        """Passing ``quantity=0`` produces ``FLAT`` regardless of the side arg."""
        p = Position(T0, 100.0, "AAPL", 0.0, PositionSide.LONG)
        assert p.quantity == 0.0
        assert p.position_side is PositionSide.FLAT

    def test_get_position_fast_path_returns_flat(self):
        """``PositionManager.get_position`` for an unopened symbol returns FLAT."""
        pm = PositionManager()
        flat = pm.get_position("NEVER_OPENED")
        assert flat.quantity == 0.0
        assert flat.position_side is PositionSide.FLAT

    def test_get_position_after_full_close_returns_flat(self):
        """Fast-path after a full close must also report ``FLAT``."""
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 10.0, T0, 100.0)
        _market(pm, "AAPL", OrderSide.SELL, 10.0, T1, 110.0)
        flat = pm.get_position("AAPL")
        assert flat.quantity == 0.0
        assert flat.position_side is PositionSide.FLAT

    def test_equality_and_hash_agree_on_derived_side(self):
        """Two ``Position``s with same quantity are equal regardless of the
        (ignored) ``position_side`` argument, because the field is
        derived from ``quantity`` in ``__post_init__``."""
        p1 = Position(T0, 100.0, "AAPL", 5.0, PositionSide.LONG)
        p2 = Position(T0, 100.0, "AAPL", 5.0, PositionSide.SHORT)
        assert p1 == p2
        assert hash(p1) == hash(p2)
        assert p1.position_side is PositionSide.LONG
        assert p2.position_side is PositionSide.LONG


# FIFO lot accounting ---------------------------------------------------
#
# Regression coverage for the per-partial-close trade-reporting defect
# where the position-level single-entry basis was reused for every
# partial close, producing wrong P&L attribution and losing the actual
# lot → close mapping. With the FIFO lot ledger, every
# ``TradeRecord`` is matched to the specific lot that was actually
# consumed; the per-row ``entry_price`` / ``entry_timestamp`` are the
# matched lot's open price/time, never a weighted average or the first
# order's basis.

class TestFifoLotAccounting:
    """FIFO lot matching for partial closes and multi-lot positions."""

    def test_buy_two_lots_sell_three_splits_into_two_rows(self):
        """Regression: Buy 2@₹10 + Buy 2@₹20 → Sell 3@₹25 must yield TWO
        ``TradeRecord`` rows with DIFFERENT entry prices (one per lot),
        not a single row attributing all 3 units to the ₹10 lot.

        This is the exact scenario the user reported. Before the FIFO
        rewrite the manager emitted a single ``TradeRecord`` with
        ``entry_price=10, quantity=3, pnl=45`` — attributing the ₹20
        unit's profit to the ₹10 lot. The correct economic P&L is
        ``(25-10)*2 + (25-20)*1 = 35`` distributed across two rows.
        """
        pm = PositionManager()
        _market(pm, "COPPER", OrderSide.BUY, 2.0, T0, 10.0)
        _market(pm, "COPPER", OrderSide.BUY, 2.0, T1, 20.0)
        _market(pm, "COPPER", OrderSide.SELL, 3.0, T2, 25.0)

        trades = pm.get_closed_trades()
        assert len(trades) == 2

        # Row 1: full consumption of the ₹10 lot (qty=2, pnl=30).
        tr0 = trades[0]
        assert tr0.symbol == "COPPER"
        assert tr0.side is PositionSide.LONG
        assert tr0.quantity == 2.0
        assert tr0.entry_price == 10.0
        assert tr0.entry_timestamp == T0
        assert tr0.exit_price == 25.0
        assert tr0.exit_timestamp == T2
        assert tr0.pnl == pytest.approx(30.0)
        # partial_entries mirrors the row's own entry — one element.
        assert len(tr0.partial_entries) == 1
        assert tr0.partial_entries[0].price == 10.0
        assert tr0.partial_entries[0].quantity == 2.0
        assert tr0.partial_entries[0].timestamp == T0
        # partial_exits mirrors the row's own exit — one element.
        assert len(tr0.partial_exits) == 1
        assert tr0.partial_exits[0].price == 25.0
        assert tr0.partial_exits[0].quantity == 2.0

        # Row 2: partial consumption of the ₹20 lot (qty=1, pnl=5).
        tr1 = trades[1]
        assert tr1.symbol == "COPPER"
        assert tr1.side is PositionSide.LONG
        assert tr1.quantity == 1.0
        assert tr1.entry_price == 20.0
        assert tr1.entry_timestamp == T1
        assert tr1.exit_price == 25.0
        assert tr1.exit_timestamp == T2
        assert tr1.pnl == pytest.approx(5.0)
        assert len(tr1.partial_entries) == 1
        assert tr1.partial_entries[0].price == 20.0
        assert tr1.partial_entries[0].quantity == 1.0

        # Total economic P&L across the two rows matches the truth.
        assert sum(t.pnl for t in trades) == pytest.approx(35.0)

        # The residual ₹20 lot (qty=1) remains open.
        remaining = pm.get_open_lots("COPPER")
        assert len(remaining) == 1
        assert remaining[0].open_price == 20.0
        assert remaining[0].quantity == 1.0

    def test_three_lots_full_close_emits_three_rows(self):
        """Buy 1@10 + Buy 1@20 + Buy 1@30 → Sell 3@40 → 3 rows, one per lot."""
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 1.0, T0, 10.0)
        _market(pm, "AAPL", OrderSide.BUY, 1.0, T1, 20.0)
        _market(pm, "AAPL", OrderSide.BUY, 1.0, T2, 30.0)
        _market(pm, "AAPL", OrderSide.SELL, 3.0, T3, 40.0)

        trades = pm.get_closed_trades()
        assert len(trades) == 3
        # FIFO order: ₹10, then ₹20, then ₹30.
        assert [t.entry_price for t in trades] == [10.0, 20.0, 30.0]
        assert [t.quantity for t in trades] == [1.0, 1.0, 1.0]
        # PnLs: 30, 20, 10.
        assert [t.pnl for t in trades] == pytest.approx([30.0, 20.0, 10.0])
        # All three rows share the same exit (the close fill).
        assert all(t.exit_price == 40.0 for t in trades)
        assert all(t.exit_timestamp == T3 for t in trades)
        # All lots consumed — symbol is removed.
        assert "AAPL" not in pm._lots

    def test_single_lot_partial_close_one_row_with_self_partial(self):
        """Single-lot partial close (Buy 2@10 → Sell 1@15) emits ONE row whose
        ``partial_entries`` mirrors the row's own entry. This is the no-information-loss
        case: the ``partial_entries`` field is always populated, even for single-lot
        closes, so downstream consumers never need to branch on emptiness.
        """
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 2.0, T0, 10.0)
        _market(pm, "AAPL", OrderSide.SELL, 1.0, T1, 15.0)

        trades = pm.get_closed_trades()
        assert len(trades) == 1
        tr = trades[0]
        assert tr.quantity == 1.0
        assert tr.entry_price == 10.0
        assert tr.exit_price == 15.0
        assert tr.pnl == pytest.approx(5.0)
        # partial_entries and partial_exits are always populated.
        assert len(tr.partial_entries) == 1
        assert tr.partial_entries[0].price == 10.0
        assert tr.partial_entries[0].quantity == 1.0
        assert len(tr.partial_exits) == 1
        assert tr.partial_exits[0].price == 15.0
        assert tr.partial_exits[0].quantity == 1.0
        # Residual lot of 1@10 remains open.
        remaining = pm.get_open_lots("AAPL")
        assert len(remaining) == 1
        assert remaining[0].quantity == 1.0

    def test_scale_in_then_partial_close_uses_lot_one_basis(self):
        """Buy 2@10, then scale-in Buy 2@20 (no TradeRecord), then Sell 1@30.

        The 1-unit close consumes the head of the deque (the ₹10 lot)
        and emits one row with ``entry_price=10, quantity=1, pnl=20``.
        The ₹20 lot is untouched and remains open.
        """
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 2.0, T0, 10.0)
        _market(pm, "AAPL", OrderSide.BUY, 2.0, T1, 20.0)  # scale-in
        _market(pm, "AAPL", OrderSide.SELL, 1.0, T2, 30.0)

        trades = pm.get_closed_trades()
        assert len(trades) == 1
        tr = trades[0]
        assert tr.quantity == 1.0
        assert tr.entry_price == 10.0  # the HEAD lot, not the newest
        assert tr.exit_price == 30.0
        assert tr.pnl == pytest.approx(20.0)

        remaining = pm.get_open_lots("AAPL")
        # The head lot had qty 2, took 1 → residual qty 1 @ ₹10. Plus the
        # untouched ₹20 lot. So lots are [(T0,10,1), (T1,20,2)].
        assert len(remaining) == 2
        assert remaining[0].open_price == 10.0
        assert remaining[0].quantity == 1.0
        assert remaining[1].open_price == 20.0
        assert remaining[1].quantity == 2.0

    def test_over_close_flip_emits_lot_rows_for_prior_side(self):
        """Buy 2@10, then over-close Sell 5@30 (flip into SHORT 3).

        The Sell 5 first consumes all 2 of the ₹10 lot, emitting one row
        for the ₹10 basis, then opens a fresh SHORT lot of size 3 @ ₹30
        as the flip residual. NO row is emitted for the new short open.
        """
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 2.0, T0, 10.0)
        _market(pm, "AAPL", OrderSide.SELL, 5.0, T1, 30.0)

        trades = pm.get_closed_trades()
        assert len(trades) == 1
        tr = trades[0]
        assert tr.side is PositionSide.LONG
        assert tr.quantity == 2.0
        assert tr.entry_price == 10.0
        assert tr.exit_price == 30.0
        assert tr.pnl == pytest.approx(40.0)

        # Residual short 3 with entry at the flip order.
        pos = pm.get_position("AAPL")
        assert pos.quantity == -3.0
        assert pos.position_side is PositionSide.SHORT
        assert pos.entry_price == 30.0  # first-order (oldest) basis

        remaining = pm.get_open_lots("AAPL")
        assert len(remaining) == 1
        assert remaining[0].side is PositionSide.SHORT
        assert remaining[0].open_price == 30.0
        assert remaining[0].quantity == 3.0

    def test_flip_with_multiple_lots_consumes_all_then_opens_residual(self):
        """Regression: Buy 2@10 + Buy 2@20 + Sell 5@30 (flip into SHORT 1).

        Both prior-side lots are fully consumed, emitting two LONG rows
        (one per lot). The residual 1@30 short is opened as a new lot.
        """
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 2.0, T0, 10.0)
        _market(pm, "AAPL", OrderSide.BUY, 2.0, T1, 20.0)
        _market(pm, "AAPL", OrderSide.SELL, 5.0, T2, 30.0)

        trades = pm.get_closed_trades()
        assert len(trades) == 2
        # Row 1: full ₹10 lot.
        assert trades[0].entry_price == 10.0
        assert trades[0].quantity == 2.0
        assert trades[0].pnl == pytest.approx(40.0)
        # Row 2: full ₹20 lot.
        assert trades[1].entry_price == 20.0
        assert trades[1].quantity == 2.0
        assert trades[1].pnl == pytest.approx(20.0)

        pos = pm.get_position("AAPL")
        assert pos.quantity == -1.0
        assert pos.position_side is PositionSide.SHORT
        assert pos.entry_price == 30.0

    def test_short_lot_close_partial_uses_fifo(self):
        """Symmetric SHORT case: Sell 2@200 + Sell 2@220, Buy 3@210.

        The Buy 3 consumes the head of the short deque (the 200 lot)
        fully (qty=2) then a partial of the 220 lot (qty=1). Two
        SHORT rows emitted.

        PnL formula: ``(exit - entry) * qty * side_multiplier`` where
        side_multiplier is -1 for SHORT.

        Row 1: entry 200, exit 210, qty 2 → (210-200)*2*-1 = -20 (loss).
        Row 2: entry 220, exit 210, qty 1 → (210-220)*1*-1 = +10 (gain).
        """
        pm = PositionManager()
        _market(pm, "MSFT", OrderSide.SELL, 2.0, T0, 200.0)
        _market(pm, "MSFT", OrderSide.SELL, 2.0, T1, 220.0)
        _market(pm, "MSFT", OrderSide.BUY, 3.0, T2, 210.0)

        trades = pm.get_closed_trades()
        assert len(trades) == 2
        # FIFO for shorts: oldest open short lot consumed first.
        assert trades[0].side is PositionSide.SHORT
        assert trades[0].entry_price == 200.0
        assert trades[0].quantity == 2.0
        assert trades[0].pnl == pytest.approx(-20.0)
        assert trades[1].side is PositionSide.SHORT
        assert trades[1].entry_price == 220.0
        assert trades[1].quantity == 1.0
        assert trades[1].pnl == pytest.approx(10.0)

        # Residual short 1 @ 220.
        remaining = pm.get_open_lots("MSFT")
        assert len(remaining) == 1
        assert remaining[0].open_price == 220.0
        assert remaining[0].quantity == 1.0

    def test_get_open_lots_returns_oldest_first(self):
        """``get_open_lots`` returns the lot deque in FIFO insertion order."""
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 1.0, T0, 100.0)
        _market(pm, "AAPL", OrderSide.BUY, 1.0, T1, 110.0)
        _market(pm, "AAPL", OrderSide.BUY, 1.0, T2, 120.0)

        lots = pm.get_open_lots("AAPL")
        assert [(l.open_price, l.quantity, l.open_timestamp) for l in lots] == [
            (100.0, 1.0, T0),
            (110.0, 1.0, T1),
            (120.0, 1.0, T2),
        ]

    def test_partial_slice_of_head_lot_replaces_with_residual(self):
        """When a close consumes only part of the head lot, the residual
        must remain in the deque with the same basis but reduced qty —
        not disappear, and not be silently merged with the next lot.
        """
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 3.0, T0, 100.0)
        _market(pm, "AAPL", OrderSide.BUY, 1.0, T1, 200.0)
        _market(pm, "AAPL", OrderSide.SELL, 2.0, T2, 150.0)

        # Consume 2 from the head (₹100) lot. Residual of the head is 1@100.
        lots = pm.get_open_lots("AAPL")
        assert len(lots) == 2
        assert lots[0].open_price == 100.0
        assert lots[0].quantity == 1.0
        assert lots[1].open_price == 200.0
        assert lots[1].quantity == 1.0

        trades = pm.get_closed_trades()
        assert len(trades) == 1
        assert trades[0].entry_price == 100.0
        assert trades[0].quantity == 2.0
        assert trades[0].pnl == pytest.approx(100.0)  # (150-100)*2

    def test_get_position_snapshot_uses_oldest_lot_basis(self):
        """The derived ``Position`` snapshot's ``entry_price`` equals the
        OLDEST open lot's open price (first-order basis), not a weighted
        average. This preserves the legacy single-Position semantics for
        all single-lot positions and the most common multi-lot case.
        """
        pm = PositionManager()
        _market(pm, "AAPL", OrderSide.BUY, 1.0, T0, 100.0)
        _market(pm, "AAPL", OrderSide.BUY, 1.0, T1, 200.0)
        _market(pm, "AAPL", OrderSide.BUY, 1.0, T2, 300.0)

        pos = pm.get_position("AAPL")
        # Net qty is the sum across lots.
        assert pos.quantity == 3.0
        # entry_price is the OLDEST lot's open price, not a weighted avg
        # ((100+200+300)/3 = 200) and not the newest (300).
        assert pos.entry_price == 100.0
        # entry_timestamp is the oldest lot's open timestamp.
        assert pos.entry_timestamp == T0
