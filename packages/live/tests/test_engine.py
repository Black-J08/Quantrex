"""Tests for LiveEngine."""

import pytest
from unittest.mock import Mock
from quantrex_live.core.engine import LiveEngine
from quantrex_core import Strategy, Candle
from quantrex_core.protocols import DataAdapter
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


def _mock_adapter():
    """Create a mock DataAdapter for testing."""
    adapter = Mock(spec=DataAdapter)
    adapter.supported_timeframes = ["1M"]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.read.return_value = []
    adapter.read_timeframe.return_value = []
    return adapter


def test_live_engine_creation():
    """LiveEngine can be instantiated with a strategy and adapter."""
    strategy = TestStrategy()
    adapter = _mock_adapter()
    engine = LiveEngine(strategy, adapter)
    assert engine is not None


def test_live_engine_run_raises_not_implemented():
    """LiveEngine.run raises NotImplementedError after calling on_start."""
    strategy = TestStrategy()
    adapter = _mock_adapter()
    engine = LiveEngine(strategy, adapter)
    
    with pytest.raises(NotImplementedError, match="Live data subscription not yet implemented"):
        engine.run()
    
    # on_start should have been called before the exception
    assert strategy.started is True
    assert strategy.candles_processed == 0
    assert strategy.stopped is False


def test_live_engine_accepts_strategy_in_constructor():
    """LiveEngine accepts a Strategy instance in constructor."""
    strategy = TestStrategy()
    adapter = _mock_adapter()
    engine = LiveEngine(strategy, adapter)
    
    # Should accept the strategy
    assert engine is not None
    
    # Strategy should not have been modified yet
    assert strategy.candles_processed == 0
    assert strategy.started is False
    assert strategy.stopped is False