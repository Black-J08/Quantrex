"""Tests for unified BacktestEngine portfolio mode."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from quantrex_core import Strategy
from quantrex_core.models import Candle
from quantrex_core.protocols import DataAdapter
from quantrex_backtest import BacktestEngine, BacktestConfig, BacktestResult
from quantrex_core import InstrumentSpec


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
        config = BacktestConfig(initial_cash=1_000_000.0)

        engine = BacktestEngine(instruments, strategy, config)

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
        config = BacktestConfig(initial_cash=1_000_000.0)

        engine = BacktestEngine(instruments, strategy, config)

        assert len(engine._instruments) == 1

    def test_portfolio_mode_requires_instruments(self):
        """Test portfolio mode requires at least one instrument."""
        mock_adapter = Mock(spec=DataAdapter)
        strategy = TestStrategy()
        config = BacktestConfig()

        with pytest.raises(Exception) as exc_info:
            BacktestEngine([], strategy, config)
        assert "At least one instrument required" in str(exc_info.value)

    def test_portfolio_mode_requires_adapters(self):
        """Test portfolio mode requires adapters for all instruments."""
        from quantrex_core import InstrumentSpec

        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=None)]
        strategy = TestStrategy()
        config = BacktestConfig()

        with pytest.raises(Exception) as exc_info:
            BacktestEngine(instruments, strategy, config)
        assert "DataAdapter required" in str(exc_info.value)

    def test_portfolio_mode_run_returns_portfolio_result(self):
        """Test portfolio mode run returns BacktestResult."""
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
        config = BacktestConfig(initial_cash=1_000_000.0, auto_download=False)

        engine = BacktestEngine(instruments, strategy, config)
        result = engine.run()

        assert isinstance(result, BacktestResult)
        assert result.initial_cash == 1_000_000.0
        assert result.symbols == ["RELIANCE"]

    def test_portfolio_mode_multiple_instruments(self):
        """Test portfolio mode with multiple instruments."""
        # Use a strategy that accesses portfolio context to force sequential execution
        # (mock adapters can't be pickled for parallel execution)
        mock_adapter_reliance = Mock(spec=DataAdapter)
        mock_adapter_reliance.datetime_format = "%Y%m%d %H:%M"
        mock_adapter_reliance.supported_timeframes = ["1M"]
        mock_adapter_reliance.get_origin_time.return_value = None
        mock_adapter_reliance.read_timeframe.return_value = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            {"datetime": "20260101 09:16", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]

        mock_adapter_tcs = Mock(spec=DataAdapter)
        mock_adapter_tcs.datetime_format = "%Y%m%d %H:%M"
        mock_adapter_tcs.supported_timeframes = ["1M"]
        mock_adapter_tcs.get_origin_time.return_value = None
        mock_adapter_tcs.read_timeframe.return_value = [
            {"datetime": "20260101 09:15", "open": "3000", "high": "3001", "low": "2999", "close": "3000", "volume": "1000"},
            {"datetime": "20260101 09:16", "open": "3000", "high": "3001", "low": "2999", "close": "3000", "volume": "1000"},
        ]

        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter_reliance),
            InstrumentSpec(symbol="TCS", adapter=mock_adapter_tcs),
        ]
        
        # Use a strategy that accesses portfolio context (forces sequential)
        class PortfolioAwareStrategy(Strategy):
            def on_candle(self, candle: Candle) -> None:
                # Access portfolio to trigger sequential fallback
                _ = self.ctx.portfolio
        
        strategy = PortfolioAwareStrategy()
        config = BacktestConfig(initial_cash=1_000_000.0, auto_download=False)

        engine = BacktestEngine(instruments, strategy, config)
        result = engine.run()

        assert isinstance(result, BacktestResult)
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
        config = BacktestConfig(initial_cash=1_000_000.0, auto_download=False)

        engine = BacktestEngine(
            [InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter)],
            strategy,
            config,
        )
        _result = engine.run()

        # Strategy should have received portfolio context
        assert len(strategy.portfolio_snapshots) > 0
        for snapshot in strategy.portfolio_snapshots:
            assert 'cash' in snapshot
            assert 'equity' in snapshot
            assert 'positions' in snapshot


class TestBacktestEnginePortfolioModeMultiTimeframe:
    """Tests for multi-timeframe dispatch in portfolio mode."""

    def test_multi_symbol_multi_timeframe_dispatch(self):
        """Test that higher-timeframe callbacks fire for all symbols in portfolio."""
        from quantrex_core.strategy.base import on_timeframe
        
        class MultiSymbolTFStrategy(Strategy):
            """Strategy that logs higher timeframe callbacks for each symbol."""
            
            def __init__(self):
                super().__init__()
                self.higher_tf_calls = {}  # symbol -> list of (timeframe, candle)
            
            @on_timeframe("1H")
            def on_1h_candle(self, candle: Candle):
                symbol = candle.symbol
                if symbol not in self.higher_tf_calls:
                    self.higher_tf_calls[symbol] = []
                self.higher_tf_calls[symbol].append(("1H", candle))
            
            @on_timeframe("1D")
            def on_daily_candle(self, candle: Candle):
                symbol = candle.symbol
                if symbol not in self.higher_tf_calls:
                    self.higher_tf_calls[symbol] = []
                self.higher_tf_calls[symbol].append(("1D", candle))
            
            def on_candle(self, candle: Candle):
                pass
            
            def compute_indicators(self, candles, timeframe=None):
                return [{} for _ in candles]

        def create_mock_adapter(symbol, base_price):
            adapter = Mock(spec=DataAdapter)
            adapter.datetime_format = "%Y%m%d %H:%M"
            adapter.supported_timeframes = ["1M", "1H", "1D"]
            adapter.get_origin_time.return_value = None
            
            # Generate 1M data for 2 days (enough for 1H and 1D candles)
            base_data = []
            for day in range(2):
                for hour in range(9, 15):
                    for minute in range(0, 60, 1):
                        dt = datetime(2026, 1, 1 + day, hour, minute)
                        base_data.append({
                            "datetime": dt.strftime("%Y%m%d %H:%M"),
                            "open": str(base_price),
                            "high": str(base_price + 1),
                            "low": str(base_price - 1),
                            "close": str(base_price),
                            "volume": "1000",
                        })
            
            # 1H data
            h1_data = []
            for day in range(2):
                for hour in range(9, 15):
                    dt = datetime(2026, 1, 1 + day, hour, 0)
                    h1_data.append({
                        "datetime": dt.strftime("%Y%m%d %H:%M"),
                        "open": str(base_price),
                        "high": str(base_price + 2),
                        "low": str(base_price - 2),
                        "close": str(base_price),
                        "volume": "60000",
                    })
            
            # 1D data - use 14:30 close time so it's before the last base candle (14:59)
            d1_data = []
            for day in range(2):
                dt = datetime(2026, 1, 1 + day, 14, 30)
                d1_data.append({
                    "datetime": dt.strftime("%Y%m%d %H:%M"),
                    "open": str(base_price),
                    "high": str(base_price + 5),
                    "low": str(base_price - 5),
                    "close": str(base_price),
                    "volume": "3600000",
                })
            
            def read_timeframe(tf, from_date=None, to_date=None):
                if tf == "1M":
                    return base_data
                elif tf == "1H":
                    return h1_data
                elif tf == "1D":
                    return d1_data
                return []
            
            adapter.read_timeframe.side_effect = read_timeframe
            return adapter

        adapter_reliance = create_mock_adapter("RELIANCE", 1500)
        adapter_tcs = create_mock_adapter("TCS", 3000)

        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=adapter_reliance),
            InstrumentSpec(symbol="TCS", adapter=adapter_tcs),
        ]

        strategy = MultiSymbolTFStrategy()
        config = BacktestConfig(
            initial_cash=1_000_000.0,
            auto_download=False,
            data_start="2026-01-01",
            data_end="2026-01-02",
        )

        engine = BacktestEngine(instruments, strategy, config)
        result = engine.run()

        # Verify both symbols received higher timeframe callbacks
        assert "RELIANCE" in strategy.higher_tf_calls, "RELIANCE missing higher TF callbacks"
        assert "TCS" in strategy.higher_tf_calls, "TCS missing higher TF callbacks"
        assert len(strategy.higher_tf_calls["RELIANCE"]) > 0, "RELIANCE has no higher TF callbacks"
        assert len(strategy.higher_tf_calls["TCS"]) > 0, "TCS has no higher TF callbacks"

        # Verify 1H callbacks exist for both symbols
        reliance_1h = [c for tf, c in strategy.higher_tf_calls["RELIANCE"] if tf == "1H"]
        tcs_1h = [c for tf, c in strategy.higher_tf_calls["TCS"] if tf == "1H"]
        assert len(reliance_1h) > 0, "RELIANCE has no 1H callbacks"
        assert len(tcs_1h) > 0, "TCS has no 1H callbacks"

        # Verify 1D callbacks exist for both symbols
        reliance_1d = [c for tf, c in strategy.higher_tf_calls["RELIANCE"] if tf == "1D"]
        tcs_1d = [c for tf, c in strategy.higher_tf_calls["TCS"] if tf == "1D"]
        assert len(reliance_1d) > 0, "RELIANCE has no 1D callbacks"
        assert len(tcs_1d) > 0, "TCS has no 1D callbacks"

        # Verify callback candles have correct symbols
        for candle in reliance_1h + reliance_1d:
            assert candle.symbol == "RELIANCE", f"RELIANCE callback has wrong symbol: {candle.symbol}"
        for candle in tcs_1h + tcs_1d:
            assert candle.symbol == "TCS", f"TCS callback has wrong symbol: {candle.symbol}"

    def test_timeframe_history_returns_correct_symbol(self):
        """Test that timeframe_history returns correct symbol's data in portfolio mode."""
        from quantrex_core.strategy.base import on_timeframe
        
        class CheckHistoryStrategy(Strategy):
            def __init__(self):
                super().__init__()
                self.history_checks = []
            
            def on_candle(self, candle: Candle):
                # Check timeframe_history returns correct symbol's data
                tf_1h = self.ctx.timeframe_history("1H")
                tf_1d = self.ctx.timeframe_history("1D")
                self.history_checks.append({
                    'symbol': candle.symbol,
                    'tf_1h_symbols': [c.symbol for c in tf_1h],
                    'tf_1d_symbols': [c.symbol for c in tf_1d],
                })
            
            def compute_indicators(self, candles, timeframe=None):
                return [{} for _ in candles]

        def create_mock_adapter(symbol, base_price):
            adapter = Mock(spec=DataAdapter)
            adapter.datetime_format = "%Y%m%d %H:%M"
            adapter.supported_timeframes = ["1M", "1H", "1D"]
            adapter.get_origin_time.return_value = None
            
            base_data = []
            for day in range(1):
                for hour in range(9, 10):
                    for minute in range(0, 60, 1):
                        dt = datetime(2026, 1, 1 + day, hour, minute)
                        base_data.append({
                            "datetime": dt.strftime("%Y%m%d %H:%M"),
                            "open": str(base_price),
                            "high": str(base_price + 1),
                            "low": str(base_price - 1),
                            "close": str(base_price),
                            "volume": "1000",
                        })
            
            h1_data = []
            for day in range(1):
                for hour in range(9, 10):
                    dt = datetime(2026, 1, 1 + day, hour, 0)
                    h1_data.append({
                        "datetime": dt.strftime("%Y%m%d %H:%M"),
                        "open": str(base_price),
                        "high": str(base_price + 2),
                        "low": str(base_price - 2),
                        "close": str(base_price),
                        "volume": "60000",
                    })
            
            d1_data = []
            for day in range(1):
                dt = datetime(2026, 1, 1 + day, 15, 30)
                d1_data.append({
                    "datetime": dt.strftime("%Y%m%d %H:%M"),
                    "open": str(base_price),
                    "high": str(base_price + 5),
                    "low": str(base_price - 5),
                    "close": str(base_price),
                    "volume": "3600000",
                })
            
            def read_timeframe(tf, from_date=None, to_date=None):
                if tf == "1M":
                    return base_data
                elif tf == "1H":
                    return h1_data
                elif tf == "1D":
                    return d1_data
                return []
            
            adapter.read_timeframe.side_effect = read_timeframe
            return adapter

        adapter_reliance = create_mock_adapter("RELIANCE", 1500)
        adapter_tcs = create_mock_adapter("TCS", 3000)

        instruments = [
            InstrumentSpec(symbol="RELIANCE", adapter=adapter_reliance),
            InstrumentSpec(symbol="TCS", adapter=adapter_tcs),
        ]

        strategy = CheckHistoryStrategy()
        config = BacktestConfig(
            initial_cash=1_000_000.0,
            auto_download=False,
            data_start="2026-01-01",
            data_end="2026-01-01",
        )

        engine = BacktestEngine(instruments, strategy, config)
        result = engine.run()

        # Verify timeframe_history returns correct symbol's data
        for check in strategy.history_checks:
            symbol = check['symbol']
            tf_1h_symbols = check['tf_1h_symbols']
            tf_1d_symbols = check['tf_1d_symbols']
            
            # All candles in timeframe_history should belong to the current symbol
            for s in tf_1h_symbols:
                assert s == symbol, f"When processing {symbol}, timeframe_history(1H) returned {s}'s candles"
            for s in tf_1d_symbols:
                assert s == symbol, f"When processing {symbol}, timeframe_history(1D) returned {s}'s candles"


class TestBacktestEnginePortfolioModeEdgeCases:
    """Tests for edge cases in portfolio mode."""

    def test_portfolio_mode_empty_data(self):
        """Test portfolio mode with empty data returns empty BacktestResult."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        mock_adapter.read_timeframe.return_value = []

        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter)]
        strategy = TestStrategy()
        config = BacktestConfig(auto_download=False)

        engine = BacktestEngine(instruments, strategy, config)
        
        result = engine.run()
        assert isinstance(result, BacktestResult)
        assert result.initial_cash == 1_000_000.0
        assert result.final_equity == 1_000_000.0
        assert len(result.trades) == 0

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
        config = BacktestConfig(auto_download=False)

        engine = BacktestEngine(instruments, strategy, config)
        result = engine.run()

        # Should handle mismatched timestamps gracefully
        assert isinstance(result, BacktestResult)