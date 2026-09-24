"""Live trading strategy context.

Context for live trading — routes orders directly to the broker
(via PositionManager) without an OMS queue, since T+1 execution semantics
apply only to the backtest engine. Maintains a bounded history buffer
for strategy lookback and timeframe_history support.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, time
from typing import TYPE_CHECKING

from quantrex_core import StrategyContext
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide, OrderType, OrderStatus
from quantrex_core.timeframe import filter_candles_by_timeframe

if TYPE_CHECKING:
    from quantrex_core.position.manager import PositionManager


class LiveStrategyContext(StrategyContext):
    """Live trading context — no OMS, orders go directly to broker/PM.

    For live trading, orders are submitted to the broker in real-time.
    The PositionManager records them for position tracking. An OMS for
    live trading (e.g. to handle exchange-side latency) is TODO.
    
    Maintains a bounded ring buffer of candles for history and timeframe_history.
    The buffer should be pre-filled from the broker's historical-candles endpoint
    (or replayed warmup bars) before the first ``on_candle`` is dispatched.
    """

    def __init__(
        self, 
        position_manager: PositionManager,
        max_history_size: int = 10000,
        origin_time: time | None = None,
    ) -> None:
        self._pm: PositionManager = position_manager
        self._max_history_size = max_history_size
        # Bounded ring buffer for candle history (oldest first)
        self._history_buffer: deque[Candle] = deque(maxlen=max_history_size)
        # Derived timeframe histories (updated incrementally)
        self._derived_histories: dict[str, deque[Candle]] = {}
        self._base_timeframe = "1M"  # Default, will be set by engine
        self._origin_time = origin_time

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: float | None = None,
    ):
        if quantity <= 0:
            return Order(status=OrderStatus.REJECTED, id="0")
        return self._pm.submit_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
        )

    def get_position(self, symbol: str):
        return self._pm.get_position(symbol)

    @property
    def current_time(self) -> datetime:
        """Execution time: the simulated clock at which the current bar is processed.

        Not yet implemented for live trading — live execution time will be
        wired when real-time candle subscription lands in the live engine.
        """
        raise NotImplementedError(
            "current_time is not yet supported by the live engine; "
            "execution-time semantics are currently backtest-only."
        )

    def add_candle(self, candle: Candle) -> None:
        """Add a new candle to the history buffer.
        
        Called by LiveEngine when a new candle is received.
        Updates both base history and derived timeframe histories.
        
        Args:
            candle: The new candle to add.
        """
        self._history_buffer.append(candle)
        self._update_derived_histories(candle)

    def _update_derived_histories(self, candle: Candle) -> None:
        """Update derived timeframe histories with a new candle.
        
        For live trading, we only add closed higher-timeframe candles.
        The current forming higher-timeframe candle is NOT added until it closes.
        """
        # Use candle's own timeframe and close_time for validation
        tf = candle.timeframe
        close_time = candle.close_time
        
        # If this is a base timeframe candle, check if any derived timeframes are now complete
        if tf == self._base_timeframe:
            # Check all derived timeframes
            for derived_tf in list(self._derived_histories.keys()):
                # In a full implementation, we'd track forming derived candles
                # and add them when their close_time is reached
                pass
        else:
            # This is a derived timeframe candle - add it if its close_time has passed
            # For now, we just add it (simplified)
            if tf not in self._derived_histories:
                from collections import deque
                self._derived_histories[tf] = deque(maxlen=self._max_history_size)
            self._derived_histories[tf].append(candle)

    def set_base_timeframe(self, timeframe: str) -> None:
        """Set the base timeframe for this context."""
        self._base_timeframe = timeframe

    def warmup_from_history(self, candles: list[Candle]) -> None:
        """Pre-fill history buffer with historical candles for warmup.
        
        Called by LiveEngine before starting live trading to provide
        initial history for indicators and lookback.
        
        Args:
            candles: List of historical candles in chronological order.
        """
        for candle in candles:
            self._history_buffer.append(candle)
        # Rebuild derived histories from warmup data
        self._rebuild_derived_histories()

    def _rebuild_derived_histories(self) -> None:
        """Rebuild derived timeframe histories from current buffer."""
        # Clear existing derived histories
        self._derived_histories.clear()
        
        # For each registered timeframe (would come from strategy), build history
        # This is a placeholder - actual implementation would use strategy's timeframe_registry
        pass

    @property
    def history(self) -> tuple[Candle, ...]:
        """Live history buffer — bounded ring buffer of recent candles.
        
        Returns a tuple of :class:`Candle` instances in **chronological
        order** (oldest first, newest last). The most recent candle
        is the last element.
        
        During warmup, the tuple may be shorter than the strategy's
        requested lookback; callers should guard with
        ``if len(ctx.history) < N: return``.
        
        Returns:
            Tuple of candles from the live history buffer.
        """
        return tuple(self._history_buffer)

    def timeframe_history(self, interval: str) -> tuple[Candle, ...]:
        """Live timeframe history — filtered view of history buffer.
        
        Returns a tuple of :class:`Candle` instances in **chronological
        order** (oldest first, newest last) that belong to the specified
        timeframe interval (e.g., "1H", "1D", "4H").
        
        For the base timeframe, returns the full history buffer.
        For derived timeframes, returns pre-computed derived candles
        (only closed higher-timeframe candles).
        
        Contract:
        * **Warmup**: while fewer than ``N`` bars of the timeframe have
          been processed, ``len(timeframe_history(interval)) < N``.
        * **Read-only**: the returned tuple is immutable; a snapshot.
        * **Derived view**: filtered from the live history buffer.
        
        Args:
            interval: Timeframe interval string (e.g., "1H", "1D", "4H").
            
        Returns:
            Tuple of candles belonging to the specified timeframe.
        """
        if interval == self._base_timeframe:
            return tuple(self._history_buffer)
        
        # Return pre-computed derived history if available
        if interval in self._derived_histories:
            return tuple(self._derived_histories[interval])
        
        # Fallback: filter from base history (for backward compatibility)
        return tuple(self._filter_by_timeframe(list(self._history_buffer), interval, self._origin_time))

    @staticmethod
    def _filter_by_timeframe(candles: list[Candle], interval: str, origin_time: time | None = None) -> list[Candle]:
        """Filter candles by timeframe interval using shared implementation.

        Delegates to quantrex_core.timeframe.filter_candles_by_timeframe.

        Args:
            candles: List of candles in chronological order.
            interval: Timeframe interval string (e.g., "1H", "1D", "4H").
            origin_time: Market origin time for interval alignment.

        Returns:
            List of candles representing the last candle of each interval.
        """
        if not candles:
            return []

        # Use origin time for correct interval alignment
        # If origin_time is not set, default to midnight (00:00)
        if origin_time is None:
            origin_time = time(0, 0)

        return list(filter_candles_by_timeframe(candles, interval, origin_time))
