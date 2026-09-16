#!/usr/bin/env python3
"""Performance test to demonstrate history optimization improvement."""

import time
from datetime import datetime, timedelta
from quantrex_core.models import Candle
from quantrex_backtest.core.context import BacktestStrategyContext
from quantrex_backtest.core.timeframe import calculate_close_time
from quantrex_core.position.manager import PositionManager
from quantrex_core.order import OrderManagementSystem


def create_test_candles(count: int, base_time: datetime) -> list[Candle]:
    """Create a list of test candles."""
    candles = []
    for i in range(count):
        timestamp = base_time + timedelta(minutes=i)
        candle = Candle(
            symbol="TEST",
            timestamp=timestamp,
            open=float(i),
            high=float(i) + 1.0,
            low=float(i) - 0.5,
            close=float(i) + 0.5,
            volume=1000.0
        )
        candles.append(candle)
    return candles


def test_history_access_performance():
    """Test performance of history access before and after optimization."""
    print("Testing history access performance...")
    
    # Create context with current_time set to allow all candles to be completed
    base_time = datetime(2024, 1, 1, 9, 30)
    # For 1M timeframe (default), close_time = timestamp + 1 minute
    # So to have all candles completed, current_time should be >= last candle's close_time
    # Last candle (i=9999) has timestamp = base_time + 9999 minutes
    # Last candle close_time = base_time + 9999 + 1 = base_time + 10000 minutes
    current_time = base_time + timedelta(minutes=10000 + 1)  # Well after all candles' close times
    
    ctx = BacktestStrategyContext(
        position_manager=PositionManager(),
        oms=OrderManagementSystem(),
        current_time=current_time
    )
    
    # Create a large number of candles
    candle_count = 10000
    candles = create_test_candles(candle_count, base_time)
    
    # Record all candles
    print(f"Recording {candle_count} candles...")
    for candle in candles:
        ctx.record_candle(candle)
    
    # Test history access performance
    print("Testing history access performance...")
    iterations = 1000
    
    # Time multiple history accesses
    start_time = time.perf_counter()
    for _ in range(iterations):
        history = ctx.history
        # Access a few elements to ensure the tuple is actually used
        _ = len(history)
        if len(history) > 0:
            _ = history[0]
    end_time = time.perf_counter()
    
    total_time = end_time - start_time
    avg_time_per_access = total_time / iterations
    
    print(f"Total time for {iterations} history accesses: {total_time:.6f} seconds")
    print(f"Average time per history access: {avg_time_per_access*1000000:.2f} microseconds")
    print(f"History length: {len(ctx.history)}")
    
    # Verify correctness
    assert len(ctx.history) == candle_count
    assert ctx._base_completed_index == candle_count
    
    return avg_time_per_access


def test_warmup_performance():
    """Test performance during warmup period."""
    print("\nTesting warmup performance...")
    
    # Create context with current_time set early (warmup period)
    base_time = datetime(2024, 1, 1, 9, 30)
    # For 1M timeframe, close_time = timestamp + 1 minute
    # Set current_time to 5 minutes after base_time, so only first 4 candles will be completed
    # (candle at 9:30 closes at 9:31, candle at 9:31 closes at 9:32, etc.)
    current_time = base_time + timedelta(minutes=5)  # 9:35
    
    ctx = BacktestStrategyContext(
        position_manager=PositionManager(),
        oms=OrderManagementSystem(),
        current_time=current_time
    )
    
    # Create candles that extend beyond current_time
    candle_count = 10000
    candles = create_test_candles(candle_count, base_time)
    
    # Record all candles
    print(f"Recording {candle_count} candles during warmup...")
    for candle in candles:
        ctx.record_candle(candle)
    
    # Test history access performance during warmup
    print("Testing history access performance during warmup...")
    iterations = 1000
    
    start_time = time.perf_counter()
    for _ in range(iterations):
        history = ctx.history
        _ = len(history)
    end_time = time.perf_counter()
    
    total_time = end_time - start_time
    avg_time_per_access = total_time / iterations
    
    print(f"Total time for {iterations} history accesses during warmup: {total_time:.6f} seconds")
    print(f"Average time per history access during warmup: {avg_time_per_access*1000000:.2f} microseconds")
    print(f"History length (completed candles): {len(ctx.history)}")
    print(f"Total candles recorded: {len(candles)}")
    
    # Verify correctness - only candles with close_time <= current_time should be in history
    # With 1M timeframe: candle at timestamp T closes at T+1 minute
    # current_time is 9:35 (base_time + 5 minutes)
    # So candles with timestamp <= 9:34 will be completed (close_time <= 9:35)
    # That's candles 0 through 4 (timestamps 9:30, 9:31, 9:32, 9:33, 9:34) = 5 candles
    expected_count = 5
    assert len(ctx.history) == expected_count, f"Expected {expected_count} completed candles, got {len(ctx.history)}"
    assert ctx._base_completed_index == expected_count, f"Expected base_completed_index {expected_count}, got {ctx._base_completed_index}"
    
    return avg_time_per_access


if __name__ == "__main__":
    print("History Optimization Performance Test")
    print("=" * 50)
    
    # Test normal performance
    normal_avg_time = test_history_access_performance()
    
    # Test warmup performance
    warmup_avg_time = test_warmup_performance()
    
    print("\n" + "=" * 50)
    print("Performance Test Summary:")
    print(f"Normal case average access time: {normal_avg_time*1000000:.2f} μs")
    print(f"Warmup case average access time: {warmup_avg_time*1000000:.2f} μs")
    print("\nBoth should be very low (ideally < 10 μs) indicating O(1) performance.")