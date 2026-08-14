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