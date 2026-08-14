"""Minimal example strategy demonstrating the Quantrex researcher workflow.

One script works for backtesting, paper trading, and live trading.
This version uses synthetic data generated via quantrex-test-support helpers.
"""

from quantrex_data.providers.csv_reader import CSVReader
from quantrex_backtest import BacktestEngine, Candle
from quantrex_test_support.csv import make_ohlc_series, csv_rows_to_string, create_temp_csv


def strategy(candle: Candle) -> None:
    """Strategy logic: print each candle (replace with your logic)."""
    print(f"{candle.timestamp} | {candle.symbol} | O:{candle.open} H:{candle.high} L:{candle.low} C:{candle.close} V:{candle.volume}")


if __name__ == "__main__":
    # 1. Generate synthetic OHLC data using test-support helpers
    rows = make_ohlc_series(num_rows=10, start_price=737.20, seed=42)
    csv_content = csv_rows_to_string(rows)

    # 2. Create temporary CSV file and configure data source
    with create_temp_csv(csv_content) as temp_path:
        reader = CSVReader(
            temp_path,
            column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            },
        )

        # 3. Create engine with data feeder
        engine = BacktestEngine(reader, symbol="COPPER")

        # 4. Run backtest - engine calls strategy(candle) for each candle in timestamp order
        engine.run(strategy)