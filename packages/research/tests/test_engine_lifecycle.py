"""Tests for ResearchEngine - Lifecycle."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig
from quantrex_backtest import InstrumentSpec, BacktestConfig


class LifecycleComponent(ForwardReturnComponent):
    """Component that tracks lifecycle calls."""
    
    def __init__(self, config):
        super().__init__(config)
        self.started = False
        self.stopped = False
        self.candles_processed = 0
    
    def on_start(self) -> None:
        self.started = True
        super().on_start()
    
    def on_candle(self, candle: Candle) -> None:
        self.candles_processed += 1
    
    def on_stop(self, output_dir) -> None:
        self.stopped = True
        return super().on_stop(output_dir)


def test_engine_calls_lifecycle_methods():
    """Engine should call on_start before and on_stop after processing."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = LifecycleComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    assert component.started is True
    assert component.stopped is True
    assert component.candles_processed == 2


def test_engine_on_start_before_first_candle():
    """on_start should be called before any on_candle."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    call_order = []
    
    class OrderComponent(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
        
        def on_start(self) -> None:
            call_order.append("on_start")
            super().on_start()
        
        def on_candle(self, candle: Candle) -> None:
            call_order.append("on_candle")
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = OrderComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    assert call_order == ["on_start", "on_candle"]


def test_engine_on_stop_after_last_candle():
    """on_stop should be called after all on_candle calls."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    call_order = []
    
    class OrderComponent(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
        
        def on_candle(self, candle: Candle) -> None:
            call_order.append("on_candle")
        
        def on_stop(self, output_dir) -> None:
            call_order.append("on_stop")
            return super().on_stop(output_dir)
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = OrderComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    engine.run()
    
    assert call_order == ["on_candle", "on_candle", "on_stop"]


def test_engine_copies_script_to_output_dir():
    """Engine should copy the research script to each component's output directory."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    
    class ScriptCopyComponent(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.started = False
            self.stopped = False
            self.candles_processed = 0
        
        def on_start(self) -> None:
            self.started = True
            super().on_start()
        
        def on_candle(self, candle: Candle) -> None:
            self.candles_processed += 1
        
        def on_stop(self, output_dir) -> None:
            self.stopped = True
            return super().on_stop(output_dir)
    
    component = ScriptCopyComponent(config)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("# Test research script\nprint('hello')\n")
        script_path = f.name
    
    try:
        engine = ResearchEngine(
            instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
            research_components=[component],
            data_start="2024-01-01",
            data_end="2024-01-02",
            backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
            script_path=script_path,
        )
        
        engine.run()
        
        # Check script was copied to component output directory (use most recent)
        output_base = Path("output/research")
        component_dirs = list(output_base.glob(f"{component.__class__.__name__}/*"))
        assert len(component_dirs) >= 1
        latest_dir = max(component_dirs, key=lambda d: d.stat().st_mtime)
        script_dest = latest_dir / "research_script.py"
        assert script_dest.exists()
        assert script_dest.read_text() == "# Test research script\nprint('hello')\n"
    finally:
        Path(script_path).unlink(missing_ok=True)


def test_engine_no_script_path_no_copy():
    """Engine should not attempt copy when script_path is None."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    
    class NoScriptComponent(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.started = False
            self.stopped = False
            self.candles_processed = 0
        
        def on_start(self) -> None:
            self.started = True
            super().on_start()
        
        def on_candle(self, candle: Candle) -> None:
            self.candles_processed += 1
        
        def on_stop(self, output_dir) -> None:
            self.stopped = True
            return super().on_stop(output_dir)
    
    component = NoScriptComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
        script_path=None,
    )
    
    engine.run()
    
    # Check no script was copied (use most recent dir)
    output_base = Path("output/research")
    component_dirs = list(output_base.glob(f"{component.__class__.__name__}/*"))
    assert len(component_dirs) >= 1
    latest_dir = max(component_dirs, key=lambda d: d.stat().st_mtime)
    script_dest = latest_dir / "research_script.py"
    assert not script_dest.exists()


def test_engine_invalid_script_path_logs_warning():
    """Engine should log warning and continue when script_path doesn't exist."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    
    class InvalidScriptComponent(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.started = False
            self.stopped = False
            self.candles_processed = 0
        
        def on_start(self) -> None:
            self.started = True
            super().on_start()
        
        def on_candle(self, candle: Candle) -> None:
            self.candles_processed += 1
        
        def on_stop(self, output_dir) -> None:
            self.stopped = True
            return super().on_stop(output_dir)
    
    component = InvalidScriptComponent(config)
    
    engine = ResearchEngine(
        instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
        script_path="/nonexistent/path/script.py",
    )
    
    # Should not raise, just log warning
    engine.run()
    
    # Check run completed successfully
    assert component.stopped is True
    output_base = Path("output/research")
    component_dirs = list(output_base.glob(f"{component.__class__.__name__}/*"))
    assert len(component_dirs) >= 1
    latest_dir = max(component_dirs, key=lambda d: d.stat().st_mtime)
    script_dest = latest_dir / "research_script.py"
    assert not script_dest.exists()


def test_engine_multiple_components_each_get_script_copy():
    """Each component should get its own copy of the script."""
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
    ]
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    
    class MultiComponent1(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.started = False
            self.stopped = False
            self.candles_processed = 0
        
        def on_start(self) -> None:
            self.started = True
            super().on_start()
        
        def on_candle(self, candle: Candle) -> None:
            self.candles_processed += 1
        
        def on_stop(self, output_dir) -> None:
            self.stopped = True
            return super().on_stop(output_dir)
    
    class MultiComponent2(ForwardReturnComponent):
        def __init__(self, config):
            super().__init__(config)
            self.started = False
            self.stopped = False
            self.candles_processed = 0
        
        def on_start(self) -> None:
            self.started = True
            super().on_start()
        
        def on_candle(self, candle: Candle) -> None:
            self.candles_processed += 1
        
        def on_stop(self, output_dir) -> None:
            self.stopped = True
            return super().on_stop(output_dir)
    
    component1 = MultiComponent1(config)
    component2 = MultiComponent2(config)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("# Test research script\nprint('hello')\n")
        script_path = f.name
    
    try:
        engine = ResearchEngine(
            instruments=[InstrumentSpec(symbol="SYM1", adapter=adapter)],
            research_components=[component1, component2],
            data_start="2024-01-01",
            data_end="2024-01-02",
            backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
            script_path=script_path,
        )
        
        engine.run()
        
        # Check both components got script copy (use most recent dir for each)
        output_base = Path("output/research")
        for component in [component1, component2]:
            component_dirs = list(output_base.glob(f"{component.__class__.__name__}/*"))
            assert len(component_dirs) >= 1
            latest_dir = max(component_dirs, key=lambda d: d.stat().st_mtime)
            script_dest = latest_dir / "research_script.py"
            assert script_dest.exists()
            assert script_dest.read_text() == "# Test research script\nprint('hello')\n"
    finally:
        Path(script_path).unlink(missing_ok=True)