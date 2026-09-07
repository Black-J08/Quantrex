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

from ..models.candle import Candle
from ..models.enums import OrderSide, OrderType
from ..models.order import Order
from ..models.position import Position


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
