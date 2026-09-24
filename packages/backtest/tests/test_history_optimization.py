#!/usr/bin/env python3
"""Test script to verify history optimization works correctly."""

from datetime import datetime, timedelta
from quantrex_core.models import Candle
from quantrex_backtest.core import BacktestStrategyContext
from quantrex_core.position.manager import PositionManager
from quantrex_core.order import OrderManagementSystem


def test_history_optimization():
    """Test that history property returns correct values after optimization."""
    print("Testing history optimization...")
    
    # Create context with current_time set to allow candles to be considered completed
    ctx = BacktestStrategyContext(
        position_manager=PositionManager(),
        oms=OrderManagementSystem(),
        current_time=datetime(2024, 1, 1, 9, 35)  # After all candle close times
    )
    
    # Create test candles
    candles = [
        Candle("TEST", datetime(2024, 1, 1, 9, 30), datetime(2024, 1, 1, 9, 31), "1M", 1.0, 2.0, 0.5, 1.5, 100),
        Candle("TEST", datetime(2024, 1, 1, 9, 31), datetime(2024, 1, 1, 9, 32), "1M", 2.0, 3.0, 1.5, 2.5, 200),
        Candle("TEST", datetime(2024, 1, 1, 9, 32), datetime(2024, 1, 1, 9, 33), "1M", 3.0, 4.0, 2.5, 3.5, 300),
        Candle("TEST", datetime(2024, 1, 1, 9, 33), datetime(2024, 1, 1, 9, 34), "1M", 4.0, 5.0, 3.5, 4.5, 400),
        Candle("TEST", datetime(2024, 1, 1, 9, 34), datetime(2024, 1, 1, 9, 35), "1M", 5.0, 6.0, 4.5, 5.5, 500),
    ]
    
    # Record candles one by one and check history after each
    for i, candle in enumerate(candles):
        ctx.record_candle(candle)
        history = ctx.history
        
        # After recording i+1 candles, history should have i+1 elements
        expected_length = i + 1
        actual_length = len(history)
        
        print(f"After recording {i+1} candles: history length = {actual_length} (expected {expected_length})")
        
        assert actual_length == expected_length, f"Expected {expected_length} candles in history, got {actual_length}"
        
        # Check that the candles are in correct order
        for j in range(expected_length):
            assert history[j] is candles[j], f"Candle {j} mismatch"
    
    # Test that history returns a fresh tuple each time
    history1 = ctx.history
    history2 = ctx.history
    assert history1 == history2, "History contents should be equal"
    assert history1 is not history2, "History should return fresh tuples"
    
    # Test reset functionality
    ctx.reset()
    assert len(ctx.history) == 0, "History should be empty after reset"
    assert ctx._base_completed_index == 0, "Base completed index should be reset to 0"
    
    print("All tests passed!")


def test_edge_cases():
    """Test edge cases like datetime.min (uninitialized context)."""
    print("\nTesting edge cases...")
    
    # Test with datetime.min (should return empty history for backward compatibility)
    ctx = BacktestStrategyContext(
        position_manager=PositionManager(),
        oms=OrderManagementSystem(),
        current_time=datetime.min  # Uninitialized context
    )
    
    # Add some candles
    candle = Candle("TEST", datetime(2024, 1, 1, 9, 30), datetime(2024, 1, 1, 9, 31), "1M", 1.0, 2.0, 0.5, 1.5, 100)
    ctx.record_candle(candle)
    
    # With datetime.min, history should be empty (backward compatibility)
    history = ctx.history
    assert len(history) == 0, f"Expected empty history with datetime.min, got {len(history)}"
    
    # Test with current_time before any candle close times
    ctx2 = BacktestStrategyContext(
        position_manager=PositionManager(),
        oms=OrderManagementSystem(),
        current_time=datetime(2024, 1, 1, 9, 29)  # Before first candle close time
    )
    
    ctx2.record_candle(candle)
    history2 = ctx2.history
    assert len(history2) == 0, f"Expected empty history when current_time < close_time, got {len(history2)}"
    
    print("Edge case tests passed!")


if __name__ == "__main__":
    test_history_optimization()
    test_edge_cases()
    print("\nAll tests completed successfully!")