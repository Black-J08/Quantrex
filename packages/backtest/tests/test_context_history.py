"""Regression tests for ``BacktestStrategyContext.history`` and engine wiring.

A bug fix without a regression test is not a fix — see project AGENTS.md
"Standing Rule: Regression Tests for Every Bug Fix". These tests cover the
N-candle lookback feature end-to-end:

1. ``history`` grows one entry per processed bar and the current candle
   is always the last element (``history[-1]``).
2. The history observed inside ``on_candle`` is stable for the duration
   of that call and includes the current bar.
3. Warmup (fewer than N bars) yields a shorter tuple — never padded
   with ``None`` sentinels.
4. The returned tuple is immutable (``TypeError`` on item assignment),
   matching the documented contract.
5. The history survives across multiple ``on_candle`` calls and
   preserves chronological order across the full bar sequence.
"""

from datetime import datetime
from unittest.mock import Mock

import pytest

from quantrex_core import Candle, Strategy
from quantrex_core.protocols import DataAdapter
from quantrex_backtest import BacktestEngine, InstrumentSpec, BacktestConfig
from quantrex_backtest.core import BacktestStrategyContext
from quantrex_core.order import OrderManagementSystem
from quantrex_core.position.manager import PositionManager


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class _HistoryRecordingStrategy(Strategy):
    """Records ``ctx.history`` snapshot at the start of every ``on_candle``."""

    def __init__(self) -> None:
        super().__init__()
        # Snapshot of ``ctx.history`` as it appeared at the start of the
        # most recent ``on_candle`` call.
        self.last_history: tuple[Candle, ...] = ()
        # The complete sequence of history snapshots, one per bar.
        self.history_per_bar: list[tuple[Candle, ...]] = []
        # The complete sequence of candles the engine delivered, in
        # delivery order. Used to assert that ``ctx.history[-1]`` is the
        # same object the engine passed to ``on_candle``.
        self.candles: list[Candle] = []

    def on_candle(self, candle: Candle) -> None:
        # Snapshot once per call. ``ctx.history`` returns a fresh tuple
        # each time, so storing the reference is safe.
        snap = self.ctx.history
        self.last_history = snap
        self.history_per_bar.append(snap)
        self.candles.append(candle)


def _mock_adapter(rows: list[dict]) -> Mock:
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = rows
    adapter.datetime_format = "%Y%m%d %H:%M"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    return adapter


def _row(ts: str, o: float, h: float, l: float, c: float, v: float) -> dict:
    return {
        "datetime": ts,
        "open": str(o),
        "high": str(h),
        "low": str(l),
        "close": str(c),
        "volume": str(v),
    }


# ---------------------------------------------------------------------------
# Direct unit tests on BacktestStrategyContext (no engine).
# These pin down the contract at the context layer alone.
# ---------------------------------------------------------------------------


def test_history_is_empty_before_any_candle_recorded():
    """A fresh context has an empty history."""
    # Set current_time to a time after the close time of the candle (base timeframe is 1M by default)
    ctx = BacktestStrategyContext(PositionManager(), OrderManagementSystem(), datetime(2024, 1, 1, 9, 32))
    assert ctx.history == ()


def test_record_candle_appends_in_order():
    """``record_candle`` appends in the order called; ``history`` reflects that."""
    # Set current_time to a time after the close time of the last candle (base timeframe is 1M by default)
    ctx = BacktestStrategyContext(PositionManager(), OrderManagementSystem(), datetime(2024, 1, 1, 9, 33))
    candles = [
        Candle("X", datetime(2024, 1, 1, 9, 30), datetime(2024, 1, 1, 9, 31), "1M", 1, 2, 0.5, 1.5, 100),
        Candle("X", datetime(2024, 1, 1, 9, 31), datetime(2024, 1, 1, 9, 32), "1M", 2, 3, 1.5, 2.5, 200),
        Candle("X", datetime(2024, 1, 1, 9, 32), datetime(2024, 1, 1, 9, 33), "1M", 3, 4, 2.5, 3.5, 300),
    ]
    for c in candles:
        ctx.record_candle(c)

    history = ctx.history
    assert len(history) == 3
    # Chronological order preserved.
    assert history[0].timestamp == datetime(2024, 1, 1, 9, 30)
    assert history[1].timestamp == datetime(2024, 1, 1, 9, 31)
    assert history[2].timestamp == datetime(2024, 1, 1, 9, 32)
    # Current bar is the last element.
    assert history[-1] is candles[-1]


def test_history_is_immutable_tuple():
    """``ctx.history`` must be a tuple — assigning an item raises ``TypeError``.

    The contract says read-only; tuple semantics give us that for free
    without depending on the ``Candle`` itself being frozen.
    """
    ctx = BacktestStrategyContext(PositionManager(), OrderManagementSystem(), datetime.min)
    ctx.record_candle(
        Candle("X", datetime(2024, 1, 1, 9, 30), datetime(2024, 1, 1, 9, 31), "1M", 1, 2, 0.5, 1.5, 100)
    )

    with pytest.raises((TypeError, AttributeError)):
        ctx.history[0] = "mutated"  # type: ignore[index]


