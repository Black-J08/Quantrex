"""Tests for BacktestEngine."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.orders import OrderSide
from quantrex.core.models.signals import Signal, SignalType
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit
from quantrex.core.models.trades import Trade
from quantrex.engine.backtest_engine.engine import BacktestEngine


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


class TestBacktestEngine:
    """Tests for BacktestEngine."""

    def test_on_signal_creates_filled_order(self) -> None:
        engine = BacktestEngine()
        signal = _make_signal()
        engine.on_signal(signal)

        fills = engine.get_pending_fills()
        assert len(fills) == 1
        assert fills[0].symbol == "RELIANCE"
        assert fills[0].side == OrderSide.BUY

    def test_on_signal_exit_long_maps_to_sell(self) -> None:
        engine = BacktestEngine()
        signal = Signal(
            symbol="RELIANCE",
            signal_type=SignalType.EXIT_LONG,
            price=Decimal(105),
            quantity=Decimal(1),
        )
        engine.on_signal(signal)

        fills = engine.get_pending_fills()
        assert len(fills) == 1
        assert fills[0].side == OrderSide.SELL

    def test_get_pending_fills_returns_and_clears(self) -> None:
        engine = BacktestEngine()
        trade = Trade(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal(1),
            entry_price=Decimal(100),
            exit_price=Decimal(101),
            entry_time=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            exit_time=datetime(2024, 1, 1, 10, 1, tzinfo=UTC),
            pnl=Decimal(1),
        )
        engine.add_fill(trade)

        fills = engine.get_pending_fills()
        assert len(fills) == 1
        assert fills[0] is trade

        # Second call should be empty
        assert engine.get_pending_fills() == []

    def test_inherits_base_engine(self) -> None:
        from quantrex.engine.base import BaseEngine

        engine = BacktestEngine()
        assert isinstance(engine, BaseEngine)

    def test_create_kernel_wires_signal_callback(self) -> None:
        engine = BacktestEngine()
        kernel = engine.create_kernel(object())
        assert kernel is not None
        assert callable(kernel.on_signal)

    def test_data_iterator_returns_candles(self) -> None:
        engine = BacktestEngine()
        engine.set_candles([_make_candle()])
        candles = list(engine.data_iterator())
        assert len(candles) == 1
        assert candles[0].symbol == "RELIANCE"
