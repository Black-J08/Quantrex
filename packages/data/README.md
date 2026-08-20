# quantrex-data

Data providers and adapters for the Quantrex framework. Read CSV market data and normalize it for the backtest engine.

## Installation

```bash
uv add quantrex-data
# or from workspace
uv sync
```

## Usage

```python
from quantrex_data.providers.csv_provider import CSVDataProvider
from quantrex_data.adapters.csv_adapter import CSVDataAdapter

# Index mode (headerless CSV)
provider = CSVDataProvider("data.csv", has_header=False)
adapter = CSVDataAdapter(provider, column_mapping={
    "datetime": [0, 1],
    "open": 2, "high": 3, "low": 4, "close": 5,
    "volume": 6, "open_interest": 7,
})
data = adapter.read()
```

## Architecture

- **DataProvider**: Fetches raw data from source (e.g., CSV files)
- **DataAdapter**: Normalizes provider data to engine format

## Modes

- **Index mode**: Column indices (integers), auto-detected
- **Header mode**: Column names (strings), requires CSV with headers

## Output

Returns `list[dict]` with standardized keys: `datetime`, `open`, `high`, `low`, `close`, `volume`.

## Testing

```bash
uv run pytest packages/data/tests/
```