"""Strategy base class for Quantrex framework.

Abstract base class defining the strategy interface that works across
all execution environments (backtest, live, paper trading, etc.).
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Mapping

from ..models.candle import Candle
from .context import StrategyContext


class Strategy(ABC):
    """Base class for all trading strategies.

    Strategies maintain their own internal state (positions, indicators, etc.)
    and receive candles via the on_candle callback.

    The same Strategy implementation can be used across different execution
    environments without modification.
    """

    def __init__(self) -> None:
        """Initialize strategy. Override to set up initial state.

        Example:
            def __init__(self):
                super().__init__()
                self.position = 0
                self.indicator_values = []
        """
        self._ctx: StrategyContext | None = None

    def set_context(self, ctx: StrategyContext) -> None:
        """Inject StrategyContext after construction. Called by Engine."""
        self._ctx = ctx

    @property
    def ctx(self) -> StrategyContext:
        if self._ctx is None:
            raise RuntimeError("StrategyContext not set. Call set_context() first.")
        return self._ctx

    @abstractmethod
    def on_candle(self, candle: Candle) -> None:
        """Process a single candle.

        This method is called for each candle in the data feed.
        Strategies should implement their trading logic here.

        Args:
            candle: The candle to process (OHLCV data with symbol and timestamp)
        """
        pass

    def compute_indicators(
        self,
        candles: Sequence[Mapping[str, object]],
    ) -> Sequence[Mapping[str, float | int | None]]:
        """Precompute technical indicators over the full ordered candle history.

        The engine calls this hook **exactly once** with the full,
        timestamp-sorted sequence of normalized raw rows (the same
        ``list[dict]`` shape produced by ``DataAdapter.read()``),
        before any ``Candle`` instances are constructed and before
        the per-bar ``on_candle`` loop begins.

        This is the right place to vectorize: convert the rows to
        whatever array/frame format the researcher prefers (pandas,
        polars, numpy, ta-lib, hand-rolled — the framework is
        implementation-agnostic) and compute every indicator in one
        pass. The returned sequence must be **aligned by index** with
        ``candles``; the i-th element is attached to the i-th bar
        via ``Candle.indicators``.

        Default behavior returns one empty mapping per row, so existing
        strategies that do not use indicators are source-compatible
        and do not need to override this hook.

        Args:
            candles: Full ordered raw row sequence. Each element is a
                string-keyed mapping with at least ``"datetime"``,
                ``"open"``, ``"high"``, ``"low"``, ``"close"``,
                ``"volume"`` (the standardized adapter shape).

        Returns:
            A sequence of mappings, one per bar, aligned by index.
            Each mapping maps indicator name to ``float | int | None``.
            ``None`` is the recommended sentinel for warmup bars where
            an indicator is not yet defined.

        Raises:
            Any exception raised here is wrapped by the engine as a
            data-provider failure (``ProviderError`` in backtest). Log
            via ``logger.exception(..., exc_info=True)`` to capture the
            full stack trace before re-raising.
        """
        # No-op default: one empty per-bar mapping keeps ``on_candle``
        # callers working unchanged while giving subclasses a single
        # override point for vectorized indicator computation.
        return [{} for _ in candles]

    def on_start(self) -> None:
        """Called once before processing begins.

        Override to perform initialization that requires the strategy
        to be fully constructed (e.g., connecting to indicators).
        """
        pass

    def on_stop(self) -> None:
        """Called once after processing ends.

        Override to perform cleanup (e.g., closing positions, saving state).
        """
        pass