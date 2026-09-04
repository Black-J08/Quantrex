"""SMA crossover strategy using DhanDataProvider and DhanDataAdapter.

Buys when a fast SMA crosses above a slow SMA (golden cross) and closes
the position when it crosses back below (death cross).

Indicators are precomputed in :meth:`SmaCrossoverStrategy.compute_indicators`
over the full sorted candle history, so :meth:`on_candle` is pure logic
with no per-bar rolling-window bookkeeping.

Requires the DHAN_ACCESS_TOKEN environment variable or a .env file at
the project root.

Usage:
    cp .env.example .env  # then add your Dhan access token
    uv run python examples/sma_crossover_dhan_strategy.py
"""

import os
import sys
from collections.abc import Sequence
from typing import Mapping

from dotenv import load_dotenv

from quantrex_core.logging import get_logger, setup_logging
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.strategy.base import Strategy
from quantrex_data.providers.dhan_provider import DhanDataProvider
from quantrex_data.adapters.dhan_adapter import DhanDataAdapter
from quantrex_backtest import BacktestEngine

logger = get_logger(__name__)

# Load .env from the project root once at module import so that os.getenv()
# calls below (and inside the data provider) can see DHAN_ACCESS_TOKEN.
load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"),
    override=False,
)

FAST_PERIOD = 5
SLOW_PERIOD = 20
TRADE_QTY = 10.0
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _sma(values: list[float], period: int) -> list[float | None]:
    """Return a simple moving average of ``values`` with ``period``-bar window.

    Returns ``None`` for warmup bars where fewer than ``period`` values are
    available. Pure Python — the framework is indicator-implementation
    agnostic, so this strategy does not depend on pandas / polars / ta-lib.
    A researcher can swap this body for ``pandas.Series.rolling(period).mean()``
    or any vectorized library inside the same override without touching
    the rest of the strategy.
    """
    out: list[float | None] = []
    running_sum = 0.0
    for i, v in enumerate(values):
        running_sum += v
        if i >= period:
            running_sum -= values[i - period]
        if i + 1 >= period:
            out.append(running_sum / period)
        else:
            out.append(None)
    return out


class SmaCrossoverStrategy(Strategy):
    """Long-only SMA crossover: buy on golden cross, exit on death cross.

    Indicators are precomputed in :meth:`compute_indicators` over the full
    sorted candle history, so :meth:`on_candle` is pure logic with no
    per-bar O(period) bookkeeping. The same ``Strategy`` subclass works
    unchanged across backtest, live, and paper trading because the hook
    lives on the shared base class.
    """

    def __init__(self, fast_period: int = FAST_PERIOD, slow_period: int = SLOW_PERIOD) -> None:
        super().__init__()
        self._fast_period = fast_period
        self._slow_period = slow_period
        # Previous (fast, slow) pair so we can detect a crossover this bar.
        self._prev_sma: tuple[float | None, float | None] = (None, None)

    def compute_indicators(
        self,
        candles: Sequence[Mapping[str, object]],
    ) -> Sequence[Mapping[str, float | None]]:
        """Vectorize the fast and slow SMAs in one pass over the full history.

        The engine calls this hook exactly once, with the full timestamp-
        sorted raw row sequence, before any ``Candle`` is constructed and
        before the per-bar loop. Returning a list aligned by index lets
        the engine attach the i-th mapping to the i-th ``Candle.indicators``
        without any per-bar recomputation in :meth:`on_candle`.
        """
        closes = [float(row["close"]) for row in candles]
        fast_sma = _sma(closes, self._fast_period)
        slow_sma = _sma(closes, self._slow_period)
        return [
            {"sma_fast": f, "sma_slow": s}
            for f, s in zip(fast_sma, slow_sma)
        ]

    def on_candle(self, candle: Candle) -> None:
        fast = candle.indicators.get("sma_fast")
        slow = candle.indicators.get("sma_slow")
        prev_fast, prev_slow = self._prev_sma
        self._prev_sma = (fast, slow)

        # Warmup bars (any SMA is None) cannot produce a crossover signal.
        if None in (fast, slow, prev_fast, prev_slow):
            return

        position = self.ctx.get_position(candle.symbol)

        # Golden cross: fast crosses above slow -> go long (or add).
        if prev_fast <= prev_slow and fast > slow and position.quantity <= 0:
            order = self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.BUY,
                quantity=TRADE_QTY,
            )
            logger.info(
                "[%s] GOLDEN CROSS  -> BUY  %s %s (order %s, %s)",
                candle.timestamp, TRADE_QTY, candle.symbol, order.id, order.status.value,
            )

        # Death cross: fast crosses below slow -> flatten long.
        elif prev_fast >= prev_slow and fast < slow and position.quantity > 0:
            order = self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.SELL,
                quantity=position.quantity,
            )
            logger.info(
                "[%s] DEATH CROSS   -> SELL %s %s (order %s, %s)",
                candle.timestamp, position.quantity, candle.symbol, order.id, order.status.value,
            )


def main() -> None:
    setup_logging(level="INFO")
    access_token = os.getenv("DHAN_ACCESS_TOKEN")
    if not access_token:
        logger.error(
            "DHAN_ACCESS_TOKEN not found. Set it via a .env file in the project root "
            "or export it in your shell."
        )
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("SMA Crossover Strategy (Dhan data, precomputed indicators)")
    logger.info("=" * 60)

    # Pick a window long enough that slow SMA + crossover signal can form.
    provider = DhanDataProvider(
        symbol="TCS",
        exchange_segment="NSE_EQ",
        instrument="EQUITY",
        from_date="2023-02-01",
        to_date="2024-02-01",
        timeframe="day",
    )

    # datetime_format MUST match what we pass to BacktestEngine below,
    # otherwise Candle.from_row fails to parse the adapter's output.
    # Dhan returns timestamps in IST; the adapter's default output timezone
    # is also IST so Candle.timestamp and the exported closed_trades.csv
    # show the exchange's local clock (e.g. 09:30 for the market open).
    adapter = DhanDataAdapter(provider, datetime_format=DATETIME_FORMAT)

    strategy = SmaCrossoverStrategy(fast_period=FAST_PERIOD, slow_period=SLOW_PERIOD)
    engine = BacktestEngine(adapter, strategy, symbol="RELIANCE")

    try:
        logger.info("Starting backtest...")
        engine.run()
        logger.info("Backtest completed successfully!")
    except Exception:
        logger.exception("Error during backtest")
    finally:
        adapter.close()


if __name__ == "__main__":
    main()
