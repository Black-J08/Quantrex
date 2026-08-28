"""Tests for BacktestEngine."""

from unittest.mock import Mock, MagicMock
from datetime import datetime
from pathlib import Path
import csv

from quantrex_core.models import Candle
from quantrex_core.strategy.base import Strategy
from quantrex_core.models.enums import OrderSide
from quantrex_data.providers.csv_provider import CSVDataProvider
from quantrex_data.adapters.csv_adapter import CSVDataAdapter
from quantrex_backtest import BacktestEngine
from quantrex_backtest.exceptions.backtest_error import ProviderError
from quantrex_core.protocols import DataAdapter
from quantrex_test_support.csv import (
    make_ohlc_series,
    csv_rows_to_string,
    create_temp_csv,
)


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


class TradeRecordingStrategy(Strategy):
    """Test strategy that submits orders to test trade recording."""
    
    def __init__(self):
        super().__init__()
        self.orders = []
        self.candles = []
    
    def on_candle(self, candle: Candle) -> None:
        # Buy on first candle, sell on third candle (close position)
        if len(self.candles) == 0:
            order = self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.BUY,
                quantity=10.0,
            )
            self.orders.append(order)
        elif len(self.candles) == 2:
            order = self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.SELL,
                quantity=10.0,
            )
            self.orders.append(order)
        self.candles.append(candle)
    
    def on_stop(self) -> None:
        pass


class PartialCloseStrategy(Strategy):
    """Test strategy that partially closes a position."""
    
    def __init__(self):
        super().__init__()
        self.orders = []
        self.candles = []
    
    def on_candle(self, candle: Candle) -> None:
        # Buy 20 on first candle
        if len(self.candles) == 0:
            order = self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.BUY,
                quantity=20.0,
            )
            self.orders.append(order)
        # Sell 10 on second candle (partial close)
        elif len(self.candles) == 1:
            order = self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.SELL,
                quantity=10.0,
            )
            self.orders.append(order)
        # Sell remaining 10 on third candle (full close)
        elif len(self.candles) == 2:
            order = self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.SELL,
                quantity=10.0,
            )
            self.orders.append(order)
        self.candles.append(candle)
    
    def on_stop(self) -> None:
        pass


