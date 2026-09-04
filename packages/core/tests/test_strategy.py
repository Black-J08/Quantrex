"""Tests for Strategy base class."""

import pytest
from quantrex_core import Strategy, Candle
from datetime import datetime


class ConcreteStrategy(Strategy):
    """Concrete strategy for testing."""
    
    def __init__(self):
        super().__init__()
        self.candles_processed = 0
        self.started = False
        self.stopped = False
    
    def on_candle(self, candle: Candle) -> None:
        self.candles_processed += 1
    
    def on_start(self) -> None:
        self.started = True
    
    def on_stop(self) -> None:
        self.stopped = True


def test_strategy_is_abstract():
    """Strategy base class cannot be instantiated directly."""
    with pytest.raises(TypeError):
        Strategy()


def test_concrete_strategy_can_be_instantiated():
    """Concrete strategy can be instantiated."""
    strategy = ConcreteStrategy()
    assert strategy is not None
    assert strategy.candles_processed == 0
    assert strategy.started is False
    assert strategy.stopped is False


def test_on_candle_is_called():
    """on_candle method is called for each candle."""
    strategy = ConcreteStrategy()
    candle = Candle(
        symbol="TEST",
        timestamp=datetime.now(),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000
    )
    
    strategy.on_candle(candle)
    assert strategy.candles_processed == 1
    
    strategy.on_candle(candle)
    assert strategy.candles_processed == 2


def test_lifecycle_hooks():
    """on_start and on_stop lifecycle hooks work."""
    strategy = ConcreteStrategy()
    
    strategy.on_start()
    assert strategy.started is True
    
    strategy.on_stop()
    assert strategy.stopped is True


def test_strategy_maintains_state():
    """Strategy maintains internal state between calls."""
    strategy = ConcreteStrategy()
    
    # Process multiple candles
    for i in range(5):
        candle = Candle(
            symbol="TEST",
            timestamp=datetime.now(),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000
        )
        strategy.on_candle(candle)
    
    assert strategy.candles_processed == 5


def test_strategy_can_override_lifecycle():
    """Strategy can override lifecycle hooks with custom behavior."""
    
    class CustomLifecycleStrategy(Strategy):
        def __init__(self):
            super().__init__()
            self.start_data = None
            self.stop_data = None
        
        def on_candle(self, candle: Candle) -> None:
            pass
        
        def on_start(self) -> None:
            self.start_data = "initialized"
        
        def on_stop(self) -> None:
            self.stop_data = "cleaned_up"
    
    strategy = CustomLifecycleStrategy()
    strategy.on_start()
    strategy.on_stop()

    assert strategy.start_data == "initialized"
    assert strategy.stop_data == "cleaned_up"


# ---------------------------------------------------------------------------
# Regression tests for the precomputed indicator API
# (Strategy.compute_indicators). A bug fix without a regression test is not
# a fix — see project AGENTS.md "Standing Rule: Regression Tests for Every
# Bug Fix".
# ---------------------------------------------------------------------------


def test_default_compute_indicators_returns_one_dict_per_row():
    """The default ``compute_indicators`` returns one mapping per input row.

    Regression: the engine calls ``strategy.compute_indicators(raw_data)``
    exactly once before the per-bar loop and threads the i-th element into
    the i-th ``Candle``. The default body must be length-aligned with the
    input so the engine's ``len(per_bar) == len(raw_data)`` check passes
    for every existing strategy that does not override the hook.
    """
    strategy = ConcreteStrategy()
    rows = [
        {"datetime": "20230101 09:30", "open": 1, "high": 2, "low": 0, "close": 1, "volume": 1},
        {"datetime": "20230101 09:31", "open": 2, "high": 3, "low": 1, "close": 2, "volume": 2},
        {"datetime": "20230101 09:32", "open": 3, "high": 4, "low": 2, "close": 3, "volume": 3},
    ]

    out = strategy.compute_indicators(rows)

    assert len(out) == 3


def test_default_compute_indicators_each_dict_is_empty():
    """The default per-bar mapping is an empty dict (no-op behavior).

    Regression: the default must not pre-populate indicator values
    (researchers who want pass-through write their own override).
    """
    strategy = ConcreteStrategy()
    rows = [
        {"datetime": "t1", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
        {"datetime": "t2", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 2},
    ]

    out = strategy.compute_indicators(rows)

    assert all(d == {} for d in out)


def test_strategy_can_override_compute_indicators():
    """A subclass can override ``compute_indicators`` to return per-bar values.

    Regression: the hook must be overridable on the shared base class so
    the same ``Strategy`` subclass works across backtest / live / paper
    without modification. Verified by passing through a simple hand-rolled
    "indicator" (``close - open``) to keep the test library-free — the
    framework is indicator-implementation agnostic, so the test does not
    import pandas / polars / ta-lib.
    """
    class SpreadStrategy(ConcreteStrategy):
        def compute_indicators(self, candles):
            return [
                {"spread": float(c["close"]) - float(c["open"])}
                for c in candles
            ]

    rows = [
        {"datetime": "20230101 09:30", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1},
        {"datetime": "20230101 09:31", "open": 2.0, "high": 2.5, "low": 1.5, "close": 2.25, "volume": 2},
    ]

    out = SpreadStrategy().compute_indicators(rows)

    assert out[0]["spread"] == 0.5
    assert out[1]["spread"] == 0.25