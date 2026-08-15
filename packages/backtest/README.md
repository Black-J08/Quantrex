# quantrex-backtest

Deterministic event-driven backtest engine for Quantrex.

## Usage

```python
from quantrex_data.providers.csv_reader import CSVReader
from quantrex_backtest import BacktestEngine
from quantrex_core import Strategy, Candle


class MyStrategy(Strategy):
    def on_candle(self, candle: Candle) -> None:
        print(f"{candle.timestamp} - Close: {candle.close}")


reader = CSVReader("data.csv", mapping={...})
strategy = MyStrategy()
engine = BacktestEngine(reader, strategy, symbol="COPPER")
engine.run()
```

## API

### `BacktestEngine(feeder, strategy, symbol="", datetime_format="%Y%m%d %H:%M")`

- `feeder`: DataFeeder instance providing candle data via `read()`
- `strategy`: Strategy instance to execute
- `symbol`: Trading symbol for the candles (optional)
- `datetime_format`: Format string for parsing datetime from feeder data (optional)

### `engine.run()`

Executes the backtest:
1. Calls `strategy.on_start()`
2. For each candle from feeder (sorted by timestamp): calls `strategy.on_candle(candle)`
3. Calls `strategy.on_stop()`

## Installation

```bash
uv add quantrex-backtest
# or from workspace: uv sync
```

## Error Handling

- `ProviderError`: Raised when feeder is None, strategy is None, or feeder.read() fails
- Malformed rows are skipped with WARNING logs (via loguru)

## Testing

```bash
uv run pytest packages/backtest/tests/
```