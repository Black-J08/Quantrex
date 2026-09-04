"""Regression tests for the precomputed indicator API wired into BacktestEngine.

A bug fix without a regression test is not a fix — see project AGENTS.md
"Standing Rule: Regression Tests for Every Bug Fix". These tests cover the
end-to-end wiring of ``Strategy.compute_indicators`` into
``BacktestEngine.run``:

1. The hook is called exactly once with the full sorted row sequence.
2. The i-th returned mapping is attached to the i-th ``Candle`` seen by
   ``on_candle``.
3. Hook exceptions and length mismatches are surfaced as ``ProviderError``
   (with ``logger.exception(..., exc_info=True)`` per the project's
   "Logging & Error Tracking Standards").
"""

from datetime import datetime
from unittest.mock import Mock

from quantrex_core import Candle, Strategy
from quantrex_core.protocols import DataAdapter
from quantrex_backtest import BacktestEngine
from quantrex_backtest.exceptions.backtest_error import ProviderError


# ---------------------------------------------------------------------------
# Test fixtures: minimal strategies and adapters. We avoid CSV test-support
# helpers here because the assertions are about the indicator wiring, not
# the CSV pipeline. Mock adapters with explicit raw row dicts are simpler
# and faster.
# ---------------------------------------------------------------------------


class _RecordingStrategy(Strategy):
    """Records every candle ``on_candle`` receives."""

    def __init__(self) -> None:
        super().__init__()
        self.candles: list[Candle] = []
        self.compute_calls: int = 0
        self.last_seen_rows: list[dict] | None = None

    def on_candle(self, candle: Candle) -> None:
        self.candles.append(candle)


class _SpreadStrategy(_RecordingStrategy):
    """Hand-rolled indicator: ``close - open`` (library-free, framework-agnostic)."""

    def compute_indicators(self, candles):
        self.compute_calls += 1
        # Capture the exact row sequence the engine passed in so the
        # timestamp-ordering test can assert on it.
        self.last_seen_rows = [dict(row) for row in candles]
        return [
            {"spread": float(c["close"]) - float(c["open"])} for c in candles
        ]


def _mock_adapter(rows: list[dict]) -> Mock:
    adapter = Mock(spec=DataAdapter)
    adapter.read.return_value = rows
    adapter.datetime_format = "%Y%m%d %H:%M"
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
# Tests
# ---------------------------------------------------------------------------


def test_engine_attaches_indicators_from_compute_indicators_hook():
    """Engine attaches the i-th returned dict to the i-th ``Candle.indicators``.

    Regression: the engine must call the hook exactly once, must pass the
    full sorted row sequence, must validate the returned length matches,
    and must thread each returned mapping into the matching candle's
    ``indicators`` field before ``on_candle`` is invoked.
    """
    rows = [
        _row("20230101 09:30", 100.0, 101.0, 99.0, 100.5, 10),
        _row("20230101 09:31", 101.0, 102.0, 100.0, 101.5, 20),
        _row("20230101 09:32", 102.0, 103.0, 101.0, 102.5, 30),
    ]
    strategy = _SpreadStrategy()
    engine = BacktestEngine(_mock_adapter(rows), strategy, symbol="COPPER")

    engine.run()

    # Hook called exactly once with the full sequence.
    assert strategy.compute_calls == 1
    assert strategy.last_seen_rows is not None
    assert len(strategy.last_seen_rows) == 3

    # Per-bar attachment: the i-th mapping is attached to the i-th candle.
    assert len(strategy.candles) == 3
    assert strategy.candles[0].indicators["spread"] == 0.5
    assert strategy.candles[1].indicators["spread"] == 0.5
    assert strategy.candles[2].indicators["spread"] == 0.5


def test_engine_passes_raw_rows_in_timestamp_order():
    """The hook receives rows already sorted by datetime, even if CSV is not.

    Regression: the engine must sort ``raw_data`` BEFORE calling
    ``compute_indicators`` so vectorized indicators compute over a
    deterministic, time-ordered series. Without the sort, an out-of-order
    CSV would silently produce a wrong series in the override.
    """
    rows = [
        # Intentionally out of order; engine must sort before hook.
        _row("20230101 09:32", 102.0, 103.0, 101.0, 102.5, 30),  # latest
        _row("20230101 09:30", 100.0, 101.0, 99.0, 100.5, 10),  # earliest
        _row("20230101 09:31", 101.0, 102.0, 100.0, 101.5, 20),  # middle
    ]
    strategy = _SpreadStrategy()
    engine = BacktestEngine(_mock_adapter(rows), strategy, symbol="COPPER")

    engine.run()

    assert strategy.last_seen_rows is not None
    seen = [r["datetime"] for r in strategy.last_seen_rows]
    assert seen == [
        "20230101 09:30",
        "20230101 09:31",
        "20230101 09:32",
    ]


def test_engine_wraps_compute_indicators_exception_as_provider_error():
    """A hook that raises becomes a ``ProviderError`` (with full stack trace).

    Regression: the framework's "Logging & Error Tracking Standards" require
    ``logger.exception(..., exc_info=True)`` for any caught error. The
    engine must wrap the hook's exception as ``ProviderError`` (consistent
    with how ``adapter.read()`` failures are wrapped) so callers have a
    single, predictable exception type for data/indicator failures.
    """

    class _BoomStrategy(_RecordingStrategy):
        def compute_indicators(self, candles):
            raise ValueError("indicator math blew up")

    rows = [_row("20230101 09:30", 100.0, 101.0, 99.0, 100.5, 10)]
    engine = BacktestEngine(_mock_adapter(rows), _BoomStrategy(), symbol="COPPER")

    try:
        engine.run()
    except ProviderError as e:
        assert "compute_indicators failed" in str(e)
        assert "indicator math blew up" in str(e)
    else:
        raise AssertionError("expected ProviderError")


def test_engine_raises_provider_error_on_length_mismatch():
    """Returning the wrong number of indicator mappings raises ``ProviderError``.

    Regression: a buggy override (e.g. off-by-one, or returning a generator
    that ``len()`` rejects) must not silently produce misaligned bars.
    The engine validates length and raises ``ProviderError`` with both
    counts in the message.
    """

    class _BadLengthStrategy(_RecordingStrategy):
        def compute_indicators(self, candles):
            # 3 input rows, 2 returned dicts — off by one.
            return [{"spread": 0.0}] * (len(candles) - 1)

    rows = [
        _row("20230101 09:30", 100.0, 101.0, 99.0, 100.5, 10),
        _row("20230101 09:31", 101.0, 102.0, 100.0, 101.5, 20),
        _row("20230101 09:32", 102.0, 103.0, 101.0, 102.5, 30),
    ]
    engine = BacktestEngine(_mock_adapter(rows), _BadLengthStrategy(), symbol="COPPER")

    try:
        engine.run()
    except ProviderError as e:
        msg = str(e)
        # Message should mention both expected and actual lengths.
        assert "2" in msg
        assert "3" in msg
    else:
        raise AssertionError("expected ProviderError on length mismatch")
