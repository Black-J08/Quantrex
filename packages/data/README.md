# Quantrex Data

Data providers package for the Quantrex algorithmic trading framework.

## Installation

```bash
uv add quantrex-data
```

Or from the workspace:

```bash
uv sync
```

## Usage

```python
from quantrex_data.providers.csv_reader import CSVReader

# Index mode (headerless CSV)
reader = CSVReader(
    "data/COPPER23AUGFUT.csv",
    column_mapping={
        "datetime": [0, 1],  # date + time columns
        "open": 2,
        "high": 3,
        "low": 4,
        "close": 5,
        "volume": 6,
    }
)

# Header mode (CSV with headers)
reader = CSVReader(
    "data/ohlcv.csv",
    column_mapping={
        "datetime": "timestamp",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
    }
)
```

## Column Mapping

The `column_mapping` parameter supports two modes:

### Index Mode (headerless CSVs)
Values are integers (column indices) or lists of integers:
```python
{
    "datetime": [0, 1],  # Join columns 0 and 1
    "open": 2,
    "high": 3,
    "low": 4,
    "close": 5,
    "volume": 6,
    "open_interest": 7,  # Additional fields supported
}
```

### Header Mode (CSVs with headers)
Values are strings (header names) or lists of strings:
```python
{
    "datetime": ["date", "time"],  # Join multiple headers
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
}
```

The mode is auto-detected from the mapping value types.

## Output Format

Returns `list[dict]` with keys matching the mapping:
```python
[
    {
        "datetime": "20230620 19:00",
        "open": "737.20",
        "high": "737.20",
        "low": "737.20",
        "close": "737.20",
        "volume": "1",
    },
    ...
]
```

## Error Handling

- Malformed rows are skipped with a `WARNING` log (via loguru)
- Invalid mappings raise `ValueError` with descriptive messages
- Missing headers or out-of-bounds indices raise appropriate exceptions

## Testing

```bash
uv run pytest tests/
```