def test_history_returns_fresh_tuple_each_call():
    """Each access to ``ctx.history`` returns a fresh tuple (snapshot)."""
    # Set current_time to a time after the close time of the candle (base timeframe is 1M by default)
    ctx = BacktestStrategyContext(PositionManager(), OrderManagementSystem(), datetime(2024, 1, 1, 9, 32))
    ctx.record_candle(
        Candle("X", datetime(2024, 1, 1, 9, 30), datetime(2024, 1, 1, 9, 31), "1M", 1, 2, 0.5, 1.5, 100)
    )
    first = ctx.history
    second = ctx.history
    assert first == second
    # Different tuple objects, so a caller cannot mutate the context's
    # internal list by holding a reference and converting to list later.
    assert first is not second


# ---------------------------------------------------------------------------
# End-to-end tests through BacktestEngine. These confirm the engine wires
# ``ctx.record_candle(candle)`` between ``update_candle`` and ``on_candle``
# so the strategy sees the current bar as the last element.
# ---------------------------------------------------------------------------


def test_engine_history_grows_one_per_bar():
    """``ctx.history`` length equals the number of bars processed so far."""
    rows = [
        _row("20240101 09:30", 1, 2, 0.5, 1.5, 100),
        _row("20240101 09:31", 2, 3, 1.5, 2.5, 200),
        _row("20240101 09:32", 3, 4, 2.5, 3.5, 300),
        _row("20240101 09:33", 4, 5, 3.5, 4.5, 400),
    ]
    strategy = _HistoryRecordingStrategy()
    engine = BacktestEngine(
        [InstrumentSpec(symbol="X", adapter=_mock_adapter(rows))],
        strategy,
        BacktestConfig()
    )
    engine.run()

    assert len(strategy.history_per_bar) == 4
    # After the i-th bar, history should have exactly i+1 entries.
    assert len(strategy.history_per_bar[0]) == 1
    assert len(strategy.history_per_bar[1]) == 2
    assert len(strategy.history_per_bar[2]) == 3
    assert len(strategy.history_per_bar[3]) == 4


def test_engine_history_includes_current_candle_as_last_element():
    """The current bar is always ``ctx.history[-1]`` inside ``on_candle``."""
    rows = [
        _row("20240101 09:30", 1, 2, 0.5, 1.5, 100),
        _row("20240101 09:31", 2, 3, 1.5, 2.5, 200),
        _row("20240101 09:32", 3, 4, 2.5, 3.5, 300),
    ]
    strategy = _HistoryRecordingStrategy()
    engine = BacktestEngine(
        [InstrumentSpec(symbol="X", adapter=_mock_adapter(rows))],
        strategy,
        BacktestConfig()
    )
    engine.run()

    # ``on_candle`` recorded the i-th candle; that same instance must be
    # the last element of the history snapshot at that call.
    for i, candle in enumerate(strategy.candles):
        assert candle is strategy.history_per_bar[i][-1]


def test_engine_history_is_chronological():
    """``ctx.history`` is oldest-first, newest-last, across all bars."""
    rows = [
        _row("20240101 09:30", 1, 2, 0.5, 1.5, 100),
        _row("20240101 09:31", 2, 3, 1.5, 2.5, 200),
        _row("20240101 09:32", 3, 4, 2.5, 3.5, 300),
        _row("20240101 09:33", 4, 5, 3.5, 4.5, 400),
        _row("20240101 09:34", 5, 6, 4.5, 5.5, 500),
    ]
    strategy = _HistoryRecordingStrategy()
    engine = BacktestEngine(
        [InstrumentSpec(symbol="X", adapter=_mock_adapter(rows))],
        strategy,
        BacktestConfig()
    )
    engine.run()

    final = strategy.history_per_bar[-1]
    timestamps = [c.timestamp for c in final]
    assert timestamps == sorted(timestamps)
    # And the last bar is the latest timestamp.
    assert final[-1].timestamp == datetime(2024, 1, 1, 9, 34)


def test_engine_history_warmup_yields_shorter_tuple():
    """During warmup, ``ctx.history`` is shorter than the strategy's requested N.

    Regression for the documented contract: a strategy that wants
    ``ctx.history[-20:]`` must guard with ``if len(ctx.history) < 20``
    because warmup bars yield a shorter tuple — never padded with
    ``None`` sentinels. This test exercises the warmup path itself.
    """
    # Use valid OHLC values: open > 0, high >= max(open, close), low <= min(open, close), low > 0
    rows = [_row(f"20240101 09:{30 + i:02d}", 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 100.0)
            for i in range(3)]

    observed_lengths: list[int] = []

    class _WarmupStrategy(Strategy):
        def on_candle(self, candle: Candle) -> None:
            observed_lengths.append(len(self.ctx.history))

    engine = BacktestEngine(
        [InstrumentSpec(symbol="X", adapter=_mock_adapter(rows))],
        _WarmupStrategy(),
        BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
    )
    engine.run()

    # On the first three (and only) bars, history grows 1 -> 2 -> 3.
    assert observed_lengths == [1, 2, 3]


