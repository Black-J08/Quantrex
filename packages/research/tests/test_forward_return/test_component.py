"""Tests for ForwardReturnComponent."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.logging import setup_logging

from quantrex_research.research_components.forward_return.config import ForwardReturnConfig
from quantrex_research.research_components.forward_return.component import ForwardReturnComponent
from quantrex_research.research_components.forward_return.models import ForwardReturnEvent, ForwardReturnSeries


class TestForwardReturnComponent(ForwardReturnComponent):
    """Test implementation of ForwardReturnComponent."""
    
    def __init__(self, config):
        super().__init__(config)
        self.detected_events = []
    
    def on_candle(self, candle: Candle) -> None:
        # Simple test: emit event on every 3rd candle
        if len(self.detected_events) % 3 == 0:
            self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {"test": True})
            self.detected_events.append(candle.timestamp)


def test_component_initialization():
    """Test component initialization with config."""
    config = ForwardReturnConfig(
        horizons=[timedelta(minutes=1), timedelta(minutes=5)],
        boundary_handling="nan",
    )
    component = TestForwardReturnComponent(config)
    
    assert component.config == config
    assert component.get_horizons() == [timedelta(minutes=1), timedelta(minutes=5)]


def test_component_on_start():
    """Test on_start initializes state."""
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = TestForwardReturnComponent(config)
    
    component.on_start()
    
    assert component._events == []
    assert component._series_list == []
    assert component._result is None


def test_component_emit_event():
    """Test emit_event stores event and calls engine."""
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = TestForwardReturnComponent(config)
    
    # Mock engine
    mock_engine = Mock()
    component.set_event_receiver(mock_engine)
    
    # Create test candle
    candle = Candle(
        symbol="TEST",
        timestamp=datetime(2024, 1, 1, 9, 15),
        close_time=datetime(2024, 1, 1, 9, 16),
        timeframe="1M",
        open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0,
    )
    component._current_candle = candle
    
    # Emit event
    component.emit_event("TEST", OrderSide.BUY, candle.timestamp, {"test": True})
    
    # Verify engine.receive_event was called
    mock_engine.receive_event.assert_called_once()
    call_args = mock_engine.receive_event.call_args
    assert call_args[0][0] is component  # component
    assert isinstance(call_args[0][1], ForwardReturnEvent)  # event
    assert call_args[0][2] is candle  # emission_candle


def test_component_on_returns_calculated():
    """Test on_returns_calculated stores series."""
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = TestForwardReturnComponent(config)
    component.on_start()
    
    # Create mock event and series
    event = ForwardReturnEvent(
        symbol="TEST",
        timestamp=datetime(2024, 1, 1, 9, 15),
        direction=OrderSide.BUY,
        metadata={},
        candle=Candle(
            symbol="TEST",
            timestamp=datetime(2024, 1, 1, 9, 15),
            close_time=datetime(2024, 1, 1, 9, 16),
            timeframe="1M",
            open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0,
        ),
    )
    series = ForwardReturnSeries(event=event, returns={timedelta(minutes=1): 1.5})
    
    component.on_returns_calculated(event, series)
    
    assert len(component._series_list) == 1
    assert component._series_list[0] is series


def test_component_on_stop_writes_artifacts(tmp_path):
    """Test on_stop writes output artifacts."""
    setup_logging(level="DEBUG")
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = TestForwardReturnComponent(config)
    component.on_start()
    
    # Add some test series
    event = ForwardReturnEvent(
        symbol="TEST",
        timestamp=datetime(2024, 1, 1, 9, 15),
        direction=OrderSide.BUY,
        metadata={},
        candle=Candle(
            symbol="TEST",
            timestamp=datetime(2024, 1, 1, 9, 15),
            close_time=datetime(2024, 1, 1, 9, 16),
            timeframe="1M",
            open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0,
        ),
    )
    series = ForwardReturnSeries(event=event, returns={timedelta(minutes=1): 1.5})
    component._series_list.append(series)
    
    # Call on_stop
    result = component.on_stop(tmp_path)
    
    # Verify result
    assert result is not None
    assert hasattr(result, 'horizon_stats')
    
    # Verify files created
    assert (tmp_path / "forward_returns.json").exists()
    assert (tmp_path / "forward_returns.csv").exists()
    assert (tmp_path / "plots").exists()
    assert (tmp_path / "plots" / "distribution_0:01:00.png").exists()
    assert (tmp_path / "plots" / "qq_0:01:00.png").exists()
    assert (tmp_path / "plots" / "tail_comparison_0:01:00.png").exists()
    assert (tmp_path / "plots" / "horizon_comparison.png").exists()


def test_component_config_validation():
    """Test ForwardReturnConfig validation."""
    # Valid config
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    assert config.horizons == [timedelta(minutes=1)]
    
    # Invalid: empty horizons
    try:
        ForwardReturnConfig(horizons=[])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "horizons must not be empty" in str(e)
    
    # Invalid: negative horizon
    try:
        ForwardReturnConfig(horizons=[timedelta(minutes=-1)])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "All horizons must be positive" in str(e)
    
    # Invalid: boundary_handling
    try:
        ForwardReturnConfig(horizons=[timedelta(minutes=1)], boundary_handling="invalid")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Invalid boundary_handling" in str(e)
    
    # Invalid: missing_data_handling
    try:
        ForwardReturnConfig(horizons=[timedelta(minutes=1)], missing_data_handling="invalid")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Invalid missing_data_handling" in str(e)


def test_component_horizon_bars_conversion():
    """Test horizon to bars conversion."""
    config = ForwardReturnConfig(
        horizons=[timedelta(minutes=1), timedelta(minutes=5), timedelta(hours=1)],
        base_timeframe_minutes=1,
    )
    
    assert config.horizon_bars == [1, 5, 60]
    
    # Test with different base timeframe
    config_5m = ForwardReturnConfig(
        horizons=[timedelta(minutes=5), timedelta(minutes=15)],
        base_timeframe_minutes=5,
    )
    
    assert config_5m.horizon_bars == [1, 3]