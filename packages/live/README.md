# quantrex-live

Live trading engine for Quantrex (placeholder implementation).

## Usage

```python
from quantrex_live import LiveEngine
from quantrex_core import Strategy, Candle


class MyStrategy(Strategy):
    def on_candle(self, candle: Candle) -> None:
        print(f"Live: {candle.timestamp} - Close: {candle.close}")


strategy = MyStrategy()
engine = LiveEngine(strategy)
engine.run()  # Raises NotImplementedError - live engine not yet implemented
```

## API

### `LiveEngine(strategy)`

- `strategy`: Strategy instance to execute

### `engine.run()`

Executes the live trading loop (placeholder):
1. Calls `strategy.on_start()`
2. Raises `NotImplementedError` - live engine not yet implemented
3. Would call `strategy.on_candle(candle)` for each live candle
4. Would call `strategy.on_stop()` on shutdown