def test_engine_history_supports_lookback_slicing():
    """The ``ctx.history[-N:]`` idiom returns the last N closed bars + current."""
    # Use valid OHLC values: open > 0, high >= max(open, close), low <= min(open, close), low > 0
    rows = [_row(f"20240101 09:{30 + i:02d}", 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 100.0)
            for i in range(10)]

    captured: list[tuple[Candle, ...]] = []

    class _LookbackStrategy(Strategy):
        LOOKBACK = 4

        def on_candle(self, candle: Candle) -> None:
            window = self.ctx.history[-self.LOOKBACK:]
            captured.append(window)

    engine = BacktestEngine(
        [InstrumentSpec(symbol="X", adapter=_mock_adapter(rows))],
        _LookbackStrategy(),
        BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
    )
    engine.run()

    # 10 bars total. The last call sees the full 10-bar history; slicing
    # the last 4 must give the 4 most recent bars including current.
    final_window = captured[-1]
    assert len(final_window) == 4
    # Newest-last means the last element of the window is the current bar.
    assert final_window[-1].timestamp == datetime(2024, 1, 1, 9, 39)
    # And the 4th-from-last is the start of the window.
    assert final_window[0].timestamp == datetime(2024, 1, 1, 9, 36)

    # On the 5th bar (i=4, the first with a full 4-bar window), the
    # window has exactly 4 elements, oldest-first.
    first_full_window = captured[3]  # bar index 3 (4th bar) has 4 history entries
    assert len(first_full_window) == 4
    assert first_full_window[0].timestamp == datetime(2024, 1, 1, 9, 30)
    assert first_full_window[-1].timestamp == datetime(2024, 1, 1, 9, 33)

    # On the first 3 bars, the window is shorter than LOOKBACK (warmup).
    assert len(captured[0]) == 1
    assert len(captured[1]) == 2
    assert len(captured[2]) == 3


def test_engine_history_preserves_candle_indicators():
    """Each entry in ``ctx.history`` carries the indicators computed for that bar.

    This is what makes the lookback feature compose with the existing
    ``compute_indicators`` pre-pass: a strategy can look back at
    ``ctx.history[-1].indicators["rsi"]`` (or any precomputed value) and
    read it as a plain attribute, not a re-computation.
    """
    rows = [
        _row("20240101 09:30", 1, 2, 0.5, 1.5, 100),
        _row("20240101 09:31", 2, 3, 1.5, 2.5, 200),
        _row("20240101 09:32", 3, 4, 2.5, 3.5, 300),
    ]

    class _TaggedStrategy(Strategy):
        seen_indicators: list[dict] = []

        def __init__(self) -> None:
            super().__init__()
            self.seen: list[dict] = []

        def compute_indicators(self, candles, timeframe=None):
            return [{"tag": f"bar_{i}"} for i in range(len(candles))]

        def on_candle(self, candle: Candle) -> None:
            self.seen.append(dict(candle.indicators))
            # Also confirm the lookback can see prior bars' indicators.
            if len(self.ctx.history) >= 2:
                prior = self.ctx.history[-2]
                self.seen.append(dict(prior.indicators))

    strat = _TaggedStrategy()
    engine = BacktestEngine(
        [InstrumentSpec(symbol="X", adapter=_mock_adapter(rows))],
        strat,
        BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
    )
    engine.run()

    # First bar: only the current candle's indicator seen.
    assert strat.seen[0] == {"tag": "bar_0"}
    # Second bar: current + prior.
    assert strat.seen[1] == {"tag": "bar_1"}
    assert strat.seen[2] == {"tag": "bar_0"}
    # Third bar: current + prior.
    assert strat.seen[3] == {"tag": "bar_2"}
    assert strat.seen[4] == {"tag": "bar_1"}


def test_engine_history_is_per_run_not_shared_across_runs():
    """Each ``BacktestEngine.run()`` starts with a fresh history buffer.

    Regression guard: a new context is constructed per engine
    instance, and ``_history`` must not be class-level or shared across
    consecutive ``engine.run()`` invocations on the same instance.
    """
    rows = [
        _row("20240101 09:30", 1, 2, 0.5, 1.5, 100),
        _row("20240101 09:31", 2, 3, 1.5, 2.5, 200),
    ]
    strategy = _HistoryRecordingStrategy()
    engine = BacktestEngine(
        [InstrumentSpec(symbol="X", adapter=_mock_adapter(rows))],
        strategy,
        BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
    )
    engine.run()
    first_run_final_len = len(strategy.history_per_bar[-1])

    engine.run()
    second_run_final_len = len(strategy.history_per_bar[-1])

    # Both runs see 2 bars at the end (not 4 — the history resets).
    assert first_run_final_len == 2
    assert second_run_final_len == 2
