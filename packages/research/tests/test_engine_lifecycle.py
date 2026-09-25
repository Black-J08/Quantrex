"""Tests for ResearchEngine - Lifecycle."""

from datetime import datetime, timedelta
from unittest.mock import Mock

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig
from quantrex_backtest import InstrumentSpec, BacktestConfig


class LifecycleComponent(ForwardReturnComponent):
    """Component that tracks lifecycle calls."""
    
    def __init__(self, config):
        super().__init__(config)
        self.started = False
        self.stopped = False
        self.candles_processed = 0
    
    def on_start(self) -> None:
        self.started = True
        super().on_start()
    
    def on_candle(self, candle: Candle) -> None:
        self.candles_processed += 1
    
    def on_stop(self, output_dir) -> None:
        self.stopped = True
        return super().on_stop(output_dir)


def test_engine_calls_lifecycle_methods():
    """Engine should call on_start before and on_stop after processing."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = LifecycleComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    assert component.started is True
    assert component.stopped is True
    assert component.candles_processed == 2


def test_engine_on_start_before_first_candle():
    """on_start should be called before any on_candle."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    call_order = []
    
    class OrderComponent(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
        
        def on_start(self) -> None:
            call_order.append("on_start")
            super().on_start()
        
        def on_candle(self, candle: Candle) -> None:
            call_order.append("on_candle")
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = OrderComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    assert call_order == ["on_start", "on_candle"]


def test_engine_on_stop_after_last_candle():
    """on_stop should be called after all on_candle calls."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    call_order = []
    
    class OrderComponent(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
        
        def on_candle(self, candle: Candle) -> None:
            call_order.append("on_candle")
        
        def on_stop(self, output_dir) -> None:
            call_order.append("on_stop")
            return super().on_stop(output_dir)
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = OrderComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    assert call_order == ["on_candle", "on_candle", "on_stop"]