"""Tests for Kernel event loop."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.signals import Signal, SignalType
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit
from quantrex.kernel.kernel import Kernel


class RecordingStrategy:
    """Strategy that records all hook calls."""

    def __init__(self) -> None:
        self.on_start_called = False
        self.on_stop_called = False
        self.bars_seen: list[OHLCVCandle] = []
        self.signals: list[Signal] = []

    def on_bar(self, candle: OHLCVCandle) -> Signal | None:
        self.bars_seen.append(candle)
        if candle.close > Decimal(100):
            return Signal(
                symbol=candle.symbol,
                signal_type=SignalType.ENTRY_LONG,
                price=candle.close,
                quantity=Decimal(1),
            )
        return None

    def on_start(self) -> None:
        self.on_start_called = True

    def on_stop(self) -> None:
        self.on_stop_called = True


def _make_candle(close: Decimal, ts: datetime, high: Decimal | None = None) -> OHLCVCandle:
    return OHLCVCandle(
        symbol="RELIANCE",
        timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        open=Decimal(99),
        high=high if high is not None else close + Decimal(1),
        low=Decimal(98),
        close=close,
        volume=Decimal(1000),
        timestamp=ts,
    )


class TestKernel:
    """Tests for Kernel event loop."""

    def test_runs_on_start_on_bar_on_stop(self) -> None:
        strategy = RecordingStrategy()
        emitted: list[Signal] = []
        kernel = Kernel(strategy, on_signal=emitted.append)

        candles = iter([
            _make_candle(Decimal(99), datetime(2024, 1, 1, 10, 0, tzinfo=UTC)),
            _make_candle(Decimal(101), datetime(2024, 1, 1, 10, 1, tzinfo=UTC)),
        ])

        kernel.run(candles)

        assert strategy.on_start_called
        assert strategy.on_stop_called
        assert len(strategy.bars_seen) == 2
        assert len(emitted) == 1  # only the candle with close > 100 emits a signal

    def test_emits_signals_via_callback(self) -> None:
        strategy = RecordingStrategy()
        emitted: list[Signal] = []
        kernel = Kernel(strategy, on_signal=emitted.append)

        candles = iter([
            _make_candle(Decimal(101), datetime(2024, 1, 1, 10, 0, tzinfo=UTC)),
        ])

        kernel.run(candles)

        assert len(emitted) == 1
        assert emitted[0].symbol == "RELIANCE"
        assert emitted[0].signal_type == SignalType.ENTRY_LONG

    def test_ctx_current_time_advances_per_bar(self) -> None:
        strategy = RecordingStrategy()
        emitted: list[Signal] = []
        kernel = Kernel(strategy, on_signal=emitted.append)

        ts1 = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        ts2 = datetime(2024, 1, 1, 10, 1, tzinfo=UTC)
        candles = iter([
            _make_candle(Decimal(101), ts1),
            _make_candle(Decimal(102), ts2, high=Decimal(103)),
        ])

        kernel.run(candles)

        assert strategy.bars_seen[0].timestamp == ts1
        assert strategy.bars_seen[1].timestamp == ts2

    def test_no_signal_when_close_not_above_100(self) -> None:
        strategy = RecordingStrategy()
        emitted: list[Signal] = []
        kernel = Kernel(strategy, on_signal=emitted.append)

        candles = iter([
            _make_candle(Decimal(99), datetime(2024, 1, 1, 10, 0, tzinfo=UTC)),
        ])

        kernel.run(candles)

        assert len(emitted) == 0

    def test_kernel_has_no_engine_dependency(self) -> None:
        """Kernel constructor takes only strategy and callback — no engine."""
        strategy = RecordingStrategy()
        emitted: list[Signal] = []
        kernel = Kernel(strategy, on_signal=emitted.append)
        assert kernel.strategy is strategy
        assert callable(kernel.on_signal)
        assert not hasattr(kernel, "engine")

    def test_kernel_does_not_call_strategy_on_order_or_on_fill(self) -> None:
        """Kernel never calls strategy.on_order or strategy.on_fill."""
        calls: list[str] = []

        class TrackingStrategy:
            def on_bar(self, candle: OHLCVCandle) -> Signal | None:
                return None

            def on_start(self) -> None:
                calls.append("on_start")

            def on_stop(self) -> None:
                calls.append("on_stop")

            def on_order(self, order: object) -> None:
                calls.append("on_order")

            def on_fill(self, trade: object) -> None:
                calls.append("on_fill")

        strategy = TrackingStrategy()
        emitted: list[Signal] = []
        kernel = Kernel(strategy, on_signal=emitted.append)

        candles = iter([
            _make_candle(Decimal(101), datetime(2024, 1, 1, 10, 0, tzinfo=UTC)),
        ])

        kernel.run(candles)

        assert "on_order" not in calls
        assert "on_fill" not in calls
