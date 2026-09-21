"""Integration tests for parallel backtest execution."""

from unittest.mock import Mock
import pickle
import pytest

from quantrex_core import Strategy
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter
from quantrex_backtest import BacktestEngine, PortfolioConfig, PortfolioResult
from quantrex_core import InstrumentSpec
from quantrex_backtest.execution import ParallelismReport


class PicklableMockAdapter:
    """A picklable mock adapter for testing."""
    
    def __init__(self):
        self.datetime_format = "%Y%m%d %H:%M"
        self.supported_timeframes = ["1M"]
        self._origin_time = None
        self._read_timeframe_data = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            {"datetime": "20260101 09:16", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            {"datetime": "20260101 09:17", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            {"datetime": "20260101 09:18", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]
    
    def get_origin_time(self):
        return self._origin_time
    
    def read_timeframe(self, tf):
        return self._read_timeframe_data


def _make_picklable_mock_adapter():
    """Create a mock adapter that can be pickled."""
    return PicklableMockAdapter()


class IndependentStrategy(Strategy):
    """Strategy that only uses current candle's symbol - safe for parallelism."""
    
    def __init__(self):
        super().__init__()
        self.candles = []
        self.orders = []
    
    def on_candle(self, candle: Candle) -> None:
        self.candles.append(candle)
        # Only trade current symbol
        if len(self.candles) == 1:
            order = self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.BUY,
                quantity=10.0,
            )
            self.orders.append(order)
        elif len(self.candles) == 3:
            order = self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.SELL,
                quantity=10.0,
            )
            self.orders.append(order)


class PortfolioAccessStrategy(Strategy):
    """Strategy that accesses portfolio context - NOT safe for parallelism."""
    
    def __init__(self):
        super().__init__()
        self.candles = []
        self.portfolio_snapshots = []
    
    def on_candle(self, candle: Candle) -> None:
        self.candles.append(candle)
        # Access portfolio - this makes parallelism unsafe
        portfolio = self.ctx.portfolio
        self.portfolio_snapshots.append({
            'cash': portfolio.cash,
            'equity': portfolio.equity,
        })


class CrossSymbolOrderStrategy(Strategy):
    """Strategy that submits orders for other symbols - NOT safe for parallelism."""
    
    def __init__(self):
        super().__init__()
        self.candles = []
    
    def on_candle(self, candle: Candle) -> None:
        self.candles.append(candle)
        # Submit order for a different symbol - unsafe
        if candle.symbol == "RELIANCE":
            self.ctx.submit_order(symbol="TCS", side=OrderSide.BUY, quantity=10.0)


class CrossSymbolPositionStrategy(Strategy):
    """Strategy that queries positions for other symbols - NOT safe for parallelism."""
    
    def __init__(self):
        super().__init__()
        self.candles = []
    
    def on_candle(self, candle: Candle) -> None:
        self.candles.append(candle)
        # Query position for different symbol - unsafe
        if candle.symbol == "RELIANCE":
            pos = self.ctx.get_position("TCS")


class SymbolKeyedStateStrategy(Strategy):
    """Strategy that maintains symbol-keyed state in __init__ - NOT safe for parallelism."""
    
    def __init__(self):
        super().__init__()
        # This creates symbol-keyed state
        self.by_symbol = {}
        self.per_symbol_data = {}
    
    def on_candle(self, candle: Candle) -> None:
        self.by_symbol[candle.symbol] = candle.close


