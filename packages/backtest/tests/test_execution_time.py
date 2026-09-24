"""Tests for execution-time semantics: open-time candle timestamps vs. close-time
``ctx.current_time``.

Covers the core requirement that:

1. ``candle.timestamp`` delivered to strategies is always the candle's
   **open time** — never shifted.
2. ``ctx.current_time`` is the **execution time** (close time = open time
   + timeframe duration) at which the engine processes the bar, advancing
   with each processed candle like a simulated clock.
3. ``ctx.history`` retains candles with open-time timestamps.
4. Orders submitted during ``on_candle`` are timestamped with the
   execution time (close time), not the candle's open time.
5. Multi-timeframe dispatch sees the correct execution time for each
   timeframe's candle.
6. The shared timeframe parser is the single source of truth and handles
   all supported units (M/H/D/W) correctly.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from quantrex_core import Candle, Strategy
from quantrex_core.strategy.timeframe import on_timeframe
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter
from quantrex_backtest import BacktestEngine, InstrumentSpec, BacktestConfig
from quantrex_backtest.core import BacktestStrategyContext
from quantrex_backtest.core.timeframe import parse_timeframe_to_timedelta
from quantrex_core.order import OrderManagementSystem
from quantrex_core.position.manager import PositionManager


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class _ExecutionTimeRecordingStrategy(Strategy):
    """Records candle timestamps and ctx.current_time at every on_candle."""

    def __init__(self) -> None:
        super().__init__()
        self.candle_timestamps: list[datetime] = []
        self.execution_times: list[datetime] = []
        self.history_last_timestamps: list[datetime] = []

    def on_candle(self, candle: Candle) -> None:
        self.candle_timestamps.append(candle.timestamp)
        self.execution_times.append(self.ctx.current_time)
        self.history_last_timestamps.append(self.ctx.history[-1].timestamp)


class _TimeframeTimeRecordingStrategy(Strategy):
    """Records execution time inside @on_timeframe-decorated methods."""

    def __init__(self) -> None:
        super().__init__()
        self.tf_candle_timestamps: list[datetime] = []
        self.tf_execution_times: list[datetime] = []

    def on_candle(self, candle: Candle) -> None:
        pass  # Base timeframe only; all logic lives in the 5M handler.

    @on_timeframe("5M")
    def on_5m(self, candle: Candle) -> None:
        self.tf_candle_timestamps.append(candle.timestamp)
        self.tf_execution_times.append(self.ctx.current_time)


class _OrderTimeRecordingStrategy(Strategy):
    """Submits an order on the first candle and records its timestamp."""

    def __init__(self) -> None:
        super().__init__()
        self.order_timestamps: list[datetime] = []
        self.submitted = False

    def on_candle(self, candle: Candle) -> None:
        if not self.submitted:
            order = self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.BUY,
                quantity=1.0,
            )
            self.order_timestamps.append(order.timestamp)
            self.submitted = True


def _mock_adapter(rows: list[dict]) -> Mock:
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.side_effect = lambda tf, from_date=None, to_date=None: rows
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


def _make_rows(count: int, start: str = "20260101 09:15") -> list[dict]:
    """Build ``count`` consecutive 1-minute rows starting at ``start``."""
    fmt = "%Y%m%d %H:%M"
    t0 = datetime.strptime(start, fmt)
    return [
        _row(
            (t0 + timedelta(minutes=i)).strftime(fmt),
            100.0 + i,
            101.0 + i,
            99.0 + i,
            100.5 + i,
            1000.0,
        )
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Open-time vs. execution-time separation
# ---------------------------------------------------------------------------


class TestOpenTimeVsExecutionTime:
    def test_candle_timestamp_is_open_time(self):
        """on_candle receives candles with their original open-time timestamps."""
        rows = _make_rows(3)
        strategy = _ExecutionTimeRecordingStrategy()
        engine = BacktestEngine(
            [InstrumentSpec(symbol="TEST", adapter=_mock_adapter(rows))],
            strategy,
            BacktestConfig()
        )
        engine.run()

        assert strategy.candle_timestamps == [
            datetime(2026, 1, 1, 9, 15),
            datetime(2026, 1, 1, 9, 16),
            datetime(2026, 1, 1, 9, 17),
        ]

    def test_current_time_is_close_time(self):
        """ctx.current_time equals open time + base timeframe duration."""
        rows = _make_rows(3)
        strategy = _ExecutionTimeRecordingStrategy()
        engine = BacktestEngine(
            [InstrumentSpec(symbol="TEST", adapter=_mock_adapter(rows))],
            strategy,
            BacktestConfig()
        )
        engine.run()

        assert strategy.execution_times == [
            datetime(2026, 1, 1, 9, 16),  # 09:15 + 1M
            datetime(2026, 1, 1, 9, 17),  # 09:16 + 1M
            datetime(2026, 1, 1, 9, 18),  # 09:17 + 1M
        ]

    def test_current_time_advances_with_each_candle(self):
        """Execution time advances monotonically like a simulated clock."""
        rows = _make_rows(5)
        strategy = _ExecutionTimeRecordingStrategy()
        engine = BacktestEngine(
            [InstrumentSpec(symbol="TEST", adapter=_mock_adapter(rows))],
            strategy,
            BacktestConfig()
        )
        engine.run()

        times = strategy.execution_times
        assert times == sorted(times)
        assert len(set(times)) == len(times)  # strictly advancing

    def test_history_keeps_open_time_timestamps(self):
        """ctx.history candles retain open-time timestamps (never shifted)."""
        rows = _make_rows(3)
        strategy = _ExecutionTimeRecordingStrategy()
        engine = BacktestEngine(
            [InstrumentSpec(symbol="TEST", adapter=_mock_adapter(rows))],
            strategy,
            BacktestConfig()
        )
        engine.run()

        assert strategy.history_last_timestamps == strategy.candle_timestamps

    def test_current_time_before_first_bar_is_datetime_min(self):
        """Before any bar is processed, current_time is datetime.min."""
        ctx = BacktestStrategyContext(
            PositionManager(), OrderManagementSystem(), datetime.min
        )
        assert ctx.current_time == datetime.min


# ---------------------------------------------------------------------------
# Order timing uses execution time
# ---------------------------------------------------------------------------


class TestOrderTiming:
    def test_order_timestamped_with_execution_time(self):
        """Orders submitted during on_candle carry the close-time timestamp."""
        rows = _make_rows(2)
        strategy = _OrderTimeRecordingStrategy()
        engine = BacktestEngine(
            [InstrumentSpec(symbol="TEST", adapter=_mock_adapter(rows))],
            strategy,
            BacktestConfig()
        )
        engine.run()

        # Order submitted while processing the 09:15 candle (open time)
        # must be timestamped at its close time 09:16.
        assert strategy.order_timestamps == [datetime(2026, 1, 1, 9, 16)]


# ---------------------------------------------------------------------------
# Multi-timeframe execution time
# ---------------------------------------------------------------------------


class TestMultiTimeframeExecutionTime:
    def test_timeframe_dispatch_sees_correct_execution_time(self):
        """@on_timeframe methods see the execution time of the base bar
        during which their timeframe candle completed."""
        # 10 one-minute rows starting 09:15 -> two complete 5M candles
        # (09:15-09:20 and 09:20-09:25).
        rows_1m = _make_rows(10)
        t0 = datetime(2026, 1, 1, 9, 15)
        fmt = "%Y%m%d %H:%M"
        rows_5m = [
            _row((t0 + timedelta(minutes=5 * i)).strftime(fmt), 100.0, 101.0, 99.0, 100.5, 1000.0)
            for i in range(3)
        ]
        adapter = _mock_adapter(rows_1m)
        adapter.read_timeframe.side_effect = lambda tf, from_date=None, to_date=None: rows_5m if tf == "5M" else rows_1m
        adapter.supported_timeframes = ["1M", "5M"]
        strategy = _TimeframeTimeRecordingStrategy()
        engine = BacktestEngine(
            [InstrumentSpec(symbol="TEST", adapter=adapter)],
            strategy,
            BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
        )
        engine.run()

        # 5M candle (09:15-09:20) has close_time = 09:20
        # Should be dispatched when processing the 1M candle at 09:19 (execution_time = 09:20)
        assert strategy.tf_candle_timestamps[0] == datetime(2026, 1, 1, 9, 15)
        assert strategy.tf_execution_times[0] == datetime(2026, 1, 1, 9, 20)

        # Second 5M candle (09:20-09:25) has close_time = 09:25
        # Should be dispatched when processing the 1M candle at 09:24 (execution_time = 09:25)
        assert strategy.tf_candle_timestamps[1] == datetime(2026, 1, 1, 9, 20)
        assert strategy.tf_execution_times[1] == datetime(2026, 1, 1, 9, 25)


# ---------------------------------------------------------------------------
# Shared timeframe parser (single source of truth)
# ---------------------------------------------------------------------------


class TestTimeframeParser:
    @pytest.mark.parametrize(
        ("timeframe", "expected"),
        [
            ("1M", timedelta(minutes=1)),
            ("5M", timedelta(minutes=5)),
            ("15M", timedelta(minutes=15)),
            ("30M", timedelta(minutes=30)),
            ("1H", timedelta(hours=1)),
            ("4H", timedelta(hours=4)),
            ("1D", timedelta(days=1)),
            ("1W", timedelta(weeks=1)),
            ("1m", timedelta(minutes=1)),  # case-insensitive
        ],
    )
    def test_parse_timeframe_to_timedelta(self, timeframe, expected):
        assert parse_timeframe_to_timedelta(timeframe) == expected

    @pytest.mark.parametrize("bad", ["", "X", "1X", "M", "1.5H", "-5M"])
    def test_parse_invalid_timeframe_returns_none(self, bad):
        assert parse_timeframe_to_timedelta(bad) is None

    
