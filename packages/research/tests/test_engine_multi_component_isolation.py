"""Tests for ResearchEngine - Multi-component isolation."""

from datetime import datetime, timedelta
from unittest.mock import Mock

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig
from quantrex_backtest import InstrumentSpec, BacktestConfig


def test_engine_multiple_components_share_candle_stream():
    """Multiple components share same candle stream; independent event buffers."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
        {"datetime": "2024-01-01 09:17:00", "open": "102", "high": "103", "low": "101", "close": "102", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    class ComponentA(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.emitted = False
        
        def on_candle(self, candle: Candle) -> None:
            if not self.emitted:
                self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {"component": "A"})
                self.emitted = True
    
    class ComponentB(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.emitted = False
        
        def on_candle(self, candle: Candle) -> None:
            if not self.emitted:
                self.emit_event(candle.symbol, OrderSide.SELL, candle.timestamp, {"component": "B"})
                self.emitted = True
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    comp_a = ComponentA(config)
    comp_b = ComponentB(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[comp_a, comp_b],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    # Both components should have received all candles
    assert len(comp_a._series_list) == 1
    assert len(comp_b._series_list) == 1
    
    # Component A: BUY event, 1% return
    assert comp_a._series_list[0].event.direction == OrderSide.BUY
    assert comp_a._series_list[0].returns[timedelta(minutes=1)] == 1.0
    
    # Component B: SELL event, 1% return (same calculation, direction doesn't affect return)
    assert comp_b._series_list[0].event.direction == OrderSide.SELL
    assert comp_b._series_list[0].returns[timedelta(minutes=1)] == 1.0


def test_engine_components_independent_event_buffers():
    """Each component has independent event buffer."""
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
    
    class ComponentA(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.count = 0
        
        def on_candle(self, candle: Candle) -> None:
            if self.count < 2:
                self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {"component": "A", "num": self.count})
                self.count += 1
    
    class ComponentB(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.count = 0
        
        def on_candle(self, candle: Candle) -> None:
            if self.count < 1:
                self.emit_event(candle.symbol, OrderSide.SELL, candle.timestamp, {"component": "B", "num": self.count})
                self.count += 1
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    comp_a = ComponentA(config)
    comp_b = ComponentB(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[comp_a, comp_b],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    # Component A emitted 2 events, Component B emitted 1 event
    assert len(comp_a._series_list) == 2
    assert len(comp_b._series_list) == 1
    
    # Each component's events calculated independently
    assert comp_a._series_list[0].returns[timedelta(minutes=1)] == 1.0
    # Second event: 101->102 = (102-101)/101*100 = 0.990099...
    assert abs(comp_a._series_list[1].returns[timedelta(minutes=1)] - 0.990099) < 0.01
    assert comp_b._series_list[0].returns[timedelta(minutes=1)] == 1.0


def test_engine_components_different_horizons():
    """Components can have different horizon configurations."""
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
    
    class ComponentA(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.emitted = False
        
        def on_candle(self, candle: Candle) -> None:
            if not self.emitted:
                self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {"component": "A"})
                self.emitted = True
    
    class ComponentB(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.emitted = False
        
        def on_candle(self, candle: Candle) -> None:
            if not self.emitted:
                self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {"component": "B"})
                self.emitted = True
    
    # Component A: 1min and 2min horizons
    config_a = ForwardReturnConfig(horizons=[timedelta(minutes=1), timedelta(minutes=2)])
    # Component B: 3min and 5min horizons
    config_b = ForwardReturnConfig(horizons=[timedelta(minutes=3), timedelta(minutes=5)])
    
    comp_a = ComponentA(config_a)
    comp_b = ComponentB(config_b)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[comp_a, comp_b],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    # Component A should have 1min and 2min calculated
    assert len(comp_a._series_list) == 1
    assert timedelta(minutes=1) in comp_a._series_list[0].returns
    assert timedelta(minutes=2) in comp_a._series_list[0].returns
    assert timedelta(minutes=3) not in comp_a._series_list[0].returns
    
    # Component B should have 3min and 5min calculated
    assert len(comp_b._series_list) == 1
    assert timedelta(minutes=3) in comp_b._series_list[0].returns
    assert timedelta(minutes=5) in comp_b._series_list[0].returns
    assert timedelta(minutes=1) not in comp_b._series_list[0].returns