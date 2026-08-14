# quantrex-backtest

Deterministic event-driven backtest engine for the Quantrex framework.

## Installation

```bash
uv add quantrex-backtest
# or from workspace: uv sync
```

## Quick Start

```python
from quantrex_data.providers.csv_reader import CSVReader
from quantrex_backtest import BacktestEngine, Candle

# Read CSV data
reader = CSVReader("data.csv", {
    "datetime": [0, 1],
    "open": 2, "high": 3, "low": 4, "close": 5,
    "volume": 6,
})

# Initialize engine
engine = BacktestEngine(reader, symbol="COPPER")

# Run strategy
engine.run(lambda candle: print(f"{candle.timestamp} | {candle.close}"))
```

## API

### `BacktestEngine(feeder, symbol="", datetime_format="%Y%m%d %H:%M")`

- `feeder`: DataFeeder providing candle data via `read()`
- `symbol`: Trading symbol (e.g., "COPPER")
- `datetime_format`: Format string for parsing timestamps

### `engine.run(on_candle)`

- `on_candle`: Callback receiving each `Candle` sequentially
- Candles are processed in timestamp order

### `Candle` data model

Immutable dataclass with attributes: `symbol`, `timestamp`, `open`, `high`, `low`, `close`, `volume`

## Error Handling

- `ProviderError`: Raised when feeder is None or feeder.read() fails
- Malformed rows are skipped with WARNING logs (via loguru)

## Testing

```bash
uv run pytest packages/backtest/tests/
```