"""Tests for ResearchEngine - All-at-once calculation."""

from datetime import datetime, timedelta
from unittest.mock import Mock

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig
from quantrex_backtest import InstrumentSpec, BacktestConfig


def test_engine_all_at_once_horizon_calculation():
    """All horizons calculated at once when the last horizon elapses; single result received via on_returns_calculated."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
        {"datetime": "2024-01-01 09:17:00", "open": "102", "high": "103", "low": "101", "close": "102", "volume": "100"},
        {"datetime": "2024-01-01 09:18:00", "open": "103", "high": "104", "low": "102", "close": "103", "volume": "100"},
        {"datetime": "2024-01-01 09:19:00", "open": "104", "high": "105", "low": "103", "close": "104", "volume": "100"},
        {"datetime": "2024-01-01 09:20:00", "open": "105", "high": "106", "low": "104", "close": "105", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    received_calculations = []
    
    class TestComponent(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.event_emitted = False
        
        def on_candle(self, candle: Candle) -> None:
            if not self.event_emitted:
                self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {"test": True})
                self.event_emitted = True
        
        def on_returns_calculated(self, event, series):
            received_calculations.append({
                "timestamp": self.current_candle.timestamp if self.current_candle else None,
                "horizons": list(series.returns.keys()),
                "returns": dict(series.returns),
            })
    
    config = ForwardReturnConfig(horizons=[
        timedelta(minutes=1),
        timedelta(minutes=2),
        timedelta(minutes=5),
    ])
    component = TestComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    # Should receive single calculation when all horizons have elapsed (at 09:20)
    assert len(received_calculations) == 1
    
    # Single calculation with all horizons
    calc = received_calculations[0]
    assert timedelta(minutes=1) in calc["horizons"]
    assert timedelta(minutes=2) in calc["horizons"]
    assert timedelta(minutes=5) in calc["horizons"]
    assert calc["returns"][timedelta(minutes=1)] == 1.0  # (101-100)/100*100
    assert calc["returns"][timedelta(minutes=2)] == 2.0  # (102-100)/100*100
    assert calc["returns"][timedelta(minutes=5)] == 5.0  # (105-100)/100*100


def test_engine_multiple_events_all_at_once():
    """Multiple events should each receive single all-at-once calculation."""
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
    
    received_calculations = []
    
    class TestComponent(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.candle_index = 0
        
        def on_candle(self, candle: Candle) -> None:
            # Emit event on first and third candle (indices 0 and 2)
            if self.candle_index == 0 or self.candle_index == 2:
                self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {"event_num": self.candle_index})
            self.candle_index += 1
        
        def on_returns_calculated(self, event, series):
            received_calculations.append({
                "event_num": event.metadata.get("event_num"),
                "horizons": list(series.returns.keys()),
                "returns": dict(series.returns),
            })
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1), timedelta(minutes=2)])
    component = TestComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    # Should have calculations for both events
    assert len(received_calculations) == 2
    event_nums = set(c["event_num"] for c in received_calculations)
    assert event_nums == {0, 2}
    for event_num in [0, 2]:
        event_calcs = [c for c in received_calculations if c["event_num"] == event_num]
        assert len(event_calcs) == 1  # One calculation per event
        calc = event_calcs[0]
        assert timedelta(minutes=1) in calc["horizons"]
        assert timedelta(minutes=2) in calc["horizons"]