"""Integration tests for multi-timeframe dispatch timing correctness in ResearchEngine."""

from datetime import datetime, time, timedelta
from unittest.mock import Mock

import pytest

from quantrex_core import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter
from quantrex_core.strategy.timeframe import on_timeframe

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig
from quantrex_backtest import InstrumentSpec, BacktestConfig
from quantrex_backtest.data.orchestrator import DataOrchestratorConfig


def _mock_adapter(rows: list[dict], supported_timeframes=None, origin_time=None) -> Mock:
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = rows
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = supported_timeframes or ["1M", "15M", "1H", "1D"]
    adapter.get_origin_time.return_value = origin_time
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


class HigherTimeframeVisibilityComponent(ForwardReturnComponent):
    """Component that records when higher-TF candles become visible."""
    
    def __init__(self, config):
        super().__init__(config)
        self.h1_candles = []
        self.h1_visibility_times = []  # execution times when 1H candles visible
    
    @on_timeframe("1H")
    def on_1h_candle(self, candle: Candle) -> None:
        self.h1_candles.append(candle)
        # Record the execution time when this 1H candle was dispatched
        self.h1_visibility_times.append(self.ctx.current_time if hasattr(self.ctx, 'current_time') else self.current_candle.close_time)
    
    def on_candle(self, candle: Candle) -> None:
        # Override to force 1M as base timeframe
        pass


class MultiTimeframeDispatchOrderComponent(ForwardReturnComponent):
    """Component that records dispatch order at each execution time."""
    
    def __init__(self, config):
        super().__init__(config)
        self.dispatch_log = []  # List of (execution_time, timeframe, candle_timestamp)
    
    @on_timeframe("15M")
    def on_15m_candle(self, candle: Candle) -> None:
        self.dispatch_log.append((self.current_candle.close_time, "15M", candle.timestamp))
    
    @on_timeframe("1H")
    def on_1h_candle(self, candle: Candle) -> None:
        self.dispatch_log.append((self.current_candle.close_time, "1H", candle.timestamp))
    
    def on_candle(self, candle: Candle) -> None:
        pass


class DispatcherResetComponent(ForwardReturnComponent):
    """Component for testing dispatcher reset between runs."""
    
    def __init__(self, config):
        super().__init__(config)
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
        rows.append(_row(ts.strftime("%Y-%m-%d %H:%M:%S"), 100.0, 101.0, 99.0, 100.5, 1000.0))
    
    # Also need 1H data (pre-aggregated) - timestamps are OPEN times
    h1_rows = [
        _row("2024-01-01 09:00:00", 100.0, 101.0, 99.0, 100.5, 60000.0),  # 9:00-10:00, close at 10:00
        _row("2024-01-01 10:00:00", 100.5, 101.5, 100.0, 101.0, 60000.0),  # 10:00-11:00, close at 11:00
    ]
    
    def read_timeframe_side_effect(tf, from_date=None, to_date=None):
        if tf == "1M":
            return rows
        elif tf == "1H":
            return h1_rows
        return []
    
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.side_effect = read_timeframe_side_effect
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M", "1H"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = HigherTimeframeVisibilityComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="TEST", adapter=adapter)],
        [component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
        data_orchestrator_config=DataOrchestratorConfig(min_bars_required=1)
    )
    
    engine.run()
    
    # The 1H candle (9:00-10:00) should only become visible at execution_time >= 10:00
    # That happens when processing the 1M candle at 9:59 (execution_time = 10:00)
    # The 1H candle (10:00-11:00) has close_time = 11:00, which is > max execution_time (10:30)
    # So we should see exactly 1 H1 candle dispatched
    assert len(component.h1_candles) == 1, f"Expected 1 H1 candle, got {len(component.h1_candles)}"
    
    # The visibility time should be 10:00 (close time of the 1H interval)
    assert component.h1_visibility_times[0] == datetime(2024, 1, 1, 10, 0), \
        f"Expected visibility at 10:00, got {component.h1_visibility_times[0]}"
    
    # The 1H candle timestamp should be 9:00 (open time from pre-aggregated data)
    assert component.h1_candles[0].timestamp == datetime(2024, 1, 1, 9, 0), \
        f"Expected 1H candle timestamp 9:00, got {component.h1_candles[0].timestamp}"


