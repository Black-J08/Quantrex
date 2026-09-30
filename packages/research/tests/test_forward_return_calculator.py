"""Regression tests for ForwardReturnCalculator symbol filtering."""

from datetime import datetime, timedelta
from unittest.mock import Mock

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide

from quantrex_research.research_components.forward_return.calculator import ForwardReturnCalculator
from quantrex_research.research_components.forward_return.models import ForwardReturnEvent


def test_calculator_uses_correct_symbol_candles():
    """Calculator should only use candles from the event's symbol for horizon search."""
    # Create merged candles for two symbols with different prices
    # SYM1: 100 -> 101 -> 102
    # SYM2: 200 -> 201 -> 202
    candles = [
        Candle(symbol="SYM1", timestamp=datetime(2024, 1, 1, 9, 15), close_time=datetime(2024, 1, 1, 9, 16),
               timeframe="1M", open=100, high=101, low=99, close=100, volume=100),
        Candle(symbol="SYM2", timestamp=datetime(2024, 1, 1, 9, 15), close_time=datetime(2024, 1, 1, 9, 16),
               timeframe="1M", open=200, high=201, low=199, close=200, volume=200),
        Candle(symbol="SYM1", timestamp=datetime(2024, 1, 1, 9, 16), close_time=datetime(2024, 1, 1, 9, 17),
               timeframe="1M", open=101, high=102, low=100, close=101, volume=100),
        Candle(symbol="SYM2", timestamp=datetime(2024, 1, 1, 9, 16), close_time=datetime(2024, 1, 1, 9, 17),
               timeframe="1M", open=201, high=202, low=200, close=201, volume=200),
        Candle(symbol="SYM1", timestamp=datetime(2024, 1, 1, 9, 17), close_time=datetime(2024, 1, 1, 9, 18),
               timeframe="1M", open=102, high=103, low=101, close=102, volume=100),
        Candle(symbol="SYM2", timestamp=datetime(2024, 1, 1, 9, 17), close_time=datetime(2024, 1, 1, 9, 18),
               timeframe="1M", open=202, high=203, low=201, close=202, volume=200),
    ]
    
    # Event for SYM1 at 9:15 (close=100)
    event_candle = candles[0]  # SYM1 9:15
    event = ForwardReturnEvent(
        symbol="SYM1",
        timestamp=datetime(2024, 1, 1, 9, 15),
        direction=OrderSide.BUY,
        metadata={},
        candle=event_candle,
    )
    
    # 1-minute horizon: should use SYM1's 9:16 candle (close=101)
    # Return = (101 - 100) / 100 * 100 = 1.0%
    series = ForwardReturnCalculator.calculate(candles, event, [timedelta(minutes=1)])
    
    assert series.returns[timedelta(minutes=1)] == 1.0, \
        f"Expected 1.0% return for SYM1, got {series.returns[timedelta(minutes=1)]}"


def test_calculator_does_not_use_other_symbol_candles():
    """Calculator should NOT use other symbol's candles even if they appear first in merged stream."""
    # Merged stream where SYM2 candles come first at each timestamp
    candles = [
        Candle(symbol="SYM2", timestamp=datetime(2024, 1, 1, 9, 15), close_time=datetime(2024, 1, 1, 9, 16),
               timeframe="1M", open=200, high=201, low=199, close=200, volume=200),
        Candle(symbol="SYM1", timestamp=datetime(2024, 1, 1, 9, 15), close_time=datetime(2024, 1, 1, 9, 16),
               timeframe="1M", open=100, high=101, low=99, close=100, volume=100),
        Candle(symbol="SYM2", timestamp=datetime(2024, 1, 1, 9, 16), close_time=datetime(2024, 1, 1, 9, 17),
               timeframe="1M", open=201, high=202, low=200, close=201, volume=200),
        Candle(symbol="SYM1", timestamp=datetime(2024, 1, 1, 9, 16), close_time=datetime(2024, 1, 1, 9, 17),
               timeframe="1M", open=101, high=102, low=100, close=101, volume=100),
    ]
    
    # Event for SYM1 at 9:15 (close=100)
    event_candle = candles[1]  # SYM1 9:15 (second in merged list)
    event = ForwardReturnEvent(
        symbol="SYM1",
        timestamp=datetime(2024, 1, 1, 9, 15),
        direction=OrderSide.BUY,
        metadata={},
        candle=event_candle,
    )
    
    # 1-minute horizon: should use SYM1's 9:16 candle (close=101), NOT SYM2's 9:16 (close=201)
    # Return = (101 - 100) / 100 * 100 = 1.0%
    series = ForwardReturnCalculator.calculate(candles, event, [timedelta(minutes=1)])
    
    assert series.returns[timedelta(minutes=1)] == 1.0, \
        f"Expected 1.0% return for SYM1 (using SYM1 candles), got {series.returns[timedelta(minutes=1)]}"


