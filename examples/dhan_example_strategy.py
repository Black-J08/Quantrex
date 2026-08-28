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
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.strategy.base import Strategy
from quantrex_data.providers.dhan_provider import DhanDataProvider
from quantrex_data.adapters.dhan_adapter import DhanDataAdapter
from quantrex_backtest import BacktestEngine


class DhanExampleStrategy(Strategy):
    """Example strategy that buys on bullish candles and tracks position."""

    def __init__(self):
        super().__init__()
        self.candles_received = 0
        self.orders_placed = 0

    def on_start(self) -> None:
        print("Strategy started - waiting for candles...")

    def on_candle(self, candle: Candle) -> None:
        self.candles_received += 1
        print(f"[{candle.timestamp}] {candle.symbol} O:{candle.open:.2f} H:{candle.high:.2f} L:{candle.low:.2f} C:{candle.close:.2f} V:{candle.volume:.0f}")

        # Simple strategy: buy 10 shares on first bullish candle
        if self.candles_received == 1 and candle.close > candle.open:
            order = self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.BUY,
                quantity=10.0,
            )
            self.orders_placed += 1
            print(f"  -> Placed BUY order: {order.id} ({order.status})")

        # Report position
        position = self.ctx.get_position(candle.symbol)
        print(f"  -> Position: {position.quantity} shares")

    def on_stop(self) -> None:
        print(f"Strategy stopped. Candles processed: {self.candles_received}, Orders placed: {self.orders_placed}")


def main():
    """Run the example strategy with Dhan data."""
    # Check for access token
    access_token = os.getenv("DHAN_ACCESS_TOKEN")
    if not access_token:
        print("ERROR: DHAN_ACCESS_TOKEN not set.")
        print("Please either:")
        print("  1. Create a .env file with DHAN_ACCESS_TOKEN=your_token")
        print("  2. Set environment variable: export DHAN_ACCESS_TOKEN=your_token")
        print("\nSee .env.example for template.")
        return

    print("=" * 60)
    print("Dhan Data Provider Example Strategy")
    print("=" * 60)

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
    adapter = DhanDataAdapter(
        provider,
        datetime_format="%Y-%m-%d %H:%M:%S",
        timezone="UTC",
    )

    # Create strategy and engine
    strategy = DhanExampleStrategy()
    engine = BacktestEngine(adapter, strategy, symbol="RELIANCE")

    try:
        print("\nStarting backtest...")
        engine.run()
        print("\nBacktest completed successfully!")
    except Exception as e:
        print(f"\nError during backtest: {e}")
        import traceback
        traceback.print_exc()
    finally:
        adapter.close()


if __name__ == "__main__":
    main()