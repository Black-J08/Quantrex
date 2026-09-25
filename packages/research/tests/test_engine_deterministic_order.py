"""Tests for ResearchEngine - Deterministic order."""

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
    
    def on_candle(self, candle: Candle) -> None:
        self.candles.append(candle)


def test_engine_deterministic_order():
    """Engine should produce identical callback sequence on repeated runs."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:17:00", "open": "102", "high": "103", "low": "101", "close": "102", "volume": "100"},
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    
    # Run 1
    component1 = RecordingComponent(config)
    engine1 = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component1],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    engine1.run()
    run1_timestamps = [c.timestamp for c in component1.candles]
    
    # Run 2
    component2 = RecordingComponent(config)
    engine2 = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component2],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    engine2.run()
    run2_timestamps = [c.timestamp for c in component2.candles]
    
    assert run1_timestamps == run2_timestamps
    assert run1_timestamps == [
        datetime(2024, 1, 1, 9, 15),
        datetime(2024, 1, 1, 9, 16),
        datetime(2024, 1, 1, 9, 17),
    ]


def test_engine_deterministic_multi_symbol():
    """Engine should produce identical order for multi-symbol runs."""
    adapter1 = Mock(spec=DataAdapter)
    adapter1.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
    ]
    adapter1.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter1.supported_timeframes = ["1M"]
    adapter1.get_origin_time.return_value = None
    
    adapter2 = Mock(spec=DataAdapter)
    adapter2.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:30", "open": "200", "high": "201", "low": "199", "close": "200", "volume": "200"},
    ]
    adapter2.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter2.supported_timeframes = ["1M"]
    adapter2.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    
    # Run 1
    component1 = RecordingComponent(config)
    engine1 = ResearchEngine(
        instruments=[
            InstrumentSpec(symbol="SYM1", adapter=adapter1),
            InstrumentSpec(symbol="SYM2", adapter=adapter2),
        ],
        research_components=[component1],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    engine1.run()
    run1_timestamps = [c.timestamp for c in component1.candles]
    
    # Run 2
    component2 = RecordingComponent(config)
    engine2 = ResearchEngine(
        instruments=[
            InstrumentSpec(symbol="SYM1", adapter=adapter1),
            InstrumentSpec(symbol="SYM2", adapter=adapter2),
        ],
        research_components=[component2],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    engine2.run()
    run2_timestamps = [c.timestamp for c in component2.candles]
    
    assert run1_timestamps == run2_timestamps
    assert run1_timestamps == [
        datetime(2024, 1, 1, 9, 15),
        datetime(2024, 1, 1, 9, 15, 30),
        datetime(2024, 1, 1, 9, 16),
    ]