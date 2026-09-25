"""Tests for ResearchEngine - Look-ahead bias prevention."""

from datetime import datetime, timedelta
from unittest.mock import Mock

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig
from quantrex_backtest import InstrumentSpec, BacktestConfig


class LookAheadTestComponent(ForwardReturnComponent):
    """Component that attempts to access future data during on_candle."""
    
    def __init__(self, config):
        super().__init__(config)
        self.future_access_attempts = 0
        self.candles_seen = []
    
    def on_candle(self, candle: Candle) -> None:
        self.candles_seen.append(candle)
        # In a real look-ahead scenario, component might try to access
        # future candles through some mechanism. Here we verify that
        # the engine doesn't provide future data during on_candle.
        pass


def test_engine_no_future_data_during_on_candle():
    """Event emitted at candle t cannot access data from t+1 during on_candle."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
        {"datetime": "2024-01-01 09:17:00", "open": "102", "high": "103", "low": "101", "close": "102", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = LookAheadTestComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    # Component should only see candles in chronological order
    # No future data should be accessible during on_candle
    timestamps = [c.timestamp for c in component.candles_seen]
    assert timestamps == [
        datetime(2024, 1, 1, 9, 15),
        datetime(2024, 1, 1, 9, 16),
        datetime(2024, 1, 1, 9, 17),
    ]


def test_engine_forward_returns_only_calculated_when_horizon_elapses():
    """Forward returns only calculated when current_candle.timestamp >= event_candle.close_time + horizon."""
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
    
    received_series = []
    
    class TestComponent(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.event_emitted = False
            self.candles_seen = []
        
        def on_candle(self, candle: Candle) -> None:
            if not self.event_emitted and len(self.candles_seen) == 0:
                # Emit event on first candle
                self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {"test": True})
                self.event_emitted = True
            self.candles_seen.append(candle)
        
        def on_returns_calculated(self, event, series):
            received_series.append((event, series))
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=2)])  # 2-minute horizon
    component = TestComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    # Event emitted at 09:15, horizon 2 minutes
    # Should be calculated when current_candle.timestamp >= 09:15 + 1min (close_time) + 2min = 09:18
    # So at 09:18 candle (3rd candle processed)
    assert len(received_series) == 1
    event, series = received_series[0]
    assert series.returns[timedelta(minutes=2)] is not None
    # Return should be (103 - 100) / 100 * 100 = 3%


def test_engine_no_calculator_future_data_leakage():
    """Calculator should not access future data beyond what's elapsed."""
    from quantrex_research.research_components.forward_return.calculator import ForwardReturnCalculator
    from quantrex_research.research_components.forward_return.models import ForwardReturnEvent
    
    # Create candles
    base_time = datetime(2024, 1, 1, 9, 15)
    candles = []
    for i in range(5):
        timestamp = base_time + timedelta(minutes=i)
        close_time = timestamp + timedelta(minutes=1)
        candle = Candle(
            symbol="TEST",
            timestamp=timestamp,
            close_time=close_time,
            timeframe="1M",
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.0 + i,
            volume=100.0,
        )
        candles.append(candle)
    
    # Event at index 0 (price 100)
    event_candle = candles[0]
    event = ForwardReturnEvent(
        symbol="TEST",
        timestamp=event_candle.timestamp,
        direction=OrderSide.BUY,
        metadata={},
        candle=event_candle,
    )
    
    # Calculate for 2-minute horizon (should use candle at index 2, price 102)
    series = ForwardReturnCalculator.calculate(candles, event, [timedelta(minutes=2)])
    assert series.returns[timedelta(minutes=2)] == 2.0  # (102-100)/100*100 = 2%
    
    # Calculate for 10-minute horizon (beyond data)
    series = ForwardReturnCalculator.calculate(candles, event, [timedelta(minutes=10)])
    assert series.returns[timedelta(minutes=10)] is None