"""Integration tests for multi-timeframe dispatch timing correctness."""

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from quantrex_core import Candle, Strategy
from quantrex_core.strategy.timeframe import on_timeframe
from quantrex_core.protocols import DataAdapter
from quantrex_backtest import BacktestEngine, InstrumentSpec, BacktestConfig


def _mock_adapter(rows: list[dict]) -> Mock:
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = rows
    adapter.datetime_format = "%Y%m%d %H:%M"
    adapter.supported_timeframes = ["1M", "15M", "1H", "1D"]
    adapter.get_origin_time.return_value = None
    return adapter


def _row(ts: str, o: float, h: float, l: float, c: float, v: float) -> dict:
    return {
        "datetime": ts,
        "open": str(o),
        "high": str(h),
        "low": str(l),
        "close": str(c),
        "volume": str(v),
    }


class HigherTimeframeVisibilityStrategy(Strategy):
    """Strategy that records when higher-TF candles become visible."""
    
    def __init__(self):
        super().__init__()
        self.h1_candles = []
        self.h1_visibility_times = []  # execution times when 1H candles visible
    
    @on_timeframe("1H")
    def on_1h_candle(self, candle: Candle) -> None:
        self.h1_candles.append(candle)
        # Record the execution time when this 1H candle was dispatched
        self.h1_visibility_times.append(self.ctx.current_time)
    
    def on_candle(self, candle: Candle) -> None:
        # Override to force 1M as base timeframe
        pass


class MultiTimeframeDispatchOrderStrategy(Strategy):
    """Strategy that records dispatch order at each execution time."""
    
    def __init__(self):
        super().__init__()
        self.dispatch_log = []  # List of (execution_time, timeframe, candle_timestamp)
    
    @on_timeframe("15M")
    def on_15m_candle(self, candle: Candle) -> None:
        self.dispatch_log.append((self.ctx.current_time, "15M", candle.timestamp))
    
    @on_timeframe("1H")
    def on_1h_candle(self, candle: Candle) -> None:
        self.dispatch_log.append((self.ctx.current_time, "1H", candle.timestamp))
    
    def on_candle(self, candle: Candle) -> None:
        pass


class DispatcherResetStrategy(Strategy):
    """Strategy for testing dispatcher reset between runs."""
    
    def __init__(self):
        super().__init__()
        self.h1_candles = []
    
    @on_timeframe("1H")
    def on_1h_candle(self, candle: Candle) -> None:
        self.h1_candles.append(candle)
    
    def on_candle(self, candle: Candle) -> None:
        pass