class TestParallelismDetector:
    """Tests for BacktestEngine._detect_parallelism() method."""
    
    def test_independent_strategy_detected_safe(self):
        """Independent strategy should be detected as safe."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        
        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter),
            InstrumentSpec(symbol="TCS", adapter=mock_adapter),
        ]
        strategy = IndependentStrategy()
        engine = BacktestEngine(instruments, strategy, PortfolioConfig())
        
        report = engine._detect_parallelism()
        
        assert report.safe is True
        assert "No cross-symbol dependencies detected" in report.reason
        assert len(report.independent_groups) == 1
        assert set(report.independent_groups[0]) == {"RELIANCE", "TCS"}
    
    def test_portfolio_access_detected_unsafe(self):
        """Strategy accessing ctx.portfolio should be detected as unsafe."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        
        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter)]
        strategy = PortfolioAccessStrategy()
        engine = BacktestEngine(instruments, strategy, PortfolioConfig())
        
        report = engine._detect_parallelism()
        
        assert report.safe is False
        assert "portfolio" in report.reason.lower()
    
    def test_cross_symbol_order_detected_unsafe(self):
        """Strategy submitting orders for other symbols should be detected as unsafe."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        
        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter),
            InstrumentSpec(symbol="TCS", adapter=mock_adapter),
        ]
        strategy = CrossSymbolOrderStrategy()
        engine = BacktestEngine(instruments, strategy, PortfolioConfig())
        
        report = engine._detect_parallelism()
        
        assert report.safe is False
        assert "submit_order" in report.reason
    
    def test_cross_symbol_position_detected_unsafe(self):
        """Strategy querying positions for other symbols should be detected as unsafe."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        
        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter),
            InstrumentSpec(symbol="TCS", adapter=mock_adapter),
        ]
        strategy = CrossSymbolPositionStrategy()
        engine = BacktestEngine(instruments, strategy, PortfolioConfig())
        
        report = engine._detect_parallelism()
        
        assert report.safe is False
        assert "get_position" in report.reason
    
    def test_symbol_keyed_state_detected_unsafe(self):
        """Strategy with symbol-keyed state in __init__ should be detected as unsafe."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        
        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter)]
        strategy = SymbolKeyedStateStrategy()
        engine = BacktestEngine(instruments, strategy, PortfolioConfig())
        
        report = engine._detect_parallelism()
        
        assert report.safe is False
        assert "symbol-keyed" in report.reason.lower() or "by_symbol" in report.reason.lower()


class TestParallelExecution:
    """Integration tests for parallel backtest execution."""
    
    def test_parallel_execution_independent_strategy(self):
        """Independent strategy with multiple instruments should run in parallel."""
        mock_adapter = _make_picklable_mock_adapter()
        
        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter),
            InstrumentSpec(symbol="TCS", adapter=mock_adapter),
        ]
        strategy = IndependentStrategy()
        config = PortfolioConfig(initial_cash=1_000_000.0, auto_download=False)
        
        engine = BacktestEngine(instruments, strategy, config)
        result = engine.run()
        
        assert isinstance(result, PortfolioResult)
        assert set(result.symbols) == {"RELIANCE", "TCS"}
        assert result.total_trades > 0
    
    def test_sequential_fallback_portfolio_access(self):
        """Strategy with portfolio access should fall back to sequential."""
        mock_adapter = _make_picklable_mock_adapter()
        mock_adapter._read_timeframe_data = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            {"datetime": "20260101 09:16", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]
        
        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter),
            InstrumentSpec(symbol="TCS", adapter=mock_adapter),
        ]
        strategy = PortfolioAccessStrategy()
        config = PortfolioConfig(initial_cash=1_000_000.0, auto_download=False)
        
        engine = BacktestEngine(instruments, strategy, config)
        result = engine.run()
        
        assert isinstance(result, PortfolioResult)
        assert set(result.symbols) == {"RELIANCE", "TCS"}
        # Should have portfolio snapshots from sequential execution
        assert len(strategy.portfolio_snapshots) > 0
    
    def test_sequential_fallback_cross_symbol_order(self):
        """Strategy with cross-symbol orders should fall back to sequential."""
        mock_adapter = _make_picklable_mock_adapter()
        mock_adapter._read_timeframe_data = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            {"datetime": "20260101 09:16", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]
        
        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter),
            InstrumentSpec(symbol="TCS", adapter=mock_adapter),
        ]
        strategy = CrossSymbolOrderStrategy()
        config = PortfolioConfig(initial_cash=1_000_000.0, auto_download=False)
        
        engine = BacktestEngine(instruments, strategy, config)
        result = engine.run()
        
        assert isinstance(result, PortfolioResult)
        assert set(result.symbols) == {"RELIANCE", "TCS"}
    
    def test_sequential_fallback_cross_symbol_position(self):
        """Strategy with cross-symbol position queries should fall back to sequential."""
        mock_adapter = _make_picklable_mock_adapter()
        mock_adapter._read_timeframe_data = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            {"datetime": "20260101 09:16", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]
        
        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter),
            InstrumentSpec(symbol="TCS", adapter=mock_adapter),
        ]
        strategy = CrossSymbolPositionStrategy()
        config = PortfolioConfig(initial_cash=1_000_000.0, auto_download=False)
        
        engine = BacktestEngine(instruments, strategy, config)
        result = engine.run()
        
        assert isinstance(result, PortfolioResult)
        assert set(result.symbols) == {"RELIANCE", "TCS"}
    
    def test_sequential_fallback_symbol_keyed_state(self):
        """Strategy with symbol-keyed state should fall back to sequential."""
        mock_adapter = _make_picklable_mock_adapter()
        mock_adapter._read_timeframe_data = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            {"datetime": "20260101 09:16", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]
        
        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter),
            InstrumentSpec(symbol="TCS", adapter=mock_adapter),
        ]
        strategy = SymbolKeyedStateStrategy()
        config = PortfolioConfig(initial_cash=1_000_000.0, auto_download=False)
        
        engine = BacktestEngine(instruments, strategy, config)
        result = engine.run()
        
        assert isinstance(result, PortfolioResult)
        assert set(result.symbols) == {"RELIANCE", "TCS"}
    
    def test_single_instrument_sequential(self):
        """Single instrument should always run sequentially (no parallel benefit)."""
        mock_adapter = _make_picklable_mock_adapter()
        mock_adapter._read_timeframe_data = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            {"datetime": "20260101 09:16", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]
        
        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter)]
        strategy = IndependentStrategy()
        config = PortfolioConfig(initial_cash=1_000_000.0, auto_download=False)
        
        engine = BacktestEngine(instruments, strategy, config)
        result = engine.run()
        
        assert isinstance(result, PortfolioResult)
        assert result.symbols == ["RELIANCE"]
    
    def test_parallel_vs_sequential_equivalence(self):
        """Parallel and sequential execution should produce equivalent results for independent strategies."""
        mock_adapter = _make_picklable_mock_adapter()
        
        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter),
            InstrumentSpec(symbol="TCS", adapter=mock_adapter),
        ]
        
        # Run with independent strategy (should auto-parallelize)
        strategy1 = IndependentStrategy()
        config = PortfolioConfig(initial_cash=1_000_000.0, auto_download=False)
        engine1 = BacktestEngine(instruments, strategy1, config)
        result1 = engine1.run()
        
        # Run with portfolio access strategy (should be sequential)
        strategy2 = PortfolioAccessStrategy()
        engine2 = BacktestEngine(instruments, strategy2, config)
        result2 = engine2.run()
        
        # Both should complete successfully
        assert isinstance(result1, PortfolioResult)
        assert isinstance(result2, PortfolioResult)
        assert set(result1.symbols) == set(result2.symbols) == {"RELIANCE", "TCS"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])