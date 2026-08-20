"""Example strategy demonstrating the new StrategyContext API.

One script works for backtesting, paper trading, and live trading.
This version uses the new DataProvider → DataAdapter pattern.
"""

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.strategy.base import Strategy
from quantrex_data.providers.csv_provider import CSVDataProvider
from quantrex_data.adapters.csv_adapter import CSVDataAdapter
from quantrex_backtest import BacktestEngine
from quantrex_test_support.csv import make_ohlc_series, csv_rows_to_string, create_temp_csv


class MyStrategy(Strategy):
    """Example strategy that buys when close > open and reports position."""

    def on_candle(self, candle: Candle) -> None:
        """Simple logic: if candle is bullish, buy 10 units."""
        if candle.close > candle.open:
            # Submit a market buy order for 10 units
            order = self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.BUY,
                quantity=10.0
            )
            print(f"[{candle.timestamp}] Submitted BUY 10 {candle.symbol} -> Order {order.id} ({order.status})")
        
        # Always report current position
        position = self.ctx.get_position(candle.symbol)
        print(f"[{candle.timestamp}] Position for {candle.symbol}: {position.quantity}")


if __name__ == "__main__":
    # 1. Generate synthetic OHLC data using test-support helpers
    rows = make_ohlc_series(num_rows=10, start_price=737.20, seed=42)
    csv_content = csv_rows_to_string(rows)

    # 2. Create temporary CSV file and configure data source using new pattern
    with create_temp_csv(csv_content) as temp_path:
        provider = CSVDataProvider(temp_path, has_header=False)
        adapter = CSVDataAdapter(
            provider,
            column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            },
        )

        # 3. Create engine with data adapter and strategy instance
        strategy = MyStrategy()
        engine = BacktestEngine(adapter, strategy, symbol="COPPER")

        # 4. Run backtest - engine will call strategy.on_start(), on_candle(), on_stop()
        engine.run()