"""Tests for Strategy base class."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from quantrex.core.models.market_data import OHLCVCandle, Tick
from quantrex.core.models.orders import Order, OrderSide, OrderType
from quantrex.core.models.signals import Signal, SignalType
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit
from quantrex.core.models.trades import Trade

from quantrex.kernel.strategy.base import Strategy


class ConcreteStrategy(Strategy):
    """A concrete strategy subclass."""

    def on_bar(self, candle: OHLCVCandle) -> Signal | None:
        return Signal(
            symbol=candle.symbol,
            signal_type=SignalType.ENTRY_LONG,
            price=candle.close,
            quantity=Decimal("1"),
        )


def _make_candle() -> OHLCVCandle:
    return OHLCVCandle(
        symbol="RELIANCE",
        timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("99"),
        close=Decimal("104"),
        volume=Decimal("1000"),
        timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
    )


class TestStrategyBase:
    """Tests for the Strategy base class."""

    def test_on_bar_is_required(self) -> None:
        strategy = Strategy()
        with pytest.raises(NotImplementedError, match="subclasses must implement on_bar"):
            strategy.on_bar(_make_candle())

    def test_concrete_strategy_implements_on_bar(self) -> None:
        strategy = ConcreteStrategy()
        candle = _make_candle()
        signal = strategy.on_bar(candle)
        assert signal is not None
        assert signal.symbol == "RELIANCE"
        assert signal.signal_type == SignalType.ENTRY_LONG

    def test_optional_hooks_are_noops(self) -> None:
        strategy = ConcreteStrategy()
        # Should not raise
        strategy.on_start()
        strategy.on_stop()
        strategy.on_tick(Tick(symbol="RELIANCE", price=Decimal("100"), timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=UTC)))
        strategy.on_order(Order(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("1"),
        ))
        strategy.on_fill(Trade(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            exit_price=Decimal("101"),
            entry_time=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            exit_time=datetime(2024, 1, 1, 10, 1, tzinfo=UTC),
            pnl=Decimal("1"),
        ))
