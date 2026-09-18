"""Strategy–Engine interaction facade.

Defines the single researcher-facing interface that the ``Strategy`` base
class uses to submit orders and query positions during ``on_candle`` calls.
Implementations live in the execution backends:

* :class:`quantrex_backtest.core.context.BacktestStrategyContext` — derives
  fill price from the current candle's open and uses the engine's candle
  timestamp.
* :class:`quantrex_live.core.context.LiveStrategyContext` — placeholder for
  broker-backed order routing; fill price will be supplied by the broker.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict

from ..models.candle import Candle
from ..models.enums import OrderSide, OrderType
from ..models.order import Order
from ..models.position import Position
from ..portfolio.context import PortfolioContext


class StrategyContext(ABC):
    """Single researcher-facing facade for Strategy–Engine interaction.

    Subclasses MUST implement both abstract methods. The default value for
    ``order_type`` is supplied here so concrete implementations don't need
    to redeclare it; ``submit_order`` is the only researcher-facing call
    that accepts a parameter, and the parameter shape is fixed.
    """

    @abstractmethod
    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
    ) -> Order:
        """Submit a MARKET order and return the resulting :class:`Order`.

        Order is accepted immediately; the net position is updated
        synchronously. The order is also recorded in the audit trail.

        Args:
            symbol: Trading symbol.
            side: :attr:`OrderSide.BUY` or :attr:`OrderSide.SELL`.
            quantity: Order quantity. Must be > 0.
            order_type: Order type. Only :attr:`OrderType.MARKET` is
                supported in the MVP.

        Returns:
            The accepted (or rejected) :class:`Order` with its final
            status.
        """
        raise NotImplementedError

    @abstractmethod
    def get_position(self, symbol: str) -> Position:
        """Return the current net :class:`Position` for ``symbol``.

        Returns a zero-quantity :class:`Position` if there is no open
        position for the symbol.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def current_time(self) -> datetime:
        """Execution time: the simulated clock at which the current bar is processed.

        This is the **close time** of the candle currently being processed
        (open time + timeframe duration), NOT the candle's open-time
        ``timestamp``. It represents "now" from the strategy's point of
        view and advances with each processed bar.

        Contract:

        * **Open vs. execution time**: ``candle.timestamp`` is always the
          candle's **open time**; ``ctx.current_time`` is the **execution
          time** (close time). Never mix the two.
        * **Backtest**: advances with each processed candle — it is the
          simulated/virtual clock, never the machine's wall-clock time.
        * **Before the first bar**: the value is engine-defined (the
          backtest engine uses ``datetime.min``).
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def history(self) -> tuple[Candle, ...]:
        """Read-only view of all candles seen so far on the current stream.

        Returns a tuple of :class:`Candle` instances in **chronological
        order** (oldest first, newest last). The candle currently being
        processed is the **last** element (``history[-1]``).

        Contract:

        * **Warmup**: while fewer than ``N`` bars have been processed,
          ``len(history) < N``. The returned tuple is exactly the bars
          that exist — never padded with ``None`` sentinels. Strategies
          that need ``N`` bars should guard with
          ``if len(ctx.history) < N: return``.
        * **Read-only**: the returned tuple is immutable; ``history`` is
          a snapshot, not a live view. Backtests re-evaluate it per
          bar, so the value observed during one ``on_candle`` call
          remains stable for the duration of that call.
        * **Per-stream**: ``history`` is scoped to the stream currently
          feeding ``on_candle``. Multi-stream / multi-timeframe access
          is a separate feature and intentionally not exposed here.

        For full-feed vectorized indicator computation, prefer the
        :meth:`Strategy.compute_indicators` pre-pass — ``history`` is
        intended for per-bar, scalar, ad-hoc lookback (e.g. breakout
        detection, last-N-bar comparisons).
        """
        raise NotImplementedError

    @abstractmethod
    def timeframe_history(self, interval: str) -> tuple[Candle, ...]:
        """Read-only view of candles filtered by timeframe interval.

        Returns a tuple of :class:`Candle` instances in **chronological
        order** (oldest first, newest last) that belong to the specified
        timeframe interval (e.g., "1H", "1D", "4H").

        The filtering is derived from the master ``history`` stream by
        grouping candles into the specified interval. The candle currently
        being processed for that timeframe is the **last** element.

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
        raise NotImplementedError

    # Portfolio-level extensions (composed, not inherited)
    # Default implementations return empty/zero for backward compatibility
    # with single-instrument backtests and live trading without portfolio support.

    @property
    def portfolio(self) -> PortfolioContext:
        """Portfolio-level view: cash, equity, positions dict, margin used.

        Returns an EmptyPortfolioContext by default. Execution environments
        with portfolio support (backtest, live) should override this to
        return their concrete PortfolioContext implementation.
        """
        from quantrex_core.portfolio.context import EmptyPortfolioContext
        return EmptyPortfolioContext()

    @property
    def positions(self) -> Dict[str, Position]:
        """All open positions keyed by symbol.

        Returns empty dict by default. Execution environments with portfolio
        support should override this to return the actual positions dict.
        """
        return {}
