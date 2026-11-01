"""Tests for kernel protocols."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.signals import Signal, SignalType
from quantrex.kernel.protocols import (
    ClockProtocol,
    ContextProtocol,
    StrategyProtocol,
)


class ConcreteStrategy:
    """A concrete strategy implementing StrategyProtocol."""

    def on_bar(self, candle: OHLCVCandle) -> Signal | None:
        return Signal(
            symbol=candle.symbol,
            signal_type=SignalType.ENTRY_LONG,
            price=candle.close,
            quantity=Decimal(1),
        )

    def on_start(self) -> None:
        pass

    def on_stop(self) -> None:
        pass


class ConcreteContext:
    """A concrete context implementing ContextProtocol."""

    def __init__(self) -> None:
        self._current_time = datetime.now(UTC)
        self._history: tuple[OHLCVCandle, ...] = ()

    @property
    def current_time(self) -> datetime:
        return self._current_time

    @property
    def history(self) -> tuple[OHLCVCandle, ...]:
        return self._history


class ConcreteClock:
    """A concrete clock implementing ClockProtocol."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def advance(self, target: datetime) -> None:
        pass


class TestStrategyProtocol:
    """Tests for StrategyProtocol runtime_checkable conformance."""

    def test_concrete_strategy_implements_protocol(self) -> None:
        strategy = ConcreteStrategy()
        assert isinstance(strategy, StrategyProtocol)

    def test_on_bar_is_required(self) -> None:
        # A class missing on_bar should not be considered a StrategyProtocol
        class Incomplete:
            def on_start(self) -> None:
                pass

        assert not isinstance(Incomplete(), StrategyProtocol)


class TestContextProtocol:
    """Tests for ContextProtocol runtime_checkable conformance."""

    def test_concrete_context_implements_protocol(self) -> None:
        ctx = ConcreteContext()
        assert isinstance(ctx, ContextProtocol)


class TestClockProtocol:
    """Tests for ClockProtocol runtime_checkable conformance."""

    def test_concrete_clock_implements_protocol(self) -> None:
        clock = ConcreteClock()
        assert isinstance(clock, ClockProtocol)