def test_higher_timeframe_candle_visibility_timing():
    """Test that higher-TF candle is NOT visible before close time, IS visible at/after close time.
    
    With 1M base and 1H higher-TF:
    - 1H candle (9:00-10:00) has close_time = 10:00
    - Should NOT be visible when processing base candles with execution_time < 10:00
    - Should BE visible when processing base candle with execution_time >= 10:00
    """
    # Create 1M candles from 9:00 to 10:29 (90 minutes)
    # 1H interval 9:00-10:00 closes at 10:00
    rows = []
    base_time = datetime(2024, 1, 1, 9, 0)
    for i in range(90):  # 9:00 to 10:29
        ts = base_time + timedelta(minutes=i)
        rows.append(_row(ts.strftime("%Y%m%d %H:%M"), 100.0, 101.0, 99.0, 100.5, 1000.0))
    
    # Also need 1H data (pre-aggregated) - timestamps are OPEN times
    h1_rows = [
        _row("20240101 09:00", 100.0, 101.0, 99.0, 100.5, 60000.0),  # 9:00-10:00, close at 10:00
        _row("20240101 10:00", 100.5, 101.5, 100.0, 101.0, 60000.0),  # 10:00-11:00, close at 11:00
    ]
    
    def read_timeframe_side_effect(tf, from_date=None, to_date=None):
        if tf == "1M":
            return rows
        elif tf == "1H":
            return h1_rows
        return []
    
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.side_effect = read_timeframe_side_effect
    adapter.datetime_format = "%Y%m%d %H:%M"
    adapter.supported_timeframes = ["1M", "1H"]
    adapter.get_origin_time.return_value = None
    
    strategy = HigherTimeframeVisibilityStrategy()
    engine = BacktestEngine(
        [InstrumentSpec(symbol="TEST", adapter=adapter)],
        strategy,
        BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
    )
    
    # Debug: check required timeframes
    required_tfs = engine._get_required_timeframes()
    print(f"Required timeframes: {required_tfs}")
    print(f"Base timeframe: {required_tfs[0]}")
    
    # Debug: check what 1H data looks like after reading
    h1_data = adapter.read_timeframe("1H")
    print(f"1H data from adapter: {h1_data}")
    
    # Debug: test calculate_close_time
    from quantrex_backtest.core.timeframe import calculate_close_time
    test_time = datetime(2024, 1, 1, 9, 0)
    close_1h = calculate_close_time(test_time, "1H")
    close_1m = calculate_close_time(test_time, "1M")
    print(f"calculate_close_time(9:00, '1H') = {close_1h}")
    print(f"calculate_close_time(9:00, '1M') = {close_1m}")
    
    engine.run()
    
    # Debug: print what we got
    print(f"H1 candles count: {len(strategy.h1_candles)}")
    for i, c in enumerate(strategy.h1_candles):
        print(f"  H1 candle {i}: timestamp={c.timestamp}, visibility_time={strategy.h1_visibility_times[i]}")
    
    # The 1H candle (9:00-10:00) should only become visible at execution_time >= 10:00
    # That happens when processing the 1M candle at 9:59 (execution_time = 10:00)
    # The 1H candle (10:00-11:00) has close_time = 11:00, which is > max execution_time (10:30)
    # So we should see exactly 1 H1 candle dispatched
    assert len(strategy.h1_candles) == 1, f"Expected 1 H1 candle, got {len(strategy.h1_candles)}"
    
    # The visibility time should be 10:00 (close time of the 1H interval)
    assert strategy.h1_visibility_times[0] == datetime(2024, 1, 1, 10, 0), \
        f"Expected visibility at 10:00, got {strategy.h1_visibility_times[0]}"
    
    # The 1H candle timestamp should be 9:00 (open time from pre-aggregated data)
    assert strategy.h1_candles[0].timestamp == datetime(2024, 1, 1, 9, 0), \
        f"Expected 1H candle timestamp 9:00, got {strategy.h1_candles[0].timestamp}"


