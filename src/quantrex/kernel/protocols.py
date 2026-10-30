"""Kernel protocols defining the contracts for strategies, engines, context, data feeds, execution, and clock."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from quantrex.core.models.market_data import OHLCVCandle, Tick
from quantrex.core.models.orders import Order
from quantrex.core.models.positions import Position
from quantrex.core.models.signals import Signal
from quantrex.core.models.timeframe import Timeframe
from quantrex.core.models.trades import Trade


@runtime_checkable
class StrategyProtocol(Protocol):
    """Protocol for trading strategies.

    A strategy reacts to market events and may emit signals.
    """

    def on_bar(self, candle: OHLCVCandle) -> Signal | None:
        """Handle a new bar/candle.

        Args:
            candle: The completed OHLCV candle.

        Returns:
            An optional trading signal, or ``None`` if no signal is emitted.
        """
        ...

    def on_start(self) -> None:
        """Called once before the event loop begins."""
        ...

    def on_stop(self) -> None:
        """Called once after the event loop ends."""
        ...

    def on_tick(self, tick: Tick) -> None:
        """Handle a new tick.

        Args:
            tick: The new tick data.
        """
        ...

    def on_order(self, order: Order) -> None:
        """Handle an order status update.

        Args:
            order: The updated order.
        """
        ...

    def on_fill(self, trade: Trade) -> None:
        """Handle a trade fill.

        Args:
            trade: The executed trade.
        """
        ...


@runtime_checkable
class ContextProtocol(Protocol):
    """Protocol for the execution context exposed to strategies."""

    @property
    def current_time(self) -> datetime:
        """Current simulation/live time."""
        ...

    @property
    def history(self) -> tuple[OHLCVCandle, ...]:
        """Read-only snapshot of historical candles seen so far."""
        ...

    def submit_order(self, order: Order) -> Order:
        """Submit an order for execution.

        Args:
            order: The order to submit.

        Returns:
            The submitted order (possibly with updated status).
        """
        ...

    def get_position(self, symbol: str) -> Position | None:
        """Get the current position for a symbol.

        Args:
            symbol: Instrument symbol.

        Returns:
            The current position, or ``None`` if no position exists.
        """
        ...


@runtime_checkable
class DataFeedProtocol(Protocol):
    """Protocol for market data feeds."""

    @property
    def islive(self) -> bool:
        """Whether the feed is live (``True``) or historical (``False``)."""
        ...

    def subscribe(self, symbol: str) -> None:
        """Subscribe to live updates for a symbol.

        Args:
            symbol: Instrument symbol to subscribe to.
        """
        ...

    def get_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: Timeframe,
    ) -> list[OHLCVCandle]:
        """Retrieve historical candles for a symbol.

        Args:
            symbol: Instrument symbol.
            start: Start timestamp (inclusive).
            end: End timestamp (exclusive).
            timeframe: Candle timeframe.

        Returns:
            List of candles sorted by timestamp.
        """
        ...


@runtime_checkable
class ExecutionProtocol(Protocol):
    """Protocol for order execution."""

    def submit_order(self, order: Order) -> Order:
        """Submit an order for execution.

        Args:
            order: The order to submit.

        Returns:
            The submitted order with updated status.
        """
        ...

    def cancel_order(self, order_id: UUID) -> None:
        """Cancel an open order.

        Args:
            order_id: The ID of the order to cancel.
        """
        ...

    def get_position(self, symbol: str) -> Position | None:
        """Get the current position for a symbol.

        Args:
            symbol: Instrument symbol.

        Returns:
            The current position, or ``None`` if no position exists.
        """
        ...

    def get_account(self) -> dict[str, object]:
        """Get account information.

        Returns:
            A dictionary of account details.
        """
        ...


@runtime_checkable
class ClockProtocol(Protocol):
    """Protocol for the clock used by the kernel."""

    def now(self) -> datetime:
        """Return the current time."""
        ...

    def advance(self, target: datetime) -> None:
        """Advance the clock to the given time.

        Args:
            target: The target time to advance to.
        """
        ...


@runtime_checkable
class EngineProtocol(Protocol):
    """Protocol for trading engines.

    The kernel interacts with engines through this protocol: it calls
    :meth:`execute_signal` to convert strategy signals into orders, and
    :meth:`get_pending_fills` to retrieve trade fills.
    """

    def execute_signal(self, signal: Signal) -> Order:
        """Convert a signal to an order and submit for execution.

        Args:
            signal: The trading signal from the strategy.

        Returns:
            The resulting order.
        """
        ...

    def get_pending_fills(self) -> list[Trade]:
        """Return and clear any pending trade fills.

        Returns:
            A list of trades that have been filled since the last call.
        """
        ...

    def submit_order(self, order: Order) -> Order:
        """Submit an order for execution.

        Args:
            order: The order to submit.

        Returns:
            The submitted order with updated status.
        """
        ...

    def get_position(self, symbol: str) -> Position | None:
        """Get the current position for a symbol.

        Args:
            symbol: Instrument symbol.

        Returns:
            The current position, or ``None`` if no position exists.
        """
        ...

    def on_start(self) -> None:
        """Called once before the event loop begins."""
        ...

    def on_stop(self) -> None:
        """Called once after the event loop ends."""
        ...
