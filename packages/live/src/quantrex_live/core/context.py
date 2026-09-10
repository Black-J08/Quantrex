"""Live trading strategy context.

Context for live trading — routes orders directly to the broker
(via PositionManager) without an OMS queue, since T+1 execution semantics
apply only to the backtest engine. Maintains a bounded history buffer
for strategy lookback and timeframe_history support.
"""

from __future__ import annotations

from collections import deque
from datetime import time
from typing import TYPE_CHECKING

from quantrex_core import StrategyContext
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide, OrderType, OrderStatus

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
        # This is a simplified implementation - in production, you'd track
        # forming higher-timeframe candles and only add them when they close
        pass

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
        return tuple(self._filter_by_timeframe(list(self._history_buffer), interval))

    @staticmethod
    def _filter_by_timeframe(candles: list[Candle], interval: str) -> list[Candle]:
        """Filter candles by timeframe interval.
        
        Groups candles into the specified interval and returns the last
        candle of each completed interval (i.e., the "closed" candles
        for that timeframe).
        
        Args:
            candles: List of candles in chronological order.
            interval: Timeframe interval string (e.g., "1H", "1D", "4H").
            
        Returns:
            List of candles representing the last candle of each interval.
        """
        if not candles:
            return []

        # Parse interval string (e.g., "1H" -> 1 hour, "4H" -> 4 hours, "1D" -> 1 day)
        import re
        match = re.match(r'^(\d+)([MHDW])$', interval.upper())
        if not match:
            raise ValueError(f"Invalid interval format: {interval}. Expected format like '1H', '4H', '1D'")

        value = int(match.group(1))
        unit = match.group(2)

        # Convert to minutes
        if unit == 'M':
            interval_minutes = value
        elif unit == 'H':
            interval_minutes = value * 60
        elif unit == 'D':
            interval_minutes = value * 60 * 24
        elif unit == 'W':
            interval_minutes = value * 60 * 24 * 7
        else:
            raise ValueError(f"Unknown interval unit: {unit}")

        # Group candles by interval
        result = []
        current_interval_start = None
        current_interval_candles = []

        # Use origin time for correct interval alignment
        # If origin_time is not set, default to midnight (00:00)
        origin_minutes = 0
        if self._origin_time is not None:
            origin_minutes = self._origin_time.hour * 60 + self._origin_time.minute

        for candle in candles:
            # Calculate the interval start for this candle using origin time
            candle_minutes = candle.timestamp.hour * 60 + candle.timestamp.minute
            # Add days
            candle_minutes += candle.timestamp.day * 24 * 60
            # Calculate interval start relative to origin time
            # For example, with origin 09:15 (555 minutes) and interval 60 minutes:
            # - 10:15 candle (615 minutes): (615 - 555) // 60 = 1, interval start = 09:15 + 1*60 = 10:15
            # - 11:15 candle (675 minutes): (675 - 555) // 60 = 2, interval start = 09:15 + 2*60 = 11:15
            interval_start_minutes = origin_minutes + ((candle_minutes - origin_minutes) // interval_minutes) * interval_minutes

            if current_interval_start is None:
                current_interval_start = interval_start_minutes
                current_interval_candles = [candle]
            elif interval_start_minutes == current_interval_start:
                current_interval_candles.append(candle)
            else:
                # Interval changed - add the last candle of the previous interval
                if current_interval_candles:
                    result.append(current_interval_candles[-1])
                current_interval_start = interval_start_minutes
                current_interval_candles = [candle]

        # Add the last interval's last candle if it has candles
        if current_interval_candles:
            result.append(current_interval_candles[-1])

        return result
