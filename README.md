# Quantrex

**Quantrex** is a Python-based event-driven algorithmic trading framework for quantitative researchers.

## Overview

A researcher writes **one simple Python strategy script** and uses the **exact same script** for backtesting, paper/mock trading, and live trading.

## Package Structure

This is a monorepo with the following packages:

| Package | Description |
|---------|-------------|
| `quantrex-data` | Data providers and adapters for market data |
| `quantrex-backtest` | Deterministic event-driven backtest engine |
| `quantrex-test-support` | Test utilities for generating temporary CSV data |

## Quick Start

```python
from quantrex_data.providers.csv_provider import CSVDataProvider
from quantrex_data.adapters.csv_adapter import CSVDataAdapter
from quantrex_backtest import BacktestEngine
from quantrex_test_support.csv import make_ohlc_series, create_temp_csv

# Generate synthetic data
rows = make_ohlc_series(num_rows=10, start_price=737.20, seed=42)
csv_content = csv_rows_to_string(rows)

# Create temporary CSV and configure data pipeline
with create_temp_csv(csv_content) as temp_path:
    provider = CSVDataProvider(temp_path, has_header=False)
    adapter = CSVDataAdapter(
        provider,
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
    engine = BacktestEngine(adapter, symbol="COPPER")
    engine.run(lambda candle: print(candle.timestamp, candle.close))
```

## Precomputed Indicators

Vectorize your indicators in one pass over the full candle history. The engine calls `Strategy.compute_indicators(raw_rows)` exactly once, with the full sorted row sequence, before any `Candle` is constructed. The i-th returned mapping is attached to the i-th `Candle.indicators` and is available inside `on_candle`. The framework is **indicator-implementation agnostic** — no `pandas_ta`, no `pandas`, no `ta-lib` are bundled. Use whatever library you prefer, or pure Python:

```python
from collections.abc import Sequence
from typing import Mapping
from quantrex_core import Strategy, Candle


class SmaCrossover(Strategy):
    def __init__(self, fast: int = 5, slow: int = 20) -> None:
        super().__init__()
        self._fast, self._slow = fast, slow
        self._prev: tuple[float | None, float | None] = (None, None)

    def compute_indicators(
        self, candles: Sequence[Mapping[str, object]],
    ) -> Sequence[Mapping[str, float | None]]:
        closes = [float(r["close"]) for r in candles]
        return [
            {"sma_fast": _sma(closes, self._fast)[i],
             "sma_slow": _sma(closes, self._slow)[i]}
            for i in range(len(closes))
        ]

    def on_candle(self, candle: Candle) -> None:
        fast = candle.indicators["sma_fast"]
        slow = candle.indicators["sma_slow"]
        prev_fast, prev_slow = self._prev
        self._prev = (fast, slow)
        if None in (fast, slow, prev_fast, prev_slow):
            return
        # ...crossover logic on (prev_fast, prev_slow) -> (fast, slow)...
```

The same `Strategy` subclass works across backtest, live, and paper trading because the hook lives on the shared base class. See `examples/sma_crossover_dhan_strategy.py` for a full working example.

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