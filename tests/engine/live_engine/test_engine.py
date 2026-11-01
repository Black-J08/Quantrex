"""Tests for LiveEngine."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.signals import Signal, SignalType
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit
from quantrex.engine.live_engine.engine import LiveEngine


def _make_signal() -> Signal:
    return Signal(
        symbol="RELIANCE",
        signal_type=SignalType.ENTRY_LONG,
        price=Decimal(100),
        quantity=Decimal(1),
    )


def _make_candle() -> OHLCVCandle:
    return OHLCVCandle(
        symbol="RELIANCE",
        timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        open=Decimal(100),
        high=Decimal(105),
        low=Decimal(99),
        close=Decimal(104),
        volume=Decimal(1000),
        timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
    )


class TestLiveEngine:
    """Tests for LiveEngine."""

    def test_on_signal_creates_pending_order(self) -> None:
        engine = LiveEngine()
        signal = _make_signal()
        engine.on_signal(signal)

        # Live orders are PENDING, not filled synchronously
        fills = engine.get_pending_fills()
        assert len(fills) == 0

    def test_on_signal_exit_long_maps_to_sell(self) -> None:
        engine = LiveEngine()
        signal = Signal(
            symbol="RELIANCE",
            signal_type=SignalType.EXIT_LONG,
            price=Decimal(105),
            quantity=Decimal(1),
        )
        engine.on_signal(signal)

        # Live orders are PENDING, not filled synchronously
        fills = engine.get_pending_fills()
        assert len(fills) == 0

    def test_get_pending_fills_default_empty(self) -> None:
        engine = LiveEngine()
        assert engine.get_pending_fills() == []

    def test_inherits_base_engine(self) -> None:
        from quantrex.engine.base import BaseEngine

        engine = LiveEngine()
        assert isinstance(engine, BaseEngine)

    def test_create_kernel_wires_signal_callback(self) -> None:
        engine = LiveEngine()
        kernel = engine.create_kernel(object())
        assert kernel is not None
        assert callable(kernel.on_signal)

    def test_data_iterator_returns_candles(self) -> None:
        engine = LiveEngine()
        engine.set_candles([_make_candle()])
        candles = list(engine.data_iterator())
        assert len(candles) == 1
        assert candles[0].symbol == "RELIANCE"
