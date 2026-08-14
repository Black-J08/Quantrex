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
    
    def on_candle(self, candle: Candle) -> None:
        self.candles_processed += 1


def test_live_engine_creation():
    """LiveEngine can be instantiated."""
    engine = LiveEngine()
    assert engine is not None


def test_live_engine_run_raises_not_implemented():
    """LiveEngine.run raises NotImplementedError."""
    engine = LiveEngine()
    strategy = TestStrategy()
    
    with pytest.raises(NotImplementedError, match="Live engine not yet implemented"):
        engine.run(strategy)


def test_live_engine_accepts_strategy():
    """LiveEngine.run accepts a Strategy instance."""
    engine = LiveEngine()
    strategy = TestStrategy()
    
    # Should accept the strategy (even though it raises NotImplementedError)
    try:
        engine.run(strategy)
    except NotImplementedError:
        pass  # Expected
    
    # Strategy should not have been modified
    assert strategy.candles_processed == 0