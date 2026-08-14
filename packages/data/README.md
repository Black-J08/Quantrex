# quantrex-data

Data providers for the Quantrex framework. Read CSV market data in index or header mode.

## Installation

```bash
uv add quantrex-data
# or from workspace
uv sync
```

## Usage

```python
from quantrex_data.providers.csv_reader import CSVReader

# Index mode (headerless CSV)
reader = CSVReader("data.csv", {
    "datetime": [0, 1],
    "open": 2, "high": 3, "low": 4, "close": 5,
    "volume": 6, "open_interest": 7,
})
data = reader.read()
```

## Modes

- **Index mode**: Column indices (integers), auto-detected
- **Header mode**: Column names (strings), requires CSV with headers

## Output

Returns `list[dict]` with mapped keys.

## Testing

```bash
uv run pytest tests/
```