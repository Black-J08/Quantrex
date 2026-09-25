"""Tests for ResearchEngine - Empty data handling."""

from datetime import datetime, timedelta
from unittest.mock import Mock

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig
from quantrex_backtest import InstrumentSpec, BacktestConfig


class RecordingComponent(ForwardReturnComponent):
    """Component that records received candles."""
    
    def __init__(self, config):
        super().__init__(config)
        self.candles = []
        self.started = False
        self.stopped = False
    
    def on_start(self) -> None:
        self.started = True
        super().on_start()
    
    def on_candle(self, candle: Candle) -> None:
        self.candles.append(candle)
    
    def on_stop(self, output_dir) -> None:
        self.stopped = True
        return super().on_stop(output_dir)


def test_engine_handles_empty_data():
    """Engine should handle empty data gracefully."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = []
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = RecordingComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    results = engine.run()
    
    assert component.started is True
    assert component.stopped is True
    assert len(component.candles) == 0
    # Engine now returns results even for empty data (components still run on_start/on_stop)
    assert "RecordingComponent" in results
    assert results["RecordingComponent"].horizon_stats == {}
    assert results["RecordingComponent"].raw_returns == {}


def test_engine_handles_empty_data_multiple_symbols():
    """Engine should handle empty data for multiple symbols."""
    adapter1 = Mock(spec=DataAdapter)
    adapter1.read_timeframe.return_value = []
    adapter1.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter1.supported_timeframes = ["1M"]
    adapter1.get_origin_time.return_value = None
    
    adapter2 = Mock(spec=DataAdapter)
    adapter2.read_timeframe.return_value = []
    adapter2.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter2.supported_timeframes = ["1M"]
    adapter2.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = RecordingComponent(config)
    
    engine = ResearchEngine(
        instruments=[
            InstrumentSpec(symbol="SYM1", adapter=adapter1),
            InstrumentSpec(symbol="SYM2", adapter=adapter2),
        ],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    results = engine.run()
    
    assert component.started is True
    assert component.stopped is True
    assert len(component.candles) == 0
    # Engine now returns results even for empty data
    assert "RecordingComponent" in results
    assert results["RecordingComponent"].horizon_stats == {}
    assert results["RecordingComponent"].raw_returns == {}


def test_engine_handles_one_symbol_empty():
    """Engine should handle one symbol with data, one without."""
    adapter1 = Mock(spec=DataAdapter)
    adapter1.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
    ]
    adapter1.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter1.supported_timeframes = ["1M"]
    adapter1.get_origin_time.return_value = None
    
    adapter2 = Mock(spec=DataAdapter)
    adapter2.read_timeframe.return_value = []
    adapter2.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter2.supported_timeframes = ["1M"]
    adapter2.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = RecordingComponent(config)
    
    engine = ResearchEngine(
        instruments=[
            InstrumentSpec(symbol="SYM1", adapter=adapter1),
            InstrumentSpec(symbol="SYM2", adapter=adapter2),
        ],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    results = engine.run()
    
    assert component.started is True
    assert component.stopped is True
    assert len(component.candles) == 1
    assert component.candles[0].symbol == "SYM1"