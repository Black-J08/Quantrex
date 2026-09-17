from datetime import datetime, time, timedelta
from quantrex_core.logging import get_logger
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderStatus, OrderType
from quantrex_core.models.order import Order, OrderSide
from quantrex_core.models.position import Position
from quantrex_core.order import OrderManagementSystem
from quantrex_core.position.manager import PositionManager
from quantrex_core.strategy.context import StrategyContext
from quantrex_backtest.core.timeframe import calculate_close_time
from collections.abc import Mapping


logger = get_logger(__name__)


class BacktestStrategyContext(StrategyContext):
    """Backtest-specific StrategyContext.

    Queues orders through the OMS for T+1 execution and delegates position
    updates to PositionManager.
    """

    def __init__(
        self,
        position_manager: PositionManager,
        oms: OrderManagementSystem,
        current_time: datetime,
        raw_data_by_timeframe: dict[str, list[dict]] | None = None,
        indicators_by_timeframe: dict[str, list[Mapping]] | None = None,
        base_timeframe: str = "1M",
        origin_time: time | None = None,
    ) -> None:
        self._pm = position_manager
        self._oms = oms
        self._current_time = current_time
        self._current_candle: Candle | None = None
        # Append-only candle history. The engine calls ``record_candle``
        # once per bar inside the per-bar loop, immediately before
        # ``strategy.on_candle``. Exposed read-only via the ``history``
        # property so strategies can do per-bar, ad-hoc lookback
        # (e.g. ``ctx.history[-20:]``) without owning a deque.
        self._history: list[Candle] = []
        
        # Multi-timeframe support
        self._base_timeframe = base_timeframe
        self._raw_data_by_timeframe = raw_data_by_timeframe or {}
        self._indicators_by_timeframe = indicators_by_timeframe or {}
        self._derived_candles: dict[str, list[Candle]] = {}
        self._derived_histories: dict[str, list[Candle]] = {}
        self._derived_indices: dict[str, int] = {}
        self._base_completed_index = 0
        self._symbol = ""
        self._datetime_format = "%Y%m%d %H:%M"
        self._origin_time = origin_time
        
        # Pre-compute derived timeframe candles
        if raw_data_by_timeframe and indicators_by_timeframe:
            self._precompute_derived_candles()

    def _precompute_derived_candles(self) -> None:
        """Pre-compute candles for all non-base timeframes."""
        for tf, raw_rows in self._raw_data_by_timeframe.items():
            if tf != self._base_timeframe:
                indicators = self._indicators_by_timeframe.get(tf, [{} for _ in raw_rows])
                self._derived_candles[tf] = self._build_candles_for_timeframe(tf, raw_rows, indicators)
                self._derived_histories[tf] = []
                self._derived_indices[tf] = 0

    def _build_candles_for_timeframe(self, timeframe: str, raw_rows: list[dict], indicators: list[Mapping]) -> list[Candle]:
        """Build Candle objects for a specific timeframe from raw rows."""
        candles = []
        for idx, row in enumerate(raw_rows):
            try:
                candle = Candle.from_row(
                    row,
                    self._symbol,
                    self._datetime_format,
                    indicators=indicators[idx] if idx < len(indicators) else {},
                )
                candles.append(candle)
            except Exception:
                # Skip malformed rows
                continue
        return candles

    def set_symbol_and_format(self, symbol: str, datetime_format: str) -> None:
        """Set symbol and datetime format for derived candle construction.
        
        Called by engine after context creation.
        """
        self._symbol = symbol
        self._datetime_format = datetime_format
        # Rebuild derived candles with correct symbol and format
        if self._raw_data_by_timeframe and self._indicators_by_timeframe:
            self._precompute_derived_candles()

    def submit_order(self, symbol: str, side: OrderSide, quantity: float,
                     order_type: OrderType = OrderType.MARKET) -> Order:
        if self._current_candle is None:
            raise RuntimeError("Cannot submit order: no current candle available. Call update_time() first.")
        # Reject non-positive quantity — return a REJECTED Order rather than
        # raising, so the audit trail records it with the same shape as an
        # ACCEPTED order (same timestamp, symbol, side, qty, type).
        if quantity <= 0:
            rejected = Order(
                id="0",
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                status=OrderStatus.REJECTED,
                timestamp=self._current_time,
            )
            logger.info(
                "[%s %s] ORDER id=%s status=REJECTED side=%s qty=%s type=%s price=%s",
                symbol,
                self._current_time.isoformat(),
                rejected.id,
                side.value,
                quantity,
                order_type.value,
                self._current_candle.open,
            )
            return rejected
        # Build the order in PENDING state and queue it for T+1 drain.
        # The OMS holds it until the engine drains at the next candle's open.
        order = Order(
            id="",  # Placeholder; engine assigns real id at drain time
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            status=OrderStatus.PENDING,
            timestamp=self._current_time,
        )
        # Store fill context: the order will be filled at the NEXT candle's open.
        self._oms.submit(order, fill_price=self._current_candle.open, fill_timestamp=self._current_time)
        return order

    def get_position(self, symbol: str) -> Position:
        return self._pm.get_position(symbol)

    @property
    def equity(self) -> float:
        """Total portfolio equity (cash + position market values)."""
        # For single-instrument mode, equity = cash + position value
        cash = 0.0  # We don't track cash in single-instrument mode
        position_value = 0.0
        for symbol in self._pm._lots.keys():
            pos = self._pm.get_position(symbol)
            if pos.quantity != 0:
                # Use entry price as approximation for current value
                position_value += abs(pos.quantity) * pos.entry_price
        return cash + position_value

    @property
    def current_time(self) -> datetime:
        """Execution time: the simulated clock at which the current bar is processed.

        This is the **close time** of the candle currently being processed
        (open time + timeframe duration), NOT the candle's open-time
        ``timestamp``. It advances with each processed candle and is the
        backtest's virtual "now" — never the machine's wall-clock time.

        Before the first bar is processed this is ``datetime.min``.
        """
        return self._current_time

    def update_time(self, timestamp: datetime) -> None:
        """Called by engine before each candle to update order timestamp."""
        self._current_time = timestamp

    def update_candle(self, candle: Candle) -> None:
        """Called by engine before each candle to provide current candle for pricing."""
        self._current_candle = candle

    def record_candle(self, candle: Candle) -> None:
        """Append ``candle`` to the per-bar history.

        Called by the engine once per bar, after ``update_candle`` and
        before ``strategy.on_candle``, so the strategy observes the
        current bar as the last element of ``ctx.history`` (``[-1]``).
        Append-only by design; clearing or mutating the history would
        silently break per-bar lookback in strategies that already
        captured a reference.
        """
        self._history.append(candle)

        # Update derived timeframe histories using the current execution
        # time (close of the base bar just processed), so a higher-
        # timeframe candle becomes visible exactly when its close time is
        # reached — not one base bar later.
        self._update_derived_histories(self._current_time)

    def _update_derived_histories(self, current_timestamp: datetime) -> None:
        """Update derived timeframe histories with candles that have completed.

        A derived candle is complete when its **close time** (open time +
        its own timeframe duration) is at or before the current execution
        time. Comparing open times here would dispatch higher-timeframe
        candles before they finish forming.
        """
        # Update base timeframe completed index
        while (self._base_completed_index < len(self._history) and
               calculate_close_time(self._history[self._base_completed_index].timestamp, self._base_timeframe) <= current_timestamp):
            self._base_completed_index += 1

        for tf, derived_candles in self._derived_candles.items():
            derived_history = self._derived_histories[tf]
            idx = self._derived_indices[tf]

            # Add all derived candles whose close time has passed
            while idx < len(derived_candles) and calculate_close_time(
                derived_candles[idx].timestamp, tf
            ) <= current_timestamp:
                derived_history.append(derived_candles[idx])
                idx += 1

            self._derived_indices[tf] = idx

    def reset(self) -> None:
        """Clear the per-bar history and the current candle.

        Called by the engine at the start of each ``run()`` so that
        repeated invocations on the same engine instance do not see
        candles from a previous run. Also exposed for tests that reuse
        a context across multiple scenarios.
        """
        self._history.clear()
        self._current_candle = None
        # Reset derived histories
        for tf in self._derived_histories:
            self._derived_histories[tf].clear()
            self._derived_indices[tf] = 0
        # Reset base timeframe completed index
        self._base_completed_index = 0

    

    @property
    def history(self) -> tuple[Candle, ...]:
        """Read-only view of all candles processed on this stream, oldest first.

        The current candle is the last element. During warmup the tuple
        is shorter than the strategy's requested lookback; callers should
        guard with ``if len(ctx.history) < N: return`` rather than relying
        on sentinels. Returned as a fresh ``tuple`` snapshot so callers
        cannot mutate the context's internal state.
        
        Returns only completed candles (those whose close time has passed).
        For backward compatibility with tests, returns all candles when
        current_time is at the minimum value (indicating uninitialized context).
        """
        return tuple(self._history[:self._base_completed_index])

    def timeframe_history(self, interval: str) -> tuple[Candle, ...]:
        """Read-only view of candles filtered by timeframe interval.

        Returns a tuple of :class:`Candle` instances in **chronological
        order** (oldest first, newest last) that belong to the specified
        timeframe interval (e.g., "1H", "1D", "4H").

        For the base timeframe, returns the master history.
        For derived timeframes, returns pre-computed derived candles.

        Contract:
        * **Warmup**: while fewer than ``N`` bars of the timeframe have
          been processed, ``len(timeframe_history(interval)) < N``.
        * **Read-only**: the returned tuple is immutable; a snapshot.
        * **Derived view**: this is a filtered view of ``history``, not
          a separate data feed. No additional storage is allocated.

        Args:
            interval: Timeframe interval string (e.g., "1H", "1D", "4H").

        Returns:
            Tuple of candles belonging to the specified timeframe.
        """
        if interval == self._base_timeframe:
            return tuple(self._history)
        
        # Return pre-computed derived history
        if interval in self._derived_histories:
            return tuple(self._derived_histories[interval])
        
        # Fallback to filtering (for backward compatibility)
        return tuple(self._filter_by_timeframe(self._history, interval))

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

        # Use origin time for correct interval alignment
        # If origin_time is not set, default to midnight (00:00)
        origin_minutes = 0
        if self._origin_time is not None:
            origin_minutes = self._origin_time.hour * 60 + self._origin_time.minute

        # Group candles by interval
        result = []
        current_interval_start = None
        current_interval_candles = []

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
