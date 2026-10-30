"""Tests for kernel protocols."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from quantrex.core.models.market_data import OHLCVCandle, Tick
from quantrex.core.models.orders import Order, OrderSide, OrderStatus, OrderType
from quantrex.core.models.positions import Position, PositionSide
from quantrex.core.models.signals import Signal, SignalType
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit
from quantrex.core.models.trades import Trade

from quantrex.kernel.protocols import (
    ClockProtocol,
    ContextProtocol,
    DataFeedProtocol,
    EngineProtocol,
    ExecutionProtocol,
    StrategyProtocol,
)


class ConcreteStrategy:
    """A concrete strategy implementing StrategyProtocol."""

    def on_bar(self, candle: OHLCVCandle) -> Signal | None:
        return Signal(
            symbol=candle.symbol,
            signal_type=SignalType.ENTRY_LONG,
            price=candle.close,
            quantity=Decimal("1"),
        )

    def on_start(self) -> None:
        pass

    def on_stop(self) -> None:
        pass

    def on_tick(self, tick: Tick) -> None:
        pass

    def on_order(self, order: Order) -> None:
        pass

    def on_fill(self, trade: Trade) -> None:
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

    def submit_order(self, order: Order) -> Order:
        return order

    def get_position(self, symbol: str) -> Position | None:
        return None


class ConcreteDataFeed:
    """A concrete data feed implementing DataFeedProtocol."""

    @property
    def islive(self) -> bool:
        return False

    def subscribe(self, symbol: str) -> None:
        pass

    def get_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: Timeframe,
    ) -> list[OHLCVCandle]:
        return []


class ConcreteExecution:
    """A concrete execution implementing ExecutionProtocol."""

    def submit_order(self, order: Order) -> Order:
        return order

    def cancel_order(self, order_id: UUID) -> None:
        pass

    def get_position(self, symbol: str) -> Position | None:
        return None

    def get_account(self) -> dict[str, object]:
        return {}


class ConcreteClock:
    """A concrete clock implementing ClockProtocol."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def advance(self, target: datetime) -> None:
        pass


class ConcreteEngine:
    """A concrete engine implementing EngineProtocol."""

    def execute_signal(self, signal: Signal) -> Order:
        return Order(
            symbol=signal.symbol,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=signal.quantity or Decimal("1"),
        )

    def get_pending_fills(self) -> list[Trade]:
        return []

    def submit_order(self, order: Order) -> Order:
        return order

    def get_position(self, symbol: str) -> Position | None:
        return None

    def on_start(self) -> None:
        pass

    def on_stop(self) -> None:
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


class TestDataFeedProtocol:
    """Tests for DataFeedProtocol runtime_checkable conformance."""

    def test_concrete_datafeed_implements_protocol(self) -> None:
        feed = ConcreteDataFeed()
        assert isinstance(feed, DataFeedProtocol)


class TestExecutionProtocol:
    """Tests for ExecutionProtocol runtime_checkable conformance."""

    def test_concrete_execution_implements_protocol(self) -> None:
        exec_ = ConcreteExecution()
        assert isinstance(exec_, ExecutionProtocol)


class TestClockProtocol:
    """Tests for ClockProtocol runtime_checkable conformance."""

    def test_concrete_clock_implements_protocol(self) -> None:
        clock = ConcreteClock()
        assert isinstance(clock, ClockProtocol)


class TestEngineProtocol:
    """Tests for EngineProtocol runtime_checkable conformance."""

    def test_concrete_engine_implements_protocol(self) -> None:
        engine = ConcreteEngine()
        assert isinstance(engine, EngineProtocol)
