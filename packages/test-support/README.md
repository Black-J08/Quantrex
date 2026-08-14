# quantrex-test-support

Test support utilities for the Quantrex project. Currently provides temporary CSV file generation with configurable row counts for testing.

## Installation

This package is part of the Quantrex monorepo and is installed via `uv`:

```bash
uv sync
```

## Usage

### CSV Generation

```python
from quantrex_test_support.csv import (
    make_index_mode_rows,
    make_header_mode_rows,
    csv_rows_to_string,
    create_temp_csv,
    SAMPLE_DATES,
    SAMPLE_TIMES,
    SAMPLE_OHLCV,
    SAMPLE_OI,
)

# Generate index-mode (headerless) CSV rows with configurable row count
rows = make_index_mode_rows(num_rows=100, num_extra_cols=1)
csv_content = csv_rows_to_string(rows)

# Generate header-mode CSV rows
headers = ["timestamp", "open", "high", "low", "close", "volume"]
header_row, data_rows = make_header_mode_rows(headers, num_rows=50)
all_rows = [header_row] + data_rows
csv_content = csv_rows_to_string(all_rows)

# Create temporary CSV file for testing
with create_temp_csv(csv_content) as temp_path:
    # Use temp_path with CSVReader or other tools
    pass
```

### Constants

The package provides consistent test data constants:

- `SAMPLE_DATES`: `["20230620", "20230621", "20230622"]`
- `SAMPLE_TIMES`: `["19:00", "10:06", "15:30"]`
- `SAMPLE_OHLCV`: List of (open, high, low, close, volume) tuples
- `SAMPLE_OI`: `["1", "1", "2"]` (open interest values)

## API Reference

### `make_index_mode_rows(num_rows=3, num_extra_cols=0) -> list[list[str]]`

Generate headerless CSV rows for index mode testing.

**Columns:** date, time, open, high, low, close, volume, [extra...]

**Args:**
- `num_rows`: Number of rows to generate (default: 3)
- `num_extra_cols`: Number of extra columns to add (e.g., open interest)

### `make_header_mode_rows(headers, num_rows=3) -> tuple[list[str], list[list[str]]]`

Generate CSV with header row and data rows for header mode testing.

**Args:**
- `headers`: List of column header names
- `num_rows`: Number of data rows to generate (default: 3)

**Returns:** Tuple of (header_row, data_rows)

### `csv_rows_to_string(rows) -> str`

Convert list of row lists to CSV-formatted string.

### `create_temp_csv(content) -> contextmanager[str]`

Context manager to create a temporary CSV file with given content. Automatically cleans up on exit.

## Development

```bash
# Run tests
uv run pytest packages/test-support/tests/

# Type checking
uv run pyright packages/test-support/src/
```