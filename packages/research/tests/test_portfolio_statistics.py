"""Regression tests for portfolio statistics accuracy."""

from datetime import datetime, timedelta
from unittest.mock import Mock

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig
from quantrex_backtest import InstrumentSpec, BacktestConfig


class SimpleEventComponent(ForwardReturnComponent):
    """Component that emits one event per symbol at a known time."""
    
    def __init__(self, config):
        super().__init__(config)
        self.events_emitted = {}
    
    def compute_indicators(self, candles, timeframe: str = "1M", symbol: str | None = None):
        return [{} for _ in candles]
    
    def on_candle(self, candle: Candle) -> None:
        # Emit event for each symbol at 9:15
        if candle.timestamp == datetime(2024, 1, 1, 9, 15):
            if candle.symbol not in self.events_emitted:
                self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, 
                               {"test": True}, emission_candle=candle)
                self.events_emitted[candle.symbol] = True
    
    def on_stop(self, output_dir):
        # Call parent to get ForwardReturnResult with statistics
        result = super().on_stop(output_dir)
        # Store tracking info on component for test access
        self._test_events_emitted = self.events_emitted
        return result


def test_portfolio_statistics_per_symbol_accuracy():
    """Portfolio statistics should accurately reflect per-symbol forward returns."""
    # SYM1: 100 -> 101 -> 102 (1% then 2% returns)
    # SYM2: 200 -> 202 -> 204 (1% then 2% returns)
    # Both have same percentage returns but different absolute prices
    
    adapter1 = Mock(spec=DataAdapter)
    adapter1.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
        {"datetime": "2024-01-01 09:17:00", "open": "102", "high": "103", "low": "101", "close": "102", "volume": "100"},
    ]
    adapter1.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter1.supported_timeframes = ["1M"]
    adapter1.get_origin_time.return_value = None
    
    adapter2 = Mock(spec=DataAdapter)
    adapter2.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "200", "high": "202", "low": "198", "close": "200", "volume": "200"},
        {"datetime": "2024-01-01 09:16:00", "open": "202", "high": "204", "low": "200", "close": "202", "volume": "200"},
        {"datetime": "2024-01-01 09:17:00", "open": "204", "high": "206", "low": "202", "close": "204", "volume": "200"},
    ]
    adapter2.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter2.supported_timeframes = ["1M"]
    adapter2.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1), timedelta(minutes=2)])
    component = SimpleEventComponent(config)
    
    engine = ResearchEngine(
        instruments=[
            InstrumentSpec(symbol="SYM1", adapter=adapter1),
            InstrumentSpec(symbol="SYM2", adapter=adapter2),
        ],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    results = engine.run()
    
    # Get the aggregated result
    result = results["SimpleEventComponent"]
    component = engine.research_components[0]
    
    # Both symbols should have 1% return at 1min and 2% return at 2min
    # SYM1: (101-100)/100*100 = 1%, (102-100)/100*100 = 2%
    # SYM2: (202-200)/200*100 = 1%, (204-200)/200*100 = 2%
    
    stats_1min = result.horizon_stats[timedelta(minutes=1)]
    stats_2min = result.horizon_stats[timedelta(minutes=2)]
    
    # Mean should be 1.0% for 1min, 2.0% for 2min
    assert abs(stats_1min["mean"] - 1.0) < 0.01, f"Expected mean 1.0% at 1min, got {stats_1min['mean']}"
    assert abs(stats_2min["mean"] - 2.0) < 0.01, f"Expected mean 2.0% at 2min, got {stats_2min['mean']}"
    
    # Count should be 2 (one per symbol)
    assert stats_1min["count"] == 2, f"Expected count 2 at 1min, got {stats_1min['count']}"
    assert stats_2min["count"] == 2, f"Expected count 2 at 2min, got {stats_2min['count']}"
    
    # Raw returns should have 2 values each
    assert len(result.raw_returns[timedelta(minutes=1)]) == 2
    assert len(result.raw_returns[timedelta(minutes=2)]) == 2
    
    # All returns should be ~1% and ~2%
    for ret in result.raw_returns[timedelta(minutes=1)]:
        assert abs(ret - 1.0) < 0.01, f"Expected ~1.0% return, got {ret}"
    for ret in result.raw_returns[timedelta(minutes=2)]:
        assert abs(ret - 2.0) < 0.01, f"Expected ~2.0% return, got {ret}"
    
    # Verify events were emitted for both symbols
    assert component._test_events_emitted.get("SYM1") is True
    assert component._test_events_emitted.get("SYM2") is True


def test_portfolio_statistics_different_returns_per_symbol():
    """Portfolio statistics should correctly aggregate different returns per symbol."""
    # SYM1: 100 -> 101 (1% return)
    # SYM2: 200 -> 204 (2% return)
    
    adapter1 = Mock(spec=DataAdapter)
    adapter1.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
    ]
    adapter1.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter1.supported_timeframes = ["1M"]
    adapter1.get_origin_time.return_value = None
    
    adapter2 = Mock(spec=DataAdapter)
    adapter2.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "200", "high": "204", "low": "198", "close": "200", "volume": "200"},
        {"datetime": "2024-01-01 09:16:00", "open": "204", "high": "206", "low": "202", "close": "204", "volume": "200"},
    ]
    adapter2.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter2.supported_timeframes = ["1M"]
    adapter2.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = SimpleEventComponent(config)
    
    engine = ResearchEngine(
        instruments=[
            InstrumentSpec(symbol="SYM1", adapter=adapter1),
            InstrumentSpec(symbol="SYM2", adapter=adapter2),
        ],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    results = engine.run()
    result = results["SimpleEventComponent"]
    component = engine.research_components[0]
    
    stats_1min = result.horizon_stats[timedelta(minutes=1)]
    
    # Mean should be (1% + 2%) / 2 = 1.5%
    assert abs(stats_1min["mean"] - 1.5) < 0.01, f"Expected mean 1.5%, got {stats_1min['mean']}"
    
    # Raw returns should be [1.0, 2.0]
    raw_returns = result.raw_returns[timedelta(minutes=1)]
    assert len(raw_returns) == 2
    assert abs(raw_returns[0] - 1.0) < 0.01 or abs(raw_returns[1] - 1.0) < 0.01
    assert abs(raw_returns[0] - 2.0) < 0.01 or abs(raw_returns[1] - 2.0) < 0.01
    
    # Verify events were emitted for both symbols
    assert component._test_events_emitted.get("SYM1") is True
    assert component._test_events_emitted.get("SYM2") is True


def test_portfolio_no_cross_symbol_contamination():
    """Verify no cross-symbol contamination: SYM1 event uses SYM1 candles only."""
    # SYM1: 100 -> 101 (1% return)
    # SYM2: 200 -> 210 (5% return) - very different!
    # If cross-contamination occurs, SYM1 event might use SYM2's 210 price
    # giving (210-100)/100*100 = 110% return (WRONG)
    
    adapter1 = Mock(spec=DataAdapter)
    adapter1.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"},
        {"datetime": "2024-01-01 09:16:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "100"},
    ]
    adapter1.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter1.supported_timeframes = ["1M"]
    adapter1.get_origin_time.return_value = None
    
    adapter2 = Mock(spec=DataAdapter)
    adapter2.read_timeframe.return_value = [
        {"datetime": "2024-01-01 09:15:00", "open": "200", "high": "210", "low": "198", "close": "200", "volume": "200"},
        {"datetime": "2024-01-01 09:16:00", "open": "210", "high": "215", "low": "205", "close": "210", "volume": "200"},
    ]
    adapter2.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter2.supported_timeframes = ["1M"]
    adapter2.get_origin_time.return_value = None
    
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = SimpleEventComponent(config)
    
    engine = ResearchEngine(
        instruments=[
            InstrumentSpec(symbol="SYM1", adapter=adapter1),
            InstrumentSpec(symbol="SYM2", adapter=adapter2),
        ],
        research_components=[component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    results = engine.run()
    result = results["SimpleEventComponent"]
    component = engine.research_components[0]
    
    stats_1min = result.horizon_stats[timedelta(minutes=1)]
    raw_returns = result.raw_returns[timedelta(minutes=1)]
    
    # Should have returns ~1% (SYM1) and ~5% (SYM2)
    # NOT 110% (cross-contaminated)
    assert len(raw_returns) == 2
    
    # Check both expected returns are present
    has_1pct = any(abs(r - 1.0) < 0.01 for r in raw_returns)
    has_5pct = any(abs(r - 5.0) < 0.01 for r in raw_returns)
    
    assert has_1pct, f"Missing SYM1's ~1% return. Got: {raw_returns}"
    assert has_5pct, f"Missing SYM2's ~5% return. Got: {raw_returns}"
    
    # Mean should be (1% + 5%) / 2 = 3%
    assert abs(stats_1min["mean"] - 3.0) < 0.01, f"Expected mean 3.0%, got {stats_1min['mean']}"
    
    # No return should be anywhere near 110% (cross-contamination indicator)
    for r in raw_returns:
        assert r < 50, f"Suspiciously high return {r}% indicates cross-symbol contamination"
    
    # Verify events were emitted for both symbols
    assert component._test_events_emitted.get("SYM1") is True
    assert component._test_events_emitted.get("SYM2") is True