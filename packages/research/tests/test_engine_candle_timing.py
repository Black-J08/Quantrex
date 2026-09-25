"""Tests for ResearchEngine - Candle timing (timestamp, close_time, timeframe)."""

from datetime import datetime, timedelta
from unittest.mock import Mock

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig
from quantrex_backtest import InstrumentSpec, BacktestConfig


class CandleTimingComponent(ForwardReturnComponent):
    """Component that validates candle timing."""
    
    def __init__(self, config):
        super().__init__(config)
        self.candles = []
    
    def on_candle(self, candle: Candle) -> None:
        self.candles.append(candle)


def test_engine_candle_timestamp_is_open_time():
    """Candle.timestamp should be the open time."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = CandleTimingComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    assert len(component.candles) == 1
    candle = component.candles[0]
    assert candle.timestamp == datetime(2024, 1, 1, 9, 15, 0)


def test_engine_candle_close_time_is_timestamp_plus_timeframe():
    """Candle.close_time should equal timestamp + timeframe duration."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = CandleTimingComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    for candle in component.candles:
        # close_time should be timestamp + 1 minute (for 1M timeframe)
        expected_close = candle.timestamp + timedelta(minutes=1)
        assert candle.close_time == expected_close, f"close_time {candle.close_time} != {expected_close}"
        assert candle.timeframe == "1M"


def test_engine_candle_timeframe_preserved():
    """Candle.timeframe should be preserved from data source."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = CandleTimingComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    assert len(component.candles) == 1
    assert component.candles[0].timeframe == "1M"


def test_engine_candle_validation_in_post_init():
    """Candle.__post_init__ validates close_time matches timestamp + timeframe."""
    # Valid candle
    timestamp = datetime(2024, 1, 1, 9, 15)
    close_time = timestamp + timedelta(minutes=1)
    candle = Candle(
        symbol="TEST",
        timestamp=timestamp,
        close_time=close_time,
        timeframe="1M",
        open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0,
    )
    assert candle.timestamp == timestamp
    assert candle.close_time == close_time
    assert candle.timeframe == "1M"
    
    # Invalid candle - close_time doesn't match
    try:
        Candle(
            symbol="TEST",
            timestamp=timestamp,
            close_time=timestamp + timedelta(minutes=5),  # Wrong: 5 minutes instead of 1
            timeframe="1M",
            open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0,
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "close_time" in str(e)
        assert "does not match" in str(e)