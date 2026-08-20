# quantrex-backtest

Deterministic event-driven backtest engine for Quantrex.

## Usage

```python
from quantrex_data.providers.csv_provider import CSVDataProvider
from quantrex_data.adapters.csv_adapter import CSVDataAdapter
from quantrex_backtest import BacktestEngine
from quantrex_core import Strategy, Candle


class MyStrategy(Strategy):
    def on_candle(self, candle: Candle) -> None:
        print(f"{candle.timestamp} - Close: {candle.close}")


provider = CSVDataProvider("data.csv", has_header=False)
adapter = CSVDataAdapter(provider, column_mapping={...})
strategy = MyStrategy()
engine = BacktestEngine(adapter, strategy, symbol="COPPER")
engine.run()
```

## API

### `BacktestEngine(adapter, strategy, symbol="", datetime_format="%Y%m%d %H:%M")`

- `adapter`: DataAdapter instance providing normalized candle data via `read()`
- `strategy`: Strategy instance to execute
- `symbol`: Trading symbol for the candles (optional)
- `datetime_format`: Format string for parsing datetime from adapter data (optional)

### `engine.run()`

Executes the backtest:
1. Calls `strategy.on_start()`
2. For each candle from adapter (sorted by timestamp): calls `strategy.on_candle(candle)`
3. Calls `strategy.on_stop()`

## Installation

```bash
uv add quantrex-backtest
# or from workspace: uv sync
```

## Error Handling

- `ProviderError`: Raised when adapter is None, strategy is None, or adapter.read() fails
- Malformed rows are skipped with WARNING logs (via loguru)

## Testing

```bash
uv run pytest packages/backtest/tests/
```