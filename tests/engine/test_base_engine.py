"""Tests for BaseEngine."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.signals import Signal, SignalType
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit
from quantrex.engine.base import BaseEngine
from quantrex.kernel.kernel import Kernel


class ConcreteEngine(BaseEngine):
    """A concrete engine for testing."""

    def __init__(self) -> None:
        super().__init__()
        self.received_signals: list[Signal] = []
        self._candles: list[OHLCVCandle] = []

    def create_kernel(self, strategy) -> Kernel:
        return Kernel(strategy, on_signal=self.on_signal)

    def data_iterator(self):
        return iter(self._candles)

    def set_candles(self, candles: list[OHLCVCandle]) -> None:
        self._candles = list(candles)

    def on_signal(self, signal: Signal) -> None:
        self.received_signals.append(signal)


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


class TestBaseEngine:
    """Tests for BaseEngine."""

    def test_base_engine_is_abstract(self) -> None:
        """BaseEngine cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseEngine()  # type: ignore[abstract]

    def test_concrete_engine_implements_interface(self) -> None:
        engine = ConcreteEngine()
        signal = Signal(
            symbol="RELIANCE",
            signal_type=SignalType.ENTRY_LONG,
            price=Decimal(100),
            quantity=Decimal(1),
        )
        engine.on_signal(signal)
        assert len(engine.received_signals) == 1
        assert engine.received_signals[0].symbol == "RELIANCE"

    def test_kernel_property_raises_before_create(self) -> None:
        engine = ConcreteEngine()
        with pytest.raises(RuntimeError, match="kernel has not been created yet"):
            _ = engine.kernel

    def test_start_creates_and_runs_kernel(self) -> None:
        engine = ConcreteEngine()
        engine.set_candles([_make_candle()])

        class SimpleStrategy:
            def on_bar(self, candle):
                return None

            def on_start(self):
                pass

            def on_stop(self):
                pass

        engine.start(SimpleStrategy())
        assert engine._kernel is not None
        assert isinstance(engine._kernel, Kernel)

    def test_get_pending_fills_default_empty(self) -> None:
        engine = ConcreteEngine()
        assert engine.get_pending_fills() == []