def test_multi_timeframe_dispatch_order_at_execution_time():
    """Test that at each execution time, callbacks fire in hierarchy order (15M then 1H)."""
    # Create 1M candles from 9:00 to 11:30 (150 minutes)
    # This gives us multiple 15M and 1H intervals
    rows = []
    base_time = datetime(2024, 1, 1, 9, 0)
    for i in range(150):  # 9:00 to 11:29
        ts = base_time + timedelta(minutes=i)
        rows.append(_row(ts.strftime("%Y%m%d %H:%M"), 100.0, 101.0, 99.0, 100.5, 1000.0))
    
    # Pre-aggregated 15M data (4 candles per hour)
    h15_rows = [
        _row("20240101 09:00", 100.0, 101.0, 99.0, 100.5, 15000.0),  # 9:00-9:15
        _row("20240101 09:15", 100.5, 101.5, 100.0, 101.0, 15000.0),  # 9:15-9:30
        _row("20240101 09:30", 101.0, 102.0, 100.5, 101.5, 15000.0),  # 9:30-9:45
        _row("20240101 09:45", 101.5, 102.5, 101.0, 102.0, 15000.0),  # 9:45-10:00
        _row("20240101 10:00", 102.0, 103.0, 101.5, 102.5, 15000.0),  # 10:00-10:15
        _row("20240101 10:15", 102.5, 103.5, 102.0, 103.0, 15000.0),  # 10:15-10:30
        _row("20240101 10:30", 103.0, 104.0, 102.5, 103.5, 15000.0),  # 10:30-10:45
        _row("20240101 10:45", 103.5, 104.5, 103.0, 104.0, 15000.0),  # 10:45-11:00
        _row("20240101 11:00", 104.0, 105.0, 103.5, 104.5, 15000.0),  # 11:00-11:15
        _row("20240101 11:15", 104.5, 105.5, 104.0, 105.0, 15000.0),  # 11:15-11:30
    ]
    
    # Pre-aggregated 1H data
    h1_rows = [
        _row("20240101 09:00", 100.0, 102.0, 99.0, 102.0, 60000.0),  # 9:00-10:00
        _row("20240101 10:00", 102.0, 104.0, 101.5, 104.0, 60000.0),  # 10:00-11:00
        _row("20240101 11:00", 104.0, 105.0, 103.5, 105.0, 60000.0),  # 11:00-12:00
    ]
    
    def read_timeframe_side_effect(tf, from_date=None, to_date=None):
        if tf == "1M":
            return rows
        elif tf == "15M":
            return h15_rows
        elif tf == "1H":
            return h1_rows
        return []
    
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.side_effect = read_timeframe_side_effect
    adapter.datetime_format = "%Y%m%d %H:%M"
    adapter.supported_timeframes = ["1M", "15M", "1H"]
    adapter.get_origin_time.return_value = None
    
    strategy = MultiTimeframeDispatchOrderStrategy()
    engine = BacktestEngine(
        [InstrumentSpec(symbol="TEST", adapter=adapter)],
        strategy,
        BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
    )
    engine.run()
    
    # Verify dispatch order at each execution time
    # Group by execution time and verify 15M comes before 1H
    from collections import defaultdict
    by_execution_time = defaultdict(list)
    for exec_time, tf, candle_ts in strategy.dispatch_log:
        by_execution_time[exec_time].append(tf)
    
    for exec_time, timeframes in by_execution_time.items():
        # At each execution time, 15M should appear before 1H if both fire
        if "15M" in timeframes and "1H" in timeframes:
            idx_15m = timeframes.index("15M")
            idx_1h = timeframes.index("1H")
            assert idx_15m < idx_1h, \
                f"At execution time {exec_time}, 15M should dispatch before 1H, got {timeframes}"


def test_dispatcher_reset_between_runs():
    """Test that TimeframeDispatcher.reset() clears state between engine runs."""
    # Create 1M candles for 2 hours
    rows = []
    base_time = datetime(2024, 1, 1, 9, 0)
    for i in range(120):  # 9:00 to 10:59
        ts = base_time + timedelta(minutes=i)
        rows.append(_row(ts.strftime("%Y%m%d %H:%M"), 100.0, 101.0, 99.0, 100.5, 1000.0))
    
    h1_rows = [
        _row("20240101 09:00", 100.0, 101.0, 99.0, 100.5, 60000.0),  # 9:00-10:00
        _row("20240101 10:00", 100.5, 101.5, 100.0, 101.0, 60000.0),  # 10:00-11:00
    ]
    
    def read_timeframe_side_effect(tf, from_date=None, to_date=None):
        if tf == "1M":
            return rows
        elif tf == "1H":
            return h1_rows
        return []
    
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.side_effect = read_timeframe_side_effect
    adapter.datetime_format = "%Y%m%d %H:%M"
    adapter.supported_timeframes = ["1M", "1H"]
    adapter.get_origin_time.return_value = None
    
    strategy = DispatcherResetStrategy()
    engine = BacktestEngine(
        [InstrumentSpec(symbol="TEST", adapter=adapter)],
        strategy,
        BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
    )
    
    # First run
    engine.run()
    first_run_count = len(strategy.h1_candles)
    assert first_run_count == 2, f"First run: expected 2 H1 candles, got {first_run_count}"
    
    # Second run (same engine, same strategy instance)
    engine.run()
    second_run_count = len(strategy.h1_candles)
    
    # Should have 2 more (total 4), not 4 more (total 6) - dispatcher should reset
    assert second_run_count == 4, \
        f"Second run: expected 4 total H1 candles (2 per run), got {second_run_count}. " \
        f"Dispatcher state not reset between runs."