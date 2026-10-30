"""Tests for Kernel event loop."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.orders import Order, OrderSide, OrderStatus, OrderType
from quantrex.core.models.signals import Signal, SignalType
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit
from quantrex.core.models.trades import Trade

from quantrex.kernel.kernel import Kernel
from quantrex.kernel.protocols import EngineProtocol, StrategyProtocol


class RecordingStrategy:
    """Strategy that records all hook calls."""

    def __init__(self) -> None:
        self.on_start_called = False
        self.on_stop_called = False
        self.bars_seen: list[OHLCVCandle] = []
        self.signals: list[Signal] = []
        self.orders_seen: list[Order] = []
        self.fills_seen: list[Trade] = []

    def on_bar(self, candle: OHLCVCandle) -> Signal | None:
        self.bars_seen.append(candle)
        if candle.close > Decimal("100"):
            return Signal(
                symbol=candle.symbol,
                signal_type=SignalType.ENTRY_LONG,
                price=candle.close,
                quantity=Decimal("1"),
            )
        return None

    def on_start(self) -> None:
        self.on_start_called = True

    def on_stop(self) -> None:
        self.on_stop_called = True

    def on_order(self, order: Order) -> None:
        self.orders_seen.append(order)

    def on_fill(self, trade: Trade) -> None:
        self.fills_seen.append(trade)


class RecordingEngine:
    """Engine that records execute_signal calls and returns canned orders/fills."""

    def __init__(self) -> None:
        self.on_start_called = False
        self.on_stop_called = False
        self.executed_signals: list[Signal] = []
        self.submitted_orders: list[Order] = []
        self.pending_fills: list[Trade] = []

    def execute_signal(self, signal: Signal) -> Order:
        self.executed_signals.append(signal)
        order = Order(
            symbol=signal.symbol,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=signal.quantity or Decimal("1"),
            status=OrderStatus.FILLED,
        )
        self.submitted_orders.append(order)
        return order

    def get_pending_fills(self) -> list[Trade]:
        fills = list(self.pending_fills)
        self.pending_fills.clear()
        return fills

    def submit_order(self, order: Order) -> Order:
        return order

    def get_position(self, symbol: str):
        return None

    def on_start(self) -> None:
        self.on_start_called = True

    def on_stop(self) -> None:
        self.on_stop_called = True


def _make_candle(close: Decimal, ts: datetime, high: Decimal | None = None) -> OHLCVCandle:
    return OHLCVCandle(
        symbol="RELIANCE",
        timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        open=Decimal("99"),
        high=high if high is not None else close + Decimal("1"),
        low=Decimal("98"),
        close=close,
        volume=Decimal("1000"),
        timestamp=ts,
    )


class TestKernel:
    """Tests for Kernel event loop."""

    def test_runs_on_start_on_bar_on_stop(self) -> None:
        strategy = RecordingStrategy()
        engine = RecordingEngine()
        kernel = Kernel(strategy, engine)

        candles = [
            _make_candle(Decimal("99"), datetime(2024, 1, 1, 10, 0, tzinfo=UTC)),
            _make_candle(Decimal("101"), datetime(2024, 1, 1, 10, 1, tzinfo=UTC)),
        ]

        kernel.run(candles)

        assert strategy.on_start_called
        assert strategy.on_stop_called
        assert engine.on_start_called
        assert engine.on_stop_called
        assert len(strategy.bars_seen) == 2

    def test_delegates_signal_to_order_via_engine(self) -> None:
        strategy = RecordingStrategy()
        engine = RecordingEngine()
        kernel = Kernel(strategy, engine)

        candles = [
            _make_candle(Decimal("101"), datetime(2024, 1, 1, 10, 0, tzinfo=UTC)),
        ]

        kernel.run(candles)

        assert len(engine.executed_signals) == 1
        assert len(engine.submitted_orders) == 1
        assert len(strategy.orders_seen) == 1

    def test_ctx_current_time_advances_per_bar(self) -> None:
        strategy = RecordingStrategy()
        engine = RecordingEngine()
        kernel = Kernel(strategy, engine)

        ts1 = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        ts2 = datetime(2024, 1, 1, 10, 1, tzinfo=UTC)
        candles = [
            _make_candle(Decimal("101"), ts1),
            _make_candle(Decimal("102"), ts2, high=Decimal("103")),
        ]

        kernel = Kernel(strategy, engine)
        kernel.run(candles)

        assert strategy.bars_seen[0].timestamp == ts1
        assert strategy.bars_seen[1].timestamp == ts2

    def test_on_fill_called_for_pending_fills(self) -> None:
        strategy = RecordingStrategy()
        engine = RecordingEngine()
        trade = Trade(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            exit_price=Decimal("101"),
            entry_time=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            exit_time=datetime(2024, 1, 1, 10, 1, tzinfo=UTC),
            pnl=Decimal("1"),
        )
        engine.pending_fills = [trade]

        kernel = Kernel(strategy, engine)
        candles = [
            _make_candle(Decimal("101"), datetime(2024, 1, 1, 10, 0, tzinfo=UTC)),
        ]

        kernel.run(candles)

        assert len(strategy.fills_seen) == 1
        assert strategy.fills_seen[0] is trade

    def test_no_signal_when_close_not_above_100(self) -> None:
        strategy = RecordingStrategy()
        engine = RecordingEngine()
        kernel = Kernel(strategy, engine)

        candles = [
            _make_candle(Decimal("99"), datetime(2024, 1, 1, 10, 0, tzinfo=UTC)),
        ]

        kernel.run(candles)

        assert len(engine.executed_signals) == 0
        assert len(engine.submitted_orders) == 0
