"""Tests for unified BacktestEngine portfolio mode."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from quantrex_core import Strategy
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter
from quantrex_backtest import BacktestEngine, PortfolioConfig, PortfolioResult
from quantrex_core import InstrumentSpec
from quantrex_test_support.csv import make_ohlc_series, csv_rows_to_string, create_temp_csv


class TestStrategy(Strategy):
    """Test strategy that records received candles."""
    
    def __init__(self):
        super().__init__()
        self.candles = []
        self.started = False
        self.stopped = False
    
    def on_start(self) -> None:
        self.started = True
    
    def on_candle(self, candle: Candle) -> None:
        self.candles.append(candle)
    
    def on_stop(self) -> None:
        self.stopped = True


class TestBacktestEnginePortfolioMode:
    """Tests for BacktestEngine in portfolio mode."""

    def test_portfolio_mode_initialization(self):
        """Test BacktestEngine initialization in portfolio mode."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None

        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter),
            InstrumentSpec(symbol="TCS", adapter=mock_adapter),
        ]
        strategy = TestStrategy()
        config = PortfolioConfig(initial_cash=1_000_000.0)

        engine = BacktestEngine(instruments, strategy, config)

        assert engine._is_portfolio_mode is True
        assert len(engine._instruments) == 2
        assert engine._config.initial_cash == 1_000_000.0

    def test_portfolio_mode_single_instrument(self):
        """Test portfolio mode with single instrument."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None

        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter)]
        strategy = TestStrategy()
        config = PortfolioConfig(initial_cash=1_000_000.0)

        engine = BacktestEngine(instruments, strategy, config)

        assert engine._is_portfolio_mode is True
        assert len(engine._instruments) == 1

    def test_portfolio_mode_requires_instruments(self):
        """Test portfolio mode requires at least one instrument."""
        mock_adapter = Mock(spec=DataAdapter)
        strategy = TestStrategy()
        config = PortfolioConfig()

        with pytest.raises(Exception) as exc_info:
            BacktestEngine([], strategy, config)
        assert "At least one instrument required" in str(exc_info.value)

    def test_portfolio_mode_requires_adapters(self):
        """Test portfolio mode requires adapters for all instruments."""
        from quantrex_core import InstrumentSpec
        from quantrex_core.protocols import DataAdapter

        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=None)]
        strategy = TestStrategy()
        config = PortfolioConfig()

        with pytest.raises(Exception) as exc_info:
            BacktestEngine(instruments, strategy, config)
        assert "DataAdapter required" in str(exc_info.value)

    def test_portfolio_mode_run_returns_portfolio_result(self):
        """Test portfolio mode run returns PortfolioResult."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        mock_adapter.read_timeframe.return_value = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            {"datetime": "20260101 09:16", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]

        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter)]
        strategy = TestStrategy()
        config = PortfolioConfig(initial_cash=1_000_000.0, auto_download=False)

        engine = BacktestEngine(instruments, strategy, config)
        result = engine.run()

        assert isinstance(result, PortfolioResult)
        assert result.initial_cash == 1_000_000.0
        assert result.symbols == ["RELIANCE"]

    def test_portfolio_mode_multiple_instruments(self):
        """Test portfolio mode with multiple instruments."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        mock_adapter.read_timeframe.return_value = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            {"datetime": "20260101 09:16", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]

        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter),
            InstrumentSpec(symbol="TCS", adapter=mock_adapter),
        ]
        strategy = TestStrategy()
        config = PortfolioConfig(initial_cash=1_000_000.0, auto_download=False)

        engine = BacktestEngine(instruments, strategy, config)
        result = engine.run()

        assert isinstance(result, PortfolioResult)
        assert set(result.symbols) == {"RELIANCE", "TCS"}

    def test_portfolio_mode_strategy_receives_portfolio_context(self):
        """Test strategy receives portfolio context with portfolio property."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        mock_adapter.read_timeframe.return_value = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]

        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter)]
        
        class PortfolioAwareStrategy(Strategy):
            def __init__(self):
                super().__init__()
                self.portfolio_snapshots = []
            
            def on_candle(self, candle: Candle) -> None:
                # Access portfolio context
                portfolio = self.ctx.portfolio
                self.portfolio_snapshots.append({
                    'cash': portfolio.cash,
                    'equity': portfolio.equity,
                    'positions': dict(portfolio.positions),
                })

        strategy = PortfolioAwareStrategy()
        config = PortfolioConfig(initial_cash=1_000_000.0, auto_download=False)

        engine = BacktestEngine(
            [InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter)],
            strategy,
            PortfolioConfig(initial_cash=1_000_000.0, auto_download=False),
        )
        result = engine.run()

        # Strategy should have received portfolio context
        assert len(strategy.portfolio_snapshots) > 0
        for snapshot in strategy.portfolio_snapshots:
            assert 'cash' in snapshot
            assert 'equity' in snapshot
            assert 'positions' in snapshot

    def test_portfolio_mode_backward_compatibility(self):
        """Test single-instrument mode still works (backward compatibility)."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        mock_adapter.read_timeframe.return_value = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]

        strategy = TestStrategy()
        engine = BacktestEngine(mock_adapter, strategy, symbol="RELIANCE")

        assert engine._is_portfolio_mode is False
        assert engine._symbol == "RELIANCE"
        assert len(engine._instruments) == 1

        result = engine.run()
        assert isinstance(result, PortfolioResult)
        assert result.symbols == ["RELIANCE"]


class TestBacktestEnginePortfolioModeEdgeCases:
    """Tests for edge cases in portfolio mode."""

    def test_portfolio_mode_empty_data(self):
        """Test portfolio mode with empty data raises ValueError."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        mock_adapter.read_timeframe.return_value = []

        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter)]
        strategy = TestStrategy()
        config = PortfolioConfig(auto_download=False)

        engine = BacktestEngine(instruments, strategy, config)
        
        with pytest.raises(ValueError) as exc_info:
            engine.run()
        assert "No data rows provided" in str(exc_info.value)

    def test_portfolio_mode_mismatched_timestamps(self):
        """Test portfolio mode with mismatched timestamps across symbols."""
        mock_adapter1 = Mock(spec=DataAdapter)
        mock_adapter1.datetime_format = "%Y%m%d %H:%M"
        mock_adapter1.supported_timeframes = ["1M"]
        mock_adapter1.get_origin_time.return_value = None
        mock_adapter1.read_timeframe.return_value = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            {"datetime": "20260101 09:16", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]

        mock_adapter2 = Mock(spec=DataAdapter)
        mock_adapter2.datetime_format = "%Y%m%d %H:%M"
        mock_adapter2.supported_timeframes = ["1M"]
        mock_adapter2.get_origin_time.return_value = None
        mock_adapter2.read_timeframe.return_value = [
            {"datetime": "20260101 09:15", "open": "3000", "high": "3001", "low": "2999", "close": "3000", "volume": "1000"},
            # Missing 09:16 timestamp
        ]

        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter1),
            InstrumentSpec(symbol="TCS", adapter=mock_adapter2),
        ]
        strategy = TestStrategy()
        config = PortfolioConfig(auto_download=False)

        engine = BacktestEngine(instruments, strategy, config)
        result = engine.run()

        # Should handle mismatched timestamps gracefully
        assert isinstance(result, PortfolioResult)