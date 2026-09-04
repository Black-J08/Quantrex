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
2. Reads and sorts raw data by datetime
3. Calls `strategy.compute_indicators(raw_data)` exactly once (see Precomputed Indicators below)
4. For each candle (with precomputed indicators attached): calls `strategy.on_candle(candle)`
5. Calls `strategy.on_stop()`

## Precomputed Indicators

The engine exposes a single hook, `Strategy.compute_indicators(candles)`, called once with the full timestamp-sorted raw row sequence **before** any `Candle` is constructed. Return a `list[dict]` aligned by index; the engine attaches the i-th mapping to the i-th `Candle.indicators` and makes it available inside `on_candle`.

The framework is **indicator-implementation agnostic**: it bundles no indicator library (no `pandas_ta`, `pandas`, or `ta-lib`). The hook receives `Sequence[Mapping[str, object]]` — list of dicts with string keys — which is the canonical pandas DataFrame input shape (`pd.DataFrame(rows)`), but you can also use polars, numpy, or pure Python. The contract is:

- **Input:** full sorted row sequence (same shape `adapter.read()` returns)
- **Output:** sequence of mappings, one per bar, aligned by index; values must be `float | int | None`
- **Warmup bars:** return `None` for any indicator that is not yet defined

```python
from collections.abc import Sequence
from typing import Mapping
from quantrex_core import Strategy, Candle


class MyStrategy(Strategy):
    def compute_indicators(
        self, candles: Sequence[Mapping[str, object]],
    ) -> Sequence[Mapping[str, float | None]]:
        closes = [float(r["close"]) for r in candles]
        # ...any vectorized library goes here...
        return [{"sma20": s} for s in _sma(closes, 20)]

    def on_candle(self, candle: Candle) -> None:
        sma = candle.indicators.get("sma20")
        if sma is None:
            return  # warmup
        # ...use sma in trading logic...
```

Errors raised in `compute_indicators` (or a length mismatch between the returned sequence and the input) are wrapped as `ProviderError` with a full stack trace. The same `Strategy` subclass works unchanged across backtest, live, and paper trading because the hook lives on the shared `quantrex_core.strategy.base.Strategy` base class.

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