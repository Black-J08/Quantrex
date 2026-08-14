# quantrex-test-support

Test support utilities for generating temporary CSV data.

## Installation

```bash
uv sync
# or install individually: uv add quantrex-test-support
```

## Usage

```python
from quantrex_test_support.csv import make_ohlc_series, create_temp_csv, csv_rows_to_string

# Generate synthetic OHLC data
rows = make_ohlc_series(num_rows=10, start_price=737.20, seed=42)
csv_content = csv_rows_to_string(rows)

# Create temporary CSV file
with create_temp_csv(csv_content) as temp_path:
    # Use temp_path with CSVReader or BacktestEngine
    pass
```

## API

- `make_ohlc_series(num_rows, start_price, seed)` - Generate OHLC series
- `create_temp_csv(content)` - Create temporary CSV file (auto-cleanup)
- `csv_rows_to_string(rows)` - Convert rows to CSV string

## Testing

```bash
uv run pytest packages/test-support/tests/
```