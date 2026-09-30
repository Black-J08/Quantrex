"""Regression tests for timeframe event emission with correct emission candle."""

from datetime import datetime, timedelta
from unittest.mock import Mock

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter
from quantrex_core.strategy.timeframe import on_timeframe

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig
from quantrex_backtest import InstrumentSpec, BacktestConfig


class TimeframeEmissionComponent(ForwardReturnComponent):
    """Component that emits events from @on_timeframe callback."""
    
    def __init__(self, config):
        super().__init__(config)
        self.emitted_events = []
        self.emission_candles = []
    
    def compute_indicators(self, candles, timeframe: str = "1M", symbol: str | None = None):
        return [{} for _ in candles]
    
    def on_candle(self, candle: Candle) -> None:
        pass
    
    @on_timeframe("5M")
    def on_5min_candle(self, candle: Candle):
        """Called by dispatcher for 5M timeframe."""
        # Emit event with the 5M candle as emission_candle
        self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, 
                       {"timeframe": "5M"}, emission_candle=candle)
    
    def on_returns_calculated(self, event, series):
        self.emitted_events.append(event)
        self.emission_candles.append(event.candle)
    
    def on_stop(self, output_dir):
        return {"emitted_events": len(self.emitted_events)}


def test_timeframe_emission_uses_correct_emission_candle():
    """Events emitted from @on_timeframe should use the higher timeframe candle as emission_candle."""
    adapter = Mock(spec=DataAdapter)
    # Provide 1M base data - need 6 minutes to complete one 5M bucket (9:15-9:20)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
        {"datetime": "2024-01-01 09:17:00", "open": "102", "high": "103", "low": "101", "close": "102", "volume": "100"},
        {"datetime": "2024-01-01 09:18:00", "open": "103", "high": "104", "low": "102", "close": "103", "volume": "100"},
        {"datetime": "2024-01-01 09:19:00", "open": "104", "high": "105", "low": "103", "close": "104", "volume": "100"},
        {"datetime": "2024-01-01 09:20:00", "open": "105", "high": "106", "low": "104", "close": "105", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]  # Only 1M native, 5M will be derived
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=5)])
    component = TimeframeEmissionComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    # Verify event was emitted with 5M candle as emission_candle
    # The 5M candle at 9:15 should have close_time 9:20
    assert len(component.emitted_events) > 0, "Should have emitted at least one event"
    
    for event, emission_candle in zip(component.emitted_events, component.emission_candles):
        # Emission candle should be the 5M candle (timeframe="5M")
        assert emission_candle.timeframe == "5M", \
            f"Expected emission_candle timeframe='5M', got '{emission_candle.timeframe}'"
        # Emission candle should have 5-minute duration
        assert (emission_candle.close_time - emission_candle.timestamp) == timedelta(minutes=5), \
            f"Expected 5M candle duration, got {emission_candle.close_time - emission_candle.timestamp}"


def test_timeframe_emission_without_emission_candle_uses_base():
    """Events emitted without explicit emission_candle should use base timeframe candle."""
    
    class BaseEmissionComponent(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.emission_candles = []
        
        def compute_indicators(self, candles, timeframe: str = "1M", symbol: str | None = None):
            return [{} for _ in candles]
        
        def on_candle(self, candle: Candle):
            # Emit from base on_candle without emission_candle
            self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {})
        
        def on_returns_calculated(self, event, series):
            self.emission_candles.append(event.candle)
        
        def on_stop(self, output_dir):
            return {}
    
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = BaseEmissionComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    # Emission candle should be base 1M candle
    assert len(component.emission_candles) > 0
    for emission_candle in component.emission_candles:
        assert emission_candle.timeframe == "1M", \
            f"Expected base emission_candle timeframe='1M', got '{emission_candle.timeframe}'"