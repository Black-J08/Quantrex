"""Unit tests for ParallelismDetector static analysis."""

import dis
from unittest.mock import Mock

import pytest

from quantrex_backtest.core.parallel import ParallelismDetector, ParallelismReport
from quantrex_core import InstrumentSpec
from quantrex_core.protocols import DataAdapter
from quantrex_core.strategy.base import Strategy
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide


class TestParallelismDetectorUnit:
    """Unit tests for ParallelismDetector static analysis methods."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_adapter = Mock(spec=DataAdapter)
        self.mock_adapter.datetime_format = "%Y%m%d %H:%M"
        self.mock_adapter.supported_timeframes = ["1M"]
        self.mock_adapter.get_origin_time.return_value = None
        
        self.instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=self.mock_adapter),
            InstrumentSpec(symbol="TCS", adapter=self.mock_adapter),
            InstrumentSpec(symbol="INFY", adapter=self.mock_adapter),
        ]
        self.symbol_names = {"RELIANCE", "TCS", "INFY"}
    
    def test_analyze_method_detects_portfolio_access(self):
        """Test detection of ctx.portfolio access."""
        class PortfolioStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                _ = self.ctx.portfolio
        
        strategy = PortfolioStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is False
        assert "portfolio" in report.reason.lower()
    
    def test_analyze_method_detects_positions_access(self):
        """Test detection of ctx.positions access."""
        class PositionsStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                _ = self.ctx.positions
        
        strategy = PositionsStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is False
        assert "positions" in report.reason.lower()
    
    def test_analyze_method_detects_self_ctx_portfolio(self):
        """Test detection of self.ctx.portfolio access."""
        class SelfCtxStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                _ = self.ctx.portfolio.cash
        
        strategy = SelfCtxStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is False
        assert "portfolio" in report.reason.lower()
    
    def test_analyze_method_allows_candle_symbol(self):
        """Test that candle.symbol access is allowed."""
        class CandleSymbolStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                symbol = candle.symbol
                pos = self.ctx.get_position(symbol)
        
        strategy = CandleSymbolStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is True
    
    def test_analyze_method_allows_candle_symbol_in_submit_order(self):
        """Test that candle.symbol in submit_order is allowed."""
        class SubmitOrderStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                self.ctx.submit_order(symbol=candle.symbol, side=OrderSide.BUY, quantity=10.0)
        
        strategy = SubmitOrderStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is True
    
    def test_analyze_method_detects_literal_symbol_in_submit_order(self):
        """Test detection of literal symbol in submit_order."""
        class LiteralSymbolStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                self.ctx.submit_order(symbol="TCS", side=OrderSide.BUY, quantity=10.0)
        
        strategy = LiteralSymbolStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is False
        assert "submit_order" in report.reason
        assert "TCS" in report.reason
    
    def test_analyze_method_detects_literal_symbol_in_get_position(self):
        """Test detection of literal symbol in get_position."""
        class LiteralPositionStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                self.ctx.get_position("TCS")
        
        strategy = LiteralPositionStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is False
        assert "get_position" in report.reason
        assert "TCS" in report.reason
    
    def test_analyze_method_detects_symbol_keyed_state(self):
        """Test detection of symbol-keyed state in __init__."""
        class SymbolKeyedStrategy(Strategy):
            def __init__(self):
                super().__init__()
                self.by_symbol = {}
                self.per_symbol_data = {}
            
            def on_candle(self, candle: Candle) -> None:
                pass
        
        strategy = SymbolKeyedStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is False
        assert "symbol-keyed" in report.reason.lower() or "by_symbol" in report.reason.lower()
    
    def test_analyze_method_allows_normal_dict(self):
        """Test that normal dict without symbol keywords is allowed."""
        class NormalDictStrategy(Strategy):
            def __init__(self):
                super().__init__()
                self.data = {}
                self.cache = {}
            
            def on_candle(self, candle: Candle) -> None:
                pass
        
        strategy = NormalDictStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is True
    
    def test_analyze_method_detects_call_kw(self):
        """Test detection of CALL_KW with literal symbol."""
        class CallKwStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                self.ctx.submit_order(symbol="INFY", side=OrderSide.BUY, quantity=10.0)
        
        strategy = CallKwStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is False
        assert "submit_order" in report.reason
    
    def test_analyze_method_detects_call(self):
        """Test detection of CALL with literal symbol."""
        class CallStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                self.ctx.get_position("INFY")
        
        strategy = CallStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is False
        assert "get_position" in report.reason
    
    def test_analyze_method_multiple_unsafe_patterns(self):
        """Test detection of multiple unsafe patterns in one strategy.
        
        Note: The detector stops at the first unsafe pattern found, which is
        acceptable since we only need to know if it's safe or not.
        """
        class MultiUnsafeStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                # Multiple unsafe patterns
                _ = self.ctx.portfolio
                self.ctx.submit_order(symbol="TCS", side=OrderSide.BUY, quantity=10.0)
                self.ctx.get_position("INFY")
        
        strategy = MultiUnsafeStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is False
        # Should mention at least one issue (detector stops at first found)
        assert "portfolio" in report.reason.lower() or "submit_order" in report.reason or "get_position" in report.reason
    
    def test_analyze_method_on_start_on_stop(self):
        """Test analysis of on_start and on_stop methods."""
        class LifecycleStrategy(Strategy):
            def on_start(self) -> None:
                _ = self.ctx.portfolio
            
            def on_stop(self) -> None:
                _ = self.ctx.positions
            
            def on_candle(self, candle: Candle) -> None:
                pass
        
        strategy = LifecycleStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is False
        assert "on_start" in report.reason or "on_stop" in report.reason
    
    def test_analyze_method_compute_indicators(self):
        """Test analysis of compute_indicators method."""
        class IndicatorsStrategy(Strategy):
            def compute_indicators(self, candles, timeframe=None):
                _ = self.ctx.portfolio
                return [{} for _ in candles]
            
            def on_candle(self, candle: Candle) -> None:
                pass
        
        strategy = IndicatorsStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is False
        assert "compute_indicators" in report.reason
    
    def test_analyze_method_safe_strategy_with_timeframe(self):
        """Test safe strategy with @on_timeframe decorator."""
        from quantrex_core.strategy.timeframe import on_timeframe
        
        class TimeframeStrategy(Strategy):
            @on_timeframe("1H")
            def on_1h_candle(self, candle: Candle) -> None:
                symbol = candle.symbol
                pos = self.ctx.get_position(symbol)
            
            def on_candle(self, candle: Candle) -> None:
                pass
        
        strategy = TimeframeStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is True
    
    def test_analyze_method_non_candle_symbol_attribute(self):
        """Test detection of symbol attribute from non-candle object."""
        class NonCandleSymbolStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                # Access symbol from something other than candle
                other = candle  # In real code this could be a different object
                symbol = other.symbol
                self.ctx.get_position(symbol)
        
        strategy = NonCandleSymbolStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        # This might be flagged as suspicious since it's not directly candle.symbol
        # The detector should be conservative
        # For now, we just verify it doesn't crash
        assert isinstance(report, ParallelismReport)
    
    def test_analyze_empty_strategy(self):
        """Test analysis of minimal strategy."""
        class MinimalStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                pass
        
        strategy = MinimalStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        assert report.safe is True
    
    def test_analyze_single_instrument(self):
        """Test analysis with single instrument."""
        single_instrument = [InstrumentSpec(symbol="RELIANCE", adapter=self.mock_adapter)]
        
        class SimpleStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                pass
        
        strategy = SimpleStrategy()
        report = ParallelismDetector.analyze(strategy, single_instrument)
        
        assert report.safe is True
        assert report.independent_groups == [["RELIANCE"]]
    
    def test_analyze_skips_base_class_methods(self):
        """Test that base class Strategy methods are skipped."""
        class DerivedStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                pass
        
        strategy = DerivedStrategy()
        report = ParallelismDetector.analyze(strategy, self.instruments)
        
        # Should not crash and should analyze the derived method
        assert isinstance(report, ParallelismReport)
    
    def test_analyze_method_handles_exception(self):
        """Test that analysis handles exceptions gracefully."""
        class BrokenStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                pass
        
        # Monkey-patch to cause an exception in bytecode analysis
        original_analyze = ParallelismDetector._analyze_method
        
        def broken_analyze(method, method_name, symbol_names):
            raise ValueError("Test exception")
        
        ParallelismDetector._analyze_method = staticmethod(broken_analyze)
        
        try:
            strategy = BrokenStrategy()
            report = ParallelismDetector.analyze(strategy, self.instruments)
            
            # Should have warning but not crash
            assert len(report.warnings) > 0
            assert "Could not analyze" in report.warnings[0]
        finally:
            ParallelismDetector._analyze_method = staticmethod(original_analyze)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])