def test_multi_timeframe_dispatch_order_at_execution_time():
    """Test that at each execution time, callbacks fire in hierarchy order (15M then 1H)."""
    # Create 1M candles from 9:00 to 11:30 (150 minutes)
    # This gives us multiple 15M and 1H intervals
    rows = []
    base_time = datetime(2024, 1, 1, 9, 0)
    for i in range(150):  # 9:00 to 11:29
        ts = base_time + timedelta(minutes=i)
        rows.append(_row(ts.strftime("%Y-%m-%d %H:%M:%S"), 100.0, 101.0, 99.0, 100.5, 1000.0))
    
    # Pre-aggregated 15M data (4 candles per hour)
    h15_rows = [
        _row("2024-01-01 09:00:00", 100.0, 101.0, 99.0, 100.5, 15000.0),  # 9:00-9:15
        _row("2024-01-01 09:15:00", 100.5, 101.5, 100.0, 101.0, 15000.0),  # 9:15-9:30
        _row("2024-01-01 09:30:00", 101.0, 102.0, 100.5, 101.5, 15000.0),  # 9:30-9:45
        _row("2024-01-01 09:45:00", 101.5, 102.5, 101.0, 102.0, 15000.0),  # 9:45-10:00
        _row("2024-01-01 10:00:00", 102.0, 103.0, 101.5, 102.5, 15000.0),  # 10:00-10:15
        _row("2024-01-01 10:15:00", 102.5, 103.5, 102.0, 103.0, 15000.0),  # 10:15-10:30
        _row("2024-01-01 10:30:00", 103.0, 104.0, 102.5, 103.5, 15000.0),  # 10:30-10:45
        _row("2024-01-01 10:45:00", 103.5, 104.5, 103.0, 104.0, 15000.0),  # 10:45-11:00
        _row("2024-01-01 11:00:00", 104.0, 105.0, 103.5, 104.5, 15000.0),  # 11:00-11:15
        _row("2024-01-01 11:15:00", 104.5, 105.5, 104.0, 105.0, 15000.0),  # 11:15-11:30
    ]
    
    # Pre-aggregated 1H data
    h1_rows = [
        _row("2024-01-01 09:00:00", 100.0, 102.0, 99.0, 102.0, 60000.0),  # 9:00-10:00
        _row("2024-01-01 10:00:00", 102.0, 104.0, 101.5, 104.0, 60000.0),  # 10:00-11:00
        _row("2024-01-01 11:00:00", 104.0, 105.0, 103.5, 105.0, 60000.0),  # 11:00-12:00
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
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M", "15M", "1H"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = MultiTimeframeDispatchOrderComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="TEST", adapter=adapter)],
        [component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
        data_orchestrator_config=DataOrchestratorConfig(min_bars_required=1)
    )
    engine.run()
    
    # Verify dispatch order at each execution time
    # Group by execution time and verify 15M comes before 1H
    from collections import defaultdict
    by_execution_time = defaultdict(list)
    for exec_time, tf, candle_ts in component.dispatch_log:
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
        rows.append(_row(ts.strftime("%Y-%m-%d %H:%M:%S"), 100.0, 101.0, 99.0, 100.5, 1000.0))
    
    h1_rows = [
        _row("2024-01-01 09:00:00", 100.0, 101.0, 99.0, 100.5, 60000.0),  # 9:00-10:00
        _row("2024-01-01 10:00:00", 100.5, 101.5, 100.0, 101.0, 60000.0),  # 10:00-11:00
    ]
    
    def read_timeframe_side_effect(tf, from_date=None, to_date=None):
        if tf == "1M":
            return rows
        elif tf == "1H":
            return h1_rows
        return []
    
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.side_effect = read_timeframe_side_effect
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M", "1H"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = DispatcherResetComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="TEST", adapter=adapter)],
        [component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
        data_orchestrator_config=DataOrchestratorConfig(min_bars_required=1)
    )
    
    # First run
    engine.run()
    first_run_count = len(component.h1_candles)
    assert first_run_count == 2, f"First run: expected 2 H1 candles, got {first_run_count}"
    
    # Second run (same engine, same component instance)
    engine.run()
    second_run_count = len(component.h1_candles)
    
    # Should have 2 more (total 4), not 4 more (total 6) - dispatcher should reset
    assert second_run_count == 4, \
        f"Second run: expected 4 total H1 candles (2 per run), got {second_run_count}. " \
        f"Dispatcher state not reset between runs."


def test_multi_timeframe_with_multiple_symbols():
    """Test multi-timeframe works correctly with multiple symbols."""
    # Symbol 1 data - 9:00 to 10:29 (90 minutes)
    rows1 = []
    base_time = datetime(2024, 1, 1, 9, 0)
    for i in range(90):  # 9:00 to 10:29
        ts = base_time + timedelta(minutes=i)
        rows1.append(_row(ts.strftime("%Y-%m-%d %H:%M:%S"), 100.0, 101.0, 99.0, 100.5, 1000.0))
    
    # Symbol 2 data - 9:00 to 10:29 (90 minutes)
    rows2 = []
    base_time2 = datetime(2024, 1, 1, 9, 0)
    for i in range(90):  # 9:00 to 10:29
        ts = base_time2 + timedelta(minutes=i)
        rows2.append(_row(ts.strftime("%Y-%m-%d %H:%M:%S"), 200.0, 201.0, 199.0, 200.5, 2000.0))
    
    # 1H data for both symbols
    h1_rows1 = [
        _row("2024-01-01 09:00:00", 100.0, 101.0, 99.0, 100.5, 60000.0),
        _row("2024-01-01 10:00:00", 100.5, 101.5, 100.0, 101.0, 60000.0),
    ]
    h1_rows2 = [
        _row("2024-01-01 09:00:00", 200.0, 201.0, 199.0, 200.5, 60000.0),
        _row("2024-01-01 10:00:00", 200.5, 201.5, 200.0, 201.0, 60000.0),
    ]
    
    def read_timeframe_side_effect1(tf, from_date=None, to_date=None):
        if tf == "1M":
            return rows1
        elif tf == "1H":
            return h1_rows1
        return []
    
    def read_timeframe_side_effect2(tf, from_date=None, to_date=None):
        if tf == "1M":
            return rows2
        elif tf == "1H":
            return h1_rows2
        return []
    
    adapter1 = Mock(spec=DataAdapter)
    adapter1.read_timeframe.side_effect = read_timeframe_side_effect1
    adapter1.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter1.supported_timeframes = ["1M", "1H"]
    adapter1.get_origin_time.return_value = None
    
    adapter2 = Mock(spec=DataAdapter)
    adapter2.read_timeframe.side_effect = read_timeframe_side_effect2
    adapter2.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter2.supported_timeframes = ["1M", "1H"]
    adapter2.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = HigherTimeframeVisibilityComponent(config)
    engine = ResearchEngine(
        [
            InstrumentSpec(symbol="SYM1", adapter=adapter1),
            InstrumentSpec(symbol="SYM2", adapter=adapter2),
        ],
        [component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
        data_orchestrator_config=DataOrchestratorConfig(min_bars_required=1)
    )
    
    engine.run()
    
    # Should have 1H candles for both symbols
    # Data goes from 9:00 to 10:29, so execution time goes from 9:01 to 10:30
    # 1H candle 9:00-10:00 closes at 10:00 -> visible at execution_time >= 10:00 (when processing 9:59 candle)
    # 1H candle 10:00-11:00 closes at 11:00 -> NOT visible (max execution_time is 10:30)
    # So we should see exactly 1 H1 candle per symbol
    sym1_candles = [c for c in component.h1_candles if c.symbol == "SYM1"]
    sym2_candles = [c for c in component.h1_candles if c.symbol == "SYM2"]
    
    assert len(sym1_candles) == 1, f"SYM1: expected 1 H1 candle, got {len(sym1_candles)}"
    assert len(sym2_candles) == 1, f"SYM2: expected 1 H1 candle, got {len(sym2_candles)}"


def test_origin_time_alignment():
    """Test that origin time correctly aligns intervals (e.g., 09:15 for NSE)."""
    # Create 1M candles from 9:15 to 11:15 (120 minutes)
    # With origin_time=09:15, 1H intervals should be 9:15-10:15, 10:15-11:15
    rows = []
    base_time = datetime(2024, 1, 1, 9, 15)
    for i in range(120):  # 9:15 to 11:14
        ts = base_time + timedelta(minutes=i)
        rows.append(_row(ts.strftime("%Y-%m-%d %H:%M:%S"), 100.0, 101.0, 99.0, 100.5, 1000.0))
    
    # 1H data aligned to 09:15 origin
    h1_rows = [
        _row("2024-01-01 09:15:00", 100.0, 101.0, 99.0, 100.5, 60000.0),  # 9:15-10:15
        _row("2024-01-01 10:15:00", 100.5, 101.5, 100.0, 101.0, 60000.0),  # 10:15-11:15
    ]
    
    def read_timeframe_side_effect(tf, from_date=None, to_date=None):
        if tf == "1M":
            return rows
        elif tf == "1H":
            return h1_rows
        return []
    
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.side_effect = read_timeframe_side_effect
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M", "1H"]
    adapter.get_origin_time.return_value = time(9, 15)  # NSE market open
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = HigherTimeframeVisibilityComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="TEST", adapter=adapter)],
        [component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
        data_orchestrator_config=DataOrchestratorConfig(min_bars_required=1)
    )
    
    engine.run()
    
    # With origin_time=09:15, the first 1H interval is 9:15-10:15 (closes at 10:15)
    # Should be visible when processing 1M candle at 10:14 (execution_time = 10:15)
    # The second 1H interval is 10:15-11:15 (closes at 11:15)
    # Should be visible when processing 1M candle at 11:14 (execution_time = 11:15)
    # Since our data goes to 11:14, both should be visible
    assert len(component.h1_candles) == 2, f"Expected 2 H1 candles, got {len(component.h1_candles)}"
    assert component.h1_candles[0].timestamp == datetime(2024, 1, 1, 9, 15), \
        f"Expected 1H candle timestamp 9:15, got {component.h1_candles[0].timestamp}"
    assert component.h1_visibility_times[0] == datetime(2024, 1, 1, 10, 15), \
        f"Expected visibility at 10:15, got {component.h1_visibility_times[0]}"
    assert component.h1_candles[1].timestamp == datetime(2024, 1, 1, 10, 15), \
        f"Expected 2nd 1H candle timestamp 10:15, got {component.h1_candles[1].timestamp}"
    assert component.h1_visibility_times[1] == datetime(2024, 1, 1, 11, 15), \
        f"Expected 2nd visibility at 11:15, got {component.h1_visibility_times[1]}"