class TestBacktestEngine:
    """Tests for BacktestEngine core functionality."""

    def test_engine_rejects_none_adapter(self):
        """Engine should raise ProviderError when adapter is None."""
        strategy = TestStrategy()
        try:
            BacktestEngine(None, strategy, symbol="COPPER")
            assert False, "Should have raised ProviderError"
        except ProviderError as e:
            assert "DataAdapter is required" in str(e)

    def test_engine_rejects_none_strategy(self):
        """Engine should raise ProviderError when strategy is None."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read.return_value = []
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        try:
            BacktestEngine(mock_adapter, None, symbol="COPPER")
            assert False, "Should have raised ProviderError"
        except ProviderError as e:
            assert "Strategy is required" in str(e)

    def test_engine_accepts_valid_adapter_and_strategy(self):
        """Engine should accept a valid DataAdapter and Strategy."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read.return_value = []
        strategy = TestStrategy()

        engine = BacktestEngine(mock_adapter, strategy, symbol="COPPER")
        assert engine is not None

    def test_engine_processes_candles_in_timestamp_order(self):
        """Engine should process candles sorted by timestamp."""
        # Create CSV with out-of-order timestamps using test-support
        rows = [
            ["20230621", "10:06", "740.00", "740.00", "740.00", "740.00", "2", "1"],  # Later
            ["20230620", "19:00", "737.20", "737.20", "737.20", "737.20", "1", "1"],  # Earlier
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = TestStrategy()
            engine = BacktestEngine(adapter, strategy, symbol="COPPER")

            engine.run()

            assert len(strategy.candles) == 2
            # Should be sorted by timestamp (earlier first)
            assert strategy.candles[0].timestamp == datetime(2023, 6, 20, 19, 0)
            assert strategy.candles[1].timestamp == datetime(2023, 6, 21, 10, 6)

    def test_engine_calls_strategy_on_candle_for_each_candle(self):
        """Engine should invoke strategy.on_candle for each candle."""
        rows = make_ohlc_series(num_rows=3, seed=42)
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = TestStrategy()
            engine = BacktestEngine(adapter, strategy, symbol="COPPER")

            engine.run()

            assert len(strategy.candles) == 3
            for candle in strategy.candles:
                assert isinstance(candle, Candle)
                assert candle.symbol == "COPPER"

    def test_engine_calls_lifecycle_methods(self):
        """Engine should call on_start before and on_stop after processing."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read.return_value = [
            {"datetime": "20230620 19:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "10"}
        ]
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        strategy = TestStrategy()
        engine = BacktestEngine(mock_adapter, strategy, symbol="COPPER")

        engine.run()

        assert strategy.started is True
        assert strategy.stopped is True
        assert len(strategy.candles) == 1

    def test_engine_handles_empty_data(self):
        """Engine should handle empty data gracefully."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read.return_value = []
        mock_adapter.datetime_format = "%Y%m%d %H:%M"

        strategy = TestStrategy()
        engine = BacktestEngine(mock_adapter, strategy, symbol="COPPER")

        engine.run()

        assert strategy.started is True
        assert strategy.stopped is True
        assert len(strategy.candles) == 0

    def test_engine_passes_candle_with_correct_values(self):
        """Engine should pass correctly parsed Candle to strategy."""
        rows = [
            ["20230620", "19:00", "737.20", "738.00", "736.50", "737.50", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = TestStrategy()
            engine = BacktestEngine(adapter, strategy, symbol="COPPER")

            engine.run()

            assert len(strategy.candles) == 1
            candle = strategy.candles[0]
            assert candle.symbol == "COPPER"
            assert candle.timestamp == datetime(2023, 6, 20, 19, 0)
            assert candle.open == 737.20
            assert candle.high == 738.00
            assert candle.low == 736.50
            assert candle.close == 737.50
            assert candle.volume == 100.0

    def test_engine_raises_on_adapter_read_failure(self):
        """Engine should wrap adapter read() failures in ProviderError."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read.side_effect = IOError("Disk error")
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        strategy = TestStrategy()

        engine = BacktestEngine(mock_adapter, strategy, symbol="COPPER")

        try:
            engine.run()
            assert False, "Should have raised ProviderError"
        except ProviderError as e:
            assert "Failed to read data from adapter" in str(e)
            assert "Disk error" in str(e)

    def test_engine_raises_on_invalid_candle_data(self):
        """Engine should raise ProviderError for malformed candle data."""
        # CSV with invalid float value
        rows = [
            ["20230620", "19:00", "not_a_number", "738.00", "736.50", "737.50", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = TestStrategy()
            engine = BacktestEngine(adapter, strategy, symbol="COPPER")

            try:
                engine.run()
                assert False, "Should have raised ProviderError"
            except ProviderError as e:
                assert "Failed to process candle" in str(e)

    def test_engine_deterministic_order(self):
        """Engine should produce identical callback sequence on repeated runs."""
        rows = [
            ["20230621", "10:06", "740.00", "740.00", "740.00", "740.00", "2", "1"],  # Later
            ["20230620", "19:00", "737.20", "737.20", "737.20", "737.20", "1", "1"],  # Earlier
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            
            strategy1 = TestStrategy()
            engine1 = BacktestEngine(adapter, strategy1, symbol="COPPER")
            engine1.run()
            run1_timestamps = [c.timestamp for c in strategy1.candles]

            strategy2 = TestStrategy()
            engine2 = BacktestEngine(adapter, strategy2, symbol="COPPER")
            engine2.run()
            run2_timestamps = [c.timestamp for c in strategy2.candles]

            assert run1_timestamps == run2_timestamps

    def test_engine_custom_datetime_format(self):
        """Engine should respect custom datetime format."""
        rows = [
            ["20-06-2023", "19:00", "737.20", "738.00", "736.50", "737.50", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            adapter = CSVDataAdapter(
                provider,
                column_mapping={
                    "datetime": [0, 1],
                    "open": 2,
                    "high": 3,
                    "low": 4,
                    "close": 5,
                    "volume": 6,
                },
                datetime_format="%d-%m-%Y %H:%M",
            )
            strategy = TestStrategy()
            engine = BacktestEngine(adapter, strategy, symbol="COPPER")

            engine.run()

            assert len(strategy.candles) == 1
            assert strategy.candles[0].timestamp == datetime(2023, 6, 20, 19, 0)

    def test_engine_with_mock_adapter(self):
        """Engine should work with a mock adapter returning dict rows."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read.return_value = [
            {"datetime": "20230620 19:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "10"},
            {"datetime": "20230621 10:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "20"},
        ]
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        strategy = TestStrategy()
        engine = BacktestEngine(mock_adapter, strategy, symbol="COPPER")

        engine.run()

        assert len(strategy.candles) == 2
        assert strategy.candles[0].close == 100.0
        assert strategy.candles[1].close == 101.0

    def test_engine_exports_closed_trades_csv(self):
        """Engine should export closed trades to CSV after backtest completes."""
        # Create CSV with 4 candles: buy on 1st, sell on 3rd
        rows = [
            ["20230620", "19:00", "100.00", "101.00", "99.00", "100.50", "100", "50"],
            ["20230620", "19:01", "100.50", "101.50", "100.00", "101.00", "100", "50"],
            ["20230620", "19:02", "101.00", "102.00", "100.50", "101.50", "100", "50"],
            ["20230620", "19:03", "101.50", "102.50", "101.00", "102.00", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = TradeRecordingStrategy()
            engine = BacktestEngine(adapter, strategy, symbol="COPPER")

            engine.run()

            # Verify CSV was created (find the most recent output directory)
            output_dirs = list(Path("output/backtest/TradeRecordingStrategy").glob("*"))
            assert len(output_dirs) >= 1
            # Use the most recent directory
            latest_dir = max(output_dirs, key=lambda d: d.stat().st_mtime)
            csv_file = latest_dir / "closed_trades.csv"
            assert csv_file.exists()

            # Verify CSV content
            with open(csv_file, "r") as f:
                reader = csv.reader(f)
                rows = list(reader)
            
            # Header + 1 trade row
            assert len(rows) == 2
            assert rows[0] == ["symbol", "side", "quantity", "entry_timestamp", "entry_price", "exit_timestamp", "exit_price", "pnl"]
            
            trade = rows[1]
            assert trade[0] == "COPPER"
            assert trade[1] == "LONG"
            assert float(trade[2]) == 10.0
            assert float(trade[4]) == 100.00  # entry_price (candle 1 open)
            assert float(trade[6]) == 101.00  # exit_price (candle 3 open)
            # P&L = (101.00 - 100.00) * 10.0 * 1.0 = 10.0
            assert abs(float(trade[7]) - 10.0) < 0.01

    def test_engine_exports_partial_close_trades_csv(self):
        """Engine should export multiple trades for partial position closes."""
        # Create CSV with 4 candles: buy 20 on 1st, sell 10 on 2nd, sell 10 on 3rd
        rows = [
            ["20230620", "19:00", "100.00", "101.00", "99.00", "100.50", "100", "50"],
            ["20230620", "19:01", "100.50", "101.50", "100.00", "101.00", "100", "50"],
            ["20230620", "19:02", "101.00", "102.00", "100.50", "101.50", "100", "50"],
            ["20230620", "19:03", "101.50", "102.50", "101.00", "102.00", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = PartialCloseStrategy()
            engine = BacktestEngine(adapter, strategy, symbol="COPPER")

            engine.run()

            # Verify CSV was created (find the most recent output directory)
            output_dirs = list(Path("output/backtest/PartialCloseStrategy").glob("*"))
            assert len(output_dirs) >= 1
            latest_dir = max(output_dirs, key=lambda d: d.stat().st_mtime)
            csv_file = latest_dir / "closed_trades.csv"
            assert csv_file.exists()

            # Verify CSV content
            with open(csv_file, "r") as f:
                reader = csv.reader(f)
                rows = list(reader)
            
            # Header + 2 trade rows (partial close + full close)
            assert len(rows) == 3
            assert rows[0] == ["symbol", "side", "quantity", "entry_timestamp", "entry_price", "exit_timestamp", "exit_price", "pnl"]
            
            # First trade: partial close of 10
            trade1 = rows[1]
            assert trade1[0] == "COPPER"
            assert trade1[1] == "LONG"
            assert float(trade1[2]) == 10.0
            assert float(trade1[4]) == 100.00  # entry_price
            assert float(trade1[6]) == 100.50  # exit_price (candle 2 open)
            # P&L = (100.50 - 100.00) * 10.0 * 1.0 = 5.0
            assert abs(float(trade1[7]) - 5.0) < 0.01
            
            # Second trade: full close of remaining 10
            trade2 = rows[2]
            assert trade2[0] == "COPPER"
            assert trade2[1] == "LONG"
            assert float(trade2[2]) == 10.0
            assert float(trade2[4]) == 100.00  # entry_price (same as original)
            assert float(trade2[6]) == 101.00  # exit_price (candle 3 open)
            # P&L = (101.00 - 100.00) * 10.0 * 1.0 = 10.0
            assert abs(float(trade2[7]) - 10.0) < 0.01

    def test_engine_exports_empty_trades_csv(self):
        """Engine should export CSV with headers only when no trades occurred."""
        rows = [
            ["20230620", "19:00", "100.00", "101.00", "99.00", "100.50", "100", "50"],
            ["20230620", "19:01", "100.50", "101.50", "100.00", "101.00", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = TestStrategy()  # No orders submitted
            engine = BacktestEngine(adapter, strategy, symbol="COPPER")

            engine.run()

            # Verify CSV was created (find the most recent output directory)
            output_dirs = list(Path("output/backtest/TestStrategy").glob("*"))
            assert len(output_dirs) >= 1
            latest_dir = max(output_dirs, key=lambda d: d.stat().st_mtime)
            csv_file = latest_dir / "closed_trades.csv"
            assert csv_file.exists()

            # Verify CSV content - only headers
            with open(csv_file, "r") as f:
                reader = csv.reader(f)
                rows = list(reader)
            
            assert len(rows) == 1
            assert rows[0] == ["symbol", "side", "quantity", "entry_timestamp", "entry_price", "exit_timestamp", "exit_price", "pnl"]

    def test_engine_short_position_trade_recording(self):
        """Engine should correctly record trades for short positions."""
        # Create CSV: sell short on 1st, buy to cover on 3rd
        rows = [
            ["20230620", "19:00", "100.00", "101.00", "99.00", "100.50", "100", "50"],
            ["20230620", "19:01", "100.50", "101.50", "100.00", "101.00", "100", "50"],
            ["20230620", "19:02", "101.00", "102.00", "100.50", "101.50", "100", "50"],
            ["20230620", "19:03", "101.50", "102.50", "101.00", "102.00", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        class ShortStrategy(Strategy):
            def __init__(self):
                super().__init__()
                self.orders = []
                self.candles = []
            
            def on_candle(self, candle: Candle) -> None:
                if len(self.candles) == 0:
                    order = self.ctx.submit_order(
                        symbol=candle.symbol,
                        side=OrderSide.SELL,
                        quantity=10.0,
                    )
                    self.orders.append(order)
                elif len(self.candles) == 2:
                    order = self.ctx.submit_order(
                        symbol=candle.symbol,
                        side=OrderSide.BUY,
                        quantity=10.0,
                    )
                    self.orders.append(order)
                self.candles.append(candle)
            
            def on_stop(self) -> None:
                pass

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = ShortStrategy()
            engine = BacktestEngine(adapter, strategy, symbol="COPPER")

            engine.run()

            # Verify CSV was created (find the most recent output directory)
            output_dirs = list(Path("output/backtest/ShortStrategy").glob("*"))
            assert len(output_dirs) >= 1
            latest_dir = max(output_dirs, key=lambda d: d.stat().st_mtime)
            csv_file = latest_dir / "closed_trades.csv"
            assert csv_file.exists()

            # Verify CSV content
            with open(csv_file, "r") as f:
                reader = csv.reader(f)
                rows = list(reader)
            
            assert len(rows) == 2
            trade = rows[1]
            assert trade[0] == "COPPER"
            assert trade[1] == "SHORT"
            assert float(trade[2]) == 10.0
            assert float(trade[4]) == 100.00  # entry_price (candle 1 open)
            assert float(trade[6]) == 101.00  # exit_price (candle 3 open)
            # P&L for SHORT = (entry - exit) * qty = (100.00 - 101.00) * 10.0 = -10.0
            assert abs(float(trade[7]) - (-10.0)) < 0.01