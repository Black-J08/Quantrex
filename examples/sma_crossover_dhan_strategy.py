"""SMA crossover strategy using DhanDataProvider and DhanDataAdapter.

Buys when a fast SMA crosses above a slow SMA (golden cross) and closes
the position when it crosses back below (death cross).

Requires the DHAN_ACCESS_TOKEN environment variable or a .env file at
the project root.

Usage:
    cp .env.example .env  # then add your Dhan access token
    uv run python examples/sma_crossover_dhan_strategy.py
"""

import os
import sys
from collections import deque

from dotenv import load_dotenv
from loguru import logger

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.strategy.base import Strategy
from quantrex_data.providers.dhan_provider import DhanDataProvider
from quantrex_data.adapters.dhan_adapter import DhanDataAdapter
from quantrex_backtest import BacktestEngine

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


class SmaCrossoverStrategy(Strategy):
    """Long-only SMA crossover: buy on golden cross, exit on death cross."""

    def __init__(self, fast_period: int = FAST_PERIOD, slow_period: int = SLOW_PERIOD) -> None:
        super().__init__()
        self._fast_period = fast_period
        self._slow_period = slow_period
        self._closes: deque[float] = deque(maxlen=slow_period)
        # Previous (fast, slow) pair so we can detect a crossover this bar.
        self._prev_sma: tuple[float | None, float | None] = (None, None)

    def _sma(self, period: int) -> float | None:
        if len(self._closes) < period:
            return None
        return sum(list(self._closes)[-period:]) / period

    def on_candle(self, candle: Candle) -> None:
        self._closes.append(candle.close)

        fast = self._sma(self._fast_period)
        slow = self._sma(self._slow_period)
        prev_fast, prev_slow = self._prev_sma
        self._prev_sma = (fast, slow)

        # Need two consecutive candles with both SMAs defined to detect a cross.
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
            print(f"[{candle.timestamp}] GOLDEN CROSS  -> BUY  {TRADE_QTY} {candle.symbol} (order {order.id}, {order.status.value})")

        # Death cross: fast crosses below slow -> flatten long.
        elif prev_fast >= prev_slow and fast < slow and position.quantity > 0:
            order = self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.SELL,
                quantity=position.quantity,
            )
            print(f"[{candle.timestamp}] DEATH CROSS   -> SELL {position.quantity} {candle.symbol} (order {order.id}, {order.status.value})")


def main() -> None:
    access_token = os.getenv("DHAN_ACCESS_TOKEN")
    if not access_token:
        logger.error(
            "DHAN_ACCESS_TOKEN not found. Set it via a .env file in the project root "
            "or export it in your shell."
        )
        sys.exit(1)

    print("=" * 60)
    print("SMA Crossover Strategy (Dhan data)")
    print("=" * 60)

    # Pick a window long enough that slow SMA + crossover signal can form.
    provider = DhanDataProvider(
        symbol="RELIANCE",
        exchange_segment="NSE_EQ",
        instrument="EQUITY",
        from_date="2023-02-01",
        to_date="2024-02-01",
        timeframe="day",
    )

    # datetime_format MUST match what we pass to BacktestEngine below,
    # otherwise Candle.from_row fails to parse the adapter's output.
    adapter = DhanDataAdapter(provider, datetime_format=DATETIME_FORMAT, timezone="UTC")

    strategy = SmaCrossoverStrategy(fast_period=FAST_PERIOD, slow_period=SLOW_PERIOD)
    engine = BacktestEngine(adapter, strategy, symbol="RELIANCE", datetime_format=DATETIME_FORMAT)

    try:
        print("\nStarting backtest...")
        engine.run()
        print("\nBacktest completed successfully!")
    except Exception:
        logger.exception("Error during backtest")
    finally:
        adapter.close()


if __name__ == "__main__":
    main()
