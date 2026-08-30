"""Example strategy using DhanDataProvider and DhanDataAdapter.

This example demonstrates how to use the Dhan data provider for backtesting.
Requires DHAN_ACCESS_TOKEN environment variable or .env file.

Usage:
    # With .env file (recommended)
    cp .env.example .env
    # Edit .env with your Dhan access token
    uv run python examples/dhan_example_strategy.py

    # Or with environment variable
    DHAN_ACCESS_TOKEN=your_token uv run python examples/dhan_example_strategy.py
"""

import os
import sys

from dotenv import load_dotenv
from quantrex_core.logging import get_logger, setup_logging
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.strategy.base import Strategy
from quantrex_data.providers.dhan_provider import DhanDataProvider
from quantrex_data.adapters.dhan_adapter import DhanDataAdapter
from quantrex_backtest import BacktestEngine

logger = get_logger(__name__)

# Load .env from the project root once at process start so subsequent
# os.getenv() calls (and anything in the data provider) see the token.
# Override=False ensures a real exported env var still wins over the file.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"), override=False)


class DhanExampleStrategy(Strategy):
    """Example strategy that buys on bullish candles and tracks position."""

    def __init__(self):
        super().__init__()
        self.candles_received = 0
        self.orders_placed = 0

    def on_start(self) -> None:
        logger.info("Strategy started - waiting for candles...")

    def on_candle(self, candle: Candle) -> None:
        self.candles_received += 1
        logger.info(
            "[%s] %s O:%.2f H:%.2f L:%.2f C:%.2f V:%.0f",
            candle.timestamp, candle.symbol,
            candle.open, candle.high, candle.low, candle.close, candle.volume,
        )

        # Simple strategy: buy 10 shares on first bullish candle
        if self.candles_received == 1 and candle.close > candle.open:
            order = self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.BUY,
                quantity=10.0,
            )
            self.orders_placed += 1
            logger.info("  -> Placed BUY order: %s (%s)", order.id, order.status)

        # Report position
        position = self.ctx.get_position(candle.symbol)
        logger.info("  -> Position: %s shares", position.quantity)

    def on_stop(self) -> None:
        logger.info(
            "Strategy stopped. Candles processed: %d, Orders placed: %d",
            self.candles_received, self.orders_placed,
        )


def main():
    """Run the example strategy with Dhan data."""
    setup_logging(level="INFO")
    # Check for access token. .env was loaded at module import above.
    access_token = os.getenv("DHAN_ACCESS_TOKEN")
    if not access_token:
        logger.error(
            "DHAN_ACCESS_TOKEN not found. Set it via a .env file in the project root "
            "or export it in your shell. See .env.example for the template."
        )
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Dhan Data Provider Example Strategy")
    logger.info("=" * 60)

    # Create provider with symbol resolution
    # Using RELIANCE (NSE_EQ) as example - replace with your desired symbol
    provider = DhanDataProvider(
        symbol="RELIANCE",
        exchange_segment="NSE_EQ",
        instrument="EQUITY",
        from_date="2024-01-01",
        to_date="2024-01-10",
        timeframe="day",
        include_oi=False,
    )

    # Create adapter
    # Dhan returns timestamps in IST; the adapter's default output timezone
    # is also IST so Candle.timestamp and the exported closed_trades.csv
    # show the exchange's local clock.
    adapter = DhanDataAdapter(
        provider,
        datetime_format="%Y-%m-%d %H:%M:%S",
    )

    # Create strategy and engine
    # Note: datetime_format MUST match the format the adapter emits; otherwise
    # Candle.from_row will fail with "unconverted data" / ValueError.
    strategy = DhanExampleStrategy()
    engine = BacktestEngine(adapter, strategy, symbol="RELIANCE")

    try:
        logger.info("Starting backtest...")
        engine.run()
        logger.info("Backtest completed successfully!")
    except Exception as e:
        logger.exception("Error during backtest: %s", e)
    finally:
        adapter.close()


if __name__ == "__main__":
    main()