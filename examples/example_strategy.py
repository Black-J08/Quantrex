"""Minimal example strategy demonstrating the Quantrex researcher workflow.

One script works for backtesting, paper trading, and live trading.
"""

from quantrex_data.providers.csv_reader import CSVReader
from quantrex_backtest import BacktestEngine, Candle


def strategy(candle: Candle) -> None:
    """Strategy logic: print each candle (replace with your logic)."""
    print(f"{candle.timestamp} | {candle.symbol} | O:{candle.open} H:{candle.high} L:{candle.low} C:{candle.close} V:{candle.volume}")


if __name__ == "__main__":
    # 1. Configure data source (CSVReader implements DataFeeder protocol)
    reader = CSVReader(
        "example_csv_data/COPPER23AUGFUT.csv",
        column_mapping={
            "datetime": [0, 1],
            "open": 2,
            "high": 3,
            "low": 4,
            "close": 5,
            "volume": 6,
        },
    )

    # 2. Create engine with data feeder
    engine = BacktestEngine(reader, symbol="COPPER")

    # 3. Run backtest - engine calls strategy(candle) for each candle in timestamp order
    engine.run(strategy)