def test_calculator_all_horizons_symbol_filter():
    """calculate_all_horizons should also filter by symbol."""
    candles = [
        Candle(symbol="SYM1", timestamp=datetime(2024, 1, 1, 9, 15), close_time=datetime(2024, 1, 1, 9, 16),
               timeframe="1M", open=100, high=101, low=99, close=100, volume=100),
        Candle(symbol="SYM2", timestamp=datetime(2024, 1, 1, 9, 15), close_time=datetime(2024, 1, 1, 9, 16),
               timeframe="1M", open=200, high=201, low=199, close=200, volume=200),
        Candle(symbol="SYM1", timestamp=datetime(2024, 1, 1, 9, 16), close_time=datetime(2024, 1, 1, 9, 17),
               timeframe="1M", open=101, high=102, low=100, close=101, volume=100),
        Candle(symbol="SYM2", timestamp=datetime(2024, 1, 1, 9, 16), close_time=datetime(2024, 1, 1, 9, 17),
               timeframe="1M", open=201, high=202, low=200, close=201, volume=200),
    ]
    
    event_candle = candles[0]  # SYM1 9:15
    event = ForwardReturnEvent(
        symbol="SYM1",
        timestamp=datetime(2024, 1, 1, 9, 15),
        direction=OrderSide.BUY,
        metadata={},
        candle=event_candle,
    )
    
    series = ForwardReturnCalculator.calculate_all_horizons(candles, event, [timedelta(minutes=1)])
    
    assert series.returns[timedelta(minutes=1)] == 1.0, \
        f"Expected 1.0% return for SYM1 in calculate_all_horizons, got {series.returns[timedelta(minutes=1)]}"


def test_calculator_handles_missing_horizon_candle():
    """Calculator should return None when horizon extends beyond available data for that symbol."""
    candles = [
        Candle(symbol="SYM1", timestamp=datetime(2024, 1, 1, 9, 15), close_time=datetime(2024, 1, 1, 9, 16),
               timeframe="1M", open=100, high=101, low=99, close=100, volume=100),
        Candle(symbol="SYM2", timestamp=datetime(2024, 1, 1, 9, 15), close_time=datetime(2024, 1, 1, 9, 16),
               timeframe="1M", open=200, high=201, low=199, close=200, volume=200),
    ]
    
    event_candle = candles[0]  # SYM1 9:15
    event = ForwardReturnEvent(
        symbol="SYM1",
        timestamp=datetime(2024, 1, 1, 9, 15),
        direction=OrderSide.BUY,
        metadata={},
        candle=event_candle,
    )
    
    # 5-minute horizon but only 1 minute of data available for SYM1
    series = ForwardReturnCalculator.calculate(candles, event, [timedelta(minutes=5)])
    
    assert series.returns[timedelta(minutes=5)] is None, \
        f"Expected None for incomplete horizon, got {series.returns[timedelta(minutes=5)]}"