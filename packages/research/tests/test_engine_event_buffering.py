"""Tests for ResearchEngine - Event buffering."""

from datetime import datetime, timedelta
from unittest.mock import Mock

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig
from quantrex_backtest import InstrumentSpec, BacktestConfig


def test_engine_events_buffered_with_emission_candle():
    """Events buffered with emission candle; horizons tracked per event."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
        {"datetime": "2024-01-01 09:17:00", "open": "102", "high": "103", "low": "101", "close": "102", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    class TestComponent(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.event_emitted = False
        
        def on_candle(self, candle: Candle) -> None:
            if not self.event_emitted:
                self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {"test": True})
                self.event_emitted = True
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = TestComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    # Verify event was buffered with correct emission candle
    # The engine's internal buffer should have the event with the emission candle
    # We can't directly access private _event_buffers, but we can verify
    # the calculation happened correctly
    assert component._series_list
    series = component._series_list[0]
    assert series.returns[timedelta(minutes=1)] == 1.0


def test_engine_multiple_events_buffered_independently():
    """Multiple events buffered independently with their own emission candles."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
        {"datetime": "2024-01-01 09:17:00", "open": "102", "high": "103", "low": "101", "close": "102", "volume": "100"},
        {"datetime": "2024-01-01 09:18:00", "open": "103", "high": "104", "low": "102", "close": "103", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    class TestComponent(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.event_count = 0
        
        def on_candle(self, candle: Candle) -> None:
            if self.event_count < 2:
                self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {"event_num": self.event_count})
                self.event_count += 1
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = TestComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    # Should have 2 events, each with its own calculation
    assert len(component._series_list) == 2
    assert component._series_list[0].returns[timedelta(minutes=1)] == 1.0  # First event: 100->101
    # Second event: 101->102 = (102-101)/101*100 = 0.990099...
    assert abs(component._series_list[1].returns[timedelta(minutes=1)] - 0.990099) < 0.01


def test_engine_horizons_tracked_per_event():
    """Each event tracks its own horizons independently."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
        {"datetime": "2024-01-01 09:17:00", "open": "102", "high": "103", "low": "101", "close": "102", "volume": "100"},
        {"datetime": "2024-01-01 09:18:00", "open": "103", "high": "104", "low": "102", "close": "103", "volume": "100"},
        {"datetime": "2024-01-01 09:19:00", "open": "104", "high": "105", "low": "103", "close": "104", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    class TestComponent(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.event_count = 0
        
        def on_candle(self, candle: Candle) -> None:
            if self.event_count < 2:
                self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {"event_num": self.event_count})
                self.event_count += 1
    
    # Two horizons: 1min and 3min
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1), timedelta(minutes=3)])
    component = TestComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    # Each event should have both horizons calculated
    assert len(component._series_list) == 2
    
    # First event (at 09:15): 1min -> 09:16 (1%), 3min -> 09:18 (3%)
    series1 = component._series_list[0]
    assert series1.returns[timedelta(minutes=1)] == 1.0
    assert series1.returns[timedelta(minutes=3)] == 3.0
    
    # Second event (at 09:16): 1min -> 09:17 (0.99%), 3min -> 09:19 (2.97%)
    series2 = component._series_list[1]
    assert abs(series2.returns[timedelta(minutes=1)] - 0.990099) < 0.01
    assert abs(series2.returns[timedelta(minutes=3)] - 2.970297) < 0.01