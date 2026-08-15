"""Tests for LiveEngine placeholder."""

import pytest
from quantrex_live.core.engine import LiveEngine
from quantrex_core import Strategy, Candle
from datetime import datetime


class TestStrategy(Strategy):
    """Test strategy for live engine."""
    
    def __init__(self):
        super().__init__()
        self.candles_processed = 0
        self.started = False
        self.stopped = False
    
    def on_start(self) -> None:
        self.started = True
    
    def on_candle(self, candle: Candle) -> None:
        self.candles_processed += 1
    
    def on_stop(self) -> None:
        self.stopped = True


def test_live_engine_creation():
    """LiveEngine can be instantiated with a strategy."""
    strategy = TestStrategy()
    engine = LiveEngine(strategy)
    assert engine is not None


def test_live_engine_run_raises_not_implemented():
    """LiveEngine.run raises NotImplementedError after calling on_start."""
    strategy = TestStrategy()
    engine = LiveEngine(strategy)
    
    with pytest.raises(NotImplementedError, match="Live engine not yet implemented"):
        engine.run()
    
    # on_start should have been called before the exception
    assert strategy.started is True
    assert strategy.candles_processed == 0
    assert strategy.stopped is False


def test_live_engine_accepts_strategy_in_constructor():
    """LiveEngine accepts a Strategy instance in constructor."""
    strategy = TestStrategy()
    engine = LiveEngine(strategy)
    
    # Should accept the strategy
    assert engine is not None
    
    # Strategy should not have been modified yet
    assert strategy.candles_processed == 0
    assert strategy.started is False
    assert strategy.stopped is False