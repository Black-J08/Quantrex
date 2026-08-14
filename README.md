# Quantrex

**Quantrex** is a Python-based event-driven algorithmic trading framework for quantitative researchers.

## Overview

A researcher writes **one simple Python strategy script** and uses the **exact same script** for backtesting, paper/mock trading, and live trading.

## Package Structure

This is a monorepo with the following packages:

| Package | Description |
|---------|-------------|
| `quantrex-data` | Data providers for reading CSV market data |
| `quantrex-backtest` | Deterministic event-driven backtest engine |
| `quantrex-test-support` | Test utilities for generating temporary CSV data |

## Quick Start

```python
from quantrex_data.providers.csv_reader import CSVReader
from quantrex_backtest import BacktestEngine
from quantrex_test_support.csv import make_ohlc_series, create_temp_csv

# Generate synthetic data
rows = make_ohlc_series(num_rows=10, start_price=737.20, seed=42)
csv_content = csv_rows_to_string(rows)

# Create temporary CSV and configure reader
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

    # Run backtest
    engine = BacktestEngine(reader, symbol="COPPER")
    engine.run(lambda candle: print(candle.timestamp, candle.close))
```

## Setup

```bash
# Install all packages from workspace
uv sync

# Or install individual packages
uv add quantrex-data
uv add quantrex-backtest
uv add quantrex-test-support
```

## Documentation

- `packages/data/README.md` - quantrex-data package
- `packages/backtest/README.md` - quantrex-backtest package
- `packages/test-support/README.md` - quantrex-test-support package