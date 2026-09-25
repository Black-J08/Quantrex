"""Tests for ForwardReturnCalculator."""

from datetime import datetime, timedelta
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide

from quantrex_research.research_components.forward_return.models import ForwardReturnEvent
from quantrex_research.research_components.forward_return.calculator import ForwardReturnCalculator


def create_test_candles() -> list[Candle]:
    """Create a series of test candles with known prices."""
    base_time = datetime(2024, 1, 1, 9, 15)
    candles = []
    
    # Create 10 candles with increasing prices
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
    
    for i, price in enumerate(prices):
        timestamp = base_time + timedelta(minutes=i)
        close_time = timestamp + timedelta(minutes=1)
        candle = Candle(
            symbol="TEST",
            timestamp=timestamp,
            close_time=close_time,
            timeframe="1M",
            open=price,
            high=price + 0.5,
            low=price - 0.5,
            close=price,
            volume=100.0,
        )
        candles.append(candle)
    
    return candles


def test_calculator_basic_percentage_return():
    """Test basic percentage return calculation."""
    candles = create_test_candles()
    
    # Event at candle index 0 (price 100.0)
    event_candle = candles[0]
    event = ForwardReturnEvent(
        symbol="TEST",
        timestamp=event_candle.timestamp,
        direction=OrderSide.BUY,
        metadata={},
        candle=event_candle,
    )
    
    # 1-minute horizon (1 bar) -> should use candle at index 1 (price 101.0)
    # Return = (101.0 - 100.0) / 100.0 * 100 = 1.0%
    horizons = [timedelta(minutes=1)]
    series = ForwardReturnCalculator.calculate(candles, event, horizons)
    
    assert series.returns[timedelta(minutes=1)] == 1.0


def test_calculator_multiple_horizons():
    """Test calculation with multiple horizons."""
    candles = create_test_candles()
    
    event_candle = candles[0]  # price 100.0
    event = ForwardReturnEvent(
        symbol="TEST",
        timestamp=event_candle.timestamp,
        direction=OrderSide.BUY,
        metadata={},
        candle=event_candle,
    )
    
    horizons = [
        timedelta(minutes=1),   # index 1: 101.0 -> 1.0%
        timedelta(minutes=3),   # index 3: 103.0 -> 3.0%
        timedelta(minutes=5),   # index 5: 105.0 -> 5.0%
    ]
    
    series = ForwardReturnCalculator.calculate(candles, event, horizons)
    
    assert series.returns[timedelta(minutes=1)] == 1.0
    assert series.returns[timedelta(minutes=3)] == 3.0
    assert series.returns[timedelta(minutes=5)] == 5.0


def test_calculator_short_direction():
    """Test calculation for SHORT direction (same formula, direction doesn't affect return)."""
    candles = create_test_candles()
    
    event_candle = candles[0]  # price 100.0
    event = ForwardReturnEvent(
        symbol="TEST",
        timestamp=event_candle.timestamp,
        direction=OrderSide.SELL,  # SHORT
        metadata={},
        candle=event_candle,
    )
    
    horizons = [timedelta(minutes=2)]  # index 2: 102.0 -> 2.0%
    series = ForwardReturnCalculator.calculate(candles, event, horizons)
    
    # Formula is the same regardless of direction
    assert series.returns[timedelta(minutes=2)] == 2.0


def test_calculator_horizon_beyond_data():
    """Test that horizons beyond data return None."""
    candles = create_test_candles()  # 10 candles, indices 0-9
    
    event_candle = candles[8]  # price 108.0, near end
    event = ForwardReturnEvent(
        symbol="TEST",
        timestamp=event_candle.timestamp,
        direction=OrderSide.BUY,
        metadata={},
        candle=event_candle,
    )
    
    # 5-minute horizon would need index 13, but we only have up to 9
    horizons = [timedelta(minutes=5)]
    series = ForwardReturnCalculator.calculate(candles, event, horizons)
    
    assert series.returns[timedelta(minutes=5)] is None


def test_calculator_calculate_all_horizons():
    """Test calculate_all_horizons method."""
    candles = create_test_candles()
    
    event_candle = candles[0]
    event = ForwardReturnEvent(
        symbol="TEST",
        timestamp=event_candle.timestamp,
        direction=OrderSide.BUY,
        metadata={},
        candle=event_candle,
    )
    
    all_horizons = [
        timedelta(minutes=1),   # valid
        timedelta(minutes=5),   # valid
        timedelta(minutes=15),  # beyond data
    ]
    
    series = ForwardReturnCalculator.calculate_all_horizons(candles, event, all_horizons)
    
    assert series.returns[timedelta(minutes=1)] == 1.0
    assert series.returns[timedelta(minutes=5)] == 5.0
    assert series.returns[timedelta(minutes=15)] is None


def test_calculator_negative_return():
    """Test calculation with decreasing prices (negative return)."""
    base_time = datetime(2024, 1, 1, 9, 15)
    candles = []
    
    # Decreasing prices
    prices = [100.0, 99.0, 98.0, 97.0, 96.0]
    
    for i, price in enumerate(prices):
        timestamp = base_time + timedelta(minutes=i)
        close_time = timestamp + timedelta(minutes=1)
        candle = Candle(
            symbol="TEST",
            timestamp=timestamp,
            close_time=close_time,
            timeframe="1M",
            open=price,
            high=price + 0.5,
            low=price - 0.5,
            close=price,
            volume=100.0,
        )
        candles.append(candle)
    
    event_candle = candles[0]  # price 100.0
    event = ForwardReturnEvent(
        symbol="TEST",
        timestamp=event_candle.timestamp,
        direction=OrderSide.BUY,
        metadata={},
        candle=event_candle,
    )
    
    horizons = [timedelta(minutes=2)]  # index 2: 98.0 -> -2.0%
    series = ForwardReturnCalculator.calculate(candles, event, horizons)
    
    assert series.returns[timedelta(minutes=2)] == -2.0


def test_calculator_event_not_in_candles():
    """Test that calculator raises error if event candle not in list."""
    candles = create_test_candles()
    
    # Create a candle not in the list
    extra_candle = Candle(
        symbol="TEST",
        timestamp=datetime(2024, 1, 1, 10, 0),
        close_time=datetime(2024, 1, 1, 10, 1),
        timeframe="1M",
        open=200.0,
        high=201.0,
        low=199.0,
        close=200.0,
        volume=100.0,
    )
    
    event = ForwardReturnEvent(
        symbol="TEST",
        timestamp=extra_candle.timestamp,
        direction=OrderSide.BUY,
        metadata={},
        candle=extra_candle,
    )
    
    horizons = [timedelta(minutes=1)]
    
    try:
        ForwardReturnCalculator.calculate(candles, event, horizons)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Event candle not found" in str(e)