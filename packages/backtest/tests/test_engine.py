"""Tests for BacktestEngine."""

from unittest.mock import Mock
from datetime import datetime
from pathlib import Path
import csv

from quantrex_core.models import Candle
from quantrex_core.strategy.base import Strategy
from quantrex_core.strategy.timeframe import on_timeframe
from quantrex_core.models.enums import OrderSide
from quantrex_data.providers.csv_provider import CSVDataProvider
from quantrex_data.adapters.csv_adapter import CSVDataAdapter
from quantrex_backtest import BacktestEngine, InstrumentSpec, BacktestConfig
from quantrex_backtest.exceptions.backtest_error import ProviderError
from quantrex_core.protocols import DataAdapter
from quantrex_test_support.csv import (
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

    def test_engine_rejects_none_instruments(self):
        """Engine should raise ProviderError when instruments list is empty."""
        strategy = TestStrategy()
        try:
            BacktestEngine([], strategy, BacktestConfig())
            assert False, "Should have raised ProviderError"
        except ProviderError as e:
            assert "At least one instrument required" in str(e)

    def test_engine_rejects_none_strategy(self):
        """Engine should raise ProviderError when strategy is None."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read_timeframe.return_value = []
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        try:
            BacktestEngine([InstrumentSpec(symbol="COPPER", adapter=mock_adapter)], None, BacktestConfig())
            assert False, "Should have raised ProviderError"
        except ProviderError as e:
            assert "Strategy is required" in str(e)

    def test_engine_accepts_valid_instruments_and_strategy(self):
        """Engine should accept valid instruments and Strategy."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read_timeframe.return_value = []
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        strategy = TestStrategy()

        engine = BacktestEngine(
            [InstrumentSpec(symbol="COPPER", adapter=mock_adapter)],
            strategy,
            BacktestConfig()
        )
        assert engine is not None

    def test_engine_processes_candles_in_timestamp_order(self):
        """Engine should process candles sorted by timestamp."""
        # Create CSV with out-of-order timestamps using test-support
        # Use NSE market hours (9:15-15:30) to pass alignment
        rows = [
            ["20230621", "10:06", "740.00", "740.00", "740.00", "740.00", "2", "1"],  # Later
            ["20230620", "09:15", "737.20", "737.20", "737.20", "737.20", "1", "1"],  # Earlier
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(
                temp_path,
                has_header=False,
                datetime_format="%Y%m%d %H:%M",
                datetime_column=[0, 1],
            )
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = TestStrategy()
            engine = BacktestEngine(
                [InstrumentSpec(symbol="COPPER", adapter=adapter)],
                strategy,
                BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
            )

            engine.run()

            assert len(strategy.candles) == 2
            # Should be sorted by timestamp (earlier first)
            assert strategy.candles[0].timestamp == datetime(2023, 6, 20, 9, 15)
            assert strategy.candles[1].timestamp == datetime(2023, 6, 21, 10, 6)

    def test_engine_calls_lifecycle_methods(self):
        """Engine should call on_start before and on_stop after processing."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read_timeframe.return_value = [
            {"datetime": "20230620 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "10"}
        ]
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        strategy = TestStrategy()
        engine = BacktestEngine(
            [InstrumentSpec(symbol="COPPER", adapter=mock_adapter)],
            strategy,
            BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
        )

        engine.run()

        assert strategy.started is True
        assert strategy.stopped is True
        assert len(strategy.candles) == 1

    def test_engine_handles_empty_data(self):
        """Engine should handle empty data gracefully."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read_timeframe.return_value = []
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None

        strategy = TestStrategy()
        engine = BacktestEngine(
            [InstrumentSpec(symbol="COPPER", adapter=mock_adapter)],
            strategy,
            BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
        )

        engine.run()

        assert strategy.started is True
        assert strategy.stopped is True
        assert len(strategy.candles) == 0

    def test_engine_passes_candle_with_correct_values(self):
        """Engine should pass correctly parsed Candle to strategy."""
        rows = [
            ["20230620", "09:15", "737.20", "738.00", "736.50", "737.50", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(
                temp_path,
                has_header=False,
                datetime_format="%Y%m%d %H:%M",
                datetime_column=[0, 1],
            )
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = TestStrategy()
            engine = BacktestEngine(
                [InstrumentSpec(symbol="COPPER", adapter=adapter)],
                strategy,
                BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
            )

            engine.run()

            assert len(strategy.candles) == 1
            candle = strategy.candles[0]
            assert candle.symbol == "COPPER"
            assert candle.timestamp == datetime(2023, 6, 20, 9, 15)
            assert candle.open == 737.20
            assert candle.high == 738.00
            assert candle.low == 736.50
            assert candle.close == 737.50
            assert candle.volume == 100.0

    def test_engine_raises_on_adapter_read_failure(self):
        """Engine should wrap adapter read_timeframe() failures in ProviderError."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read_timeframe.side_effect = IOError("Disk error")
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        strategy = TestStrategy()

        engine = BacktestEngine(
            [InstrumentSpec(symbol="COPPER", adapter=mock_adapter)],
            strategy,
            BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
        )

        try:
            engine.run()
            assert False, "Should have raised ProviderError"
        except ProviderError as e:
            assert "Failed to read data" in str(e)
            assert "Disk error" in str(e)

    def test_engine_raises_on_invalid_candle_data(self):
        """Engine should raise ProviderError for malformed candle data."""
        # CSV with invalid float value
        rows = [
            ["20230620", "09:15", "not_a_number", "738.00", "736.50", "737.50", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(
                temp_path,
                has_header=False,
                datetime_format="%Y%m%d %H:%M",
                datetime_column=[0, 1],
            )
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = TestStrategy()
            engine = BacktestEngine(
                [InstrumentSpec(symbol="COPPER", adapter=adapter)],
                strategy,
                BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
            )

            try:
                engine.run()
                assert False, "Should have raised ProviderError"
            except ProviderError as e:
                # Error now comes from DataOrchestrator validation
                assert "Failed to read data" in str(e)
                assert "Invalid data format" in str(e)
                assert "open must be numeric" in str(e)

    def test_engine_deterministic_order(self):
        """Engine should produce identical callback sequence on repeated runs."""
        rows = [
            ["20230621", "10:06", "740.00", "740.00", "740.00", "740.00", "2", "1"],  # Later
            ["20230620", "09:15", "737.20", "737.20", "737.20", "737.20", "1", "1"],  # Earlier
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(
                temp_path,
                has_header=False,
                datetime_format="%Y%m%d %H:%M",
                datetime_column=[0, 1],
            )
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            
            strategy1 = TestStrategy()
            engine1 = BacktestEngine(
                [InstrumentSpec(symbol="COPPER", adapter=adapter)],
                strategy1,
                BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
            )
            engine1.run()
            run1_timestamps = [c.timestamp for c in strategy1.candles]
            strategy2 = TestStrategy()
            engine2 = BacktestEngine(
                [InstrumentSpec(symbol="COPPER", adapter=adapter)],
                strategy2,
                BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
            )
            engine2.run()
            run2_timestamps = [c.timestamp for c in strategy2.candles]

            assert run1_timestamps == run2_timestamps

    def test_engine_custom_datetime_format(self):
        """Engine should respect custom datetime format."""
        # Use a format that the alignment code can parse
        rows = [
            ["2023-06-20 09:15:00", "737.20", "738.00", "736.50", "737.50", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(
                temp_path,
                has_header=False,
                datetime_format="%Y-%m-%d %H:%M:%S",
                datetime_column=0,
            )
            adapter = CSVDataAdapter(
                provider,
                column_mapping={
                    "datetime": 0,
                    "open": 1,
                    "high": 2,
                    "low": 3,
                    "close": 4,
                    "volume": 5,
                },
                datetime_format="%Y-%m-%d %H:%M:%S",
            )
            strategy = TestStrategy()
            engine = BacktestEngine(
                [InstrumentSpec(symbol="COPPER", adapter=adapter)],
                strategy,
                BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
            )

            engine.run()

            assert len(strategy.candles) == 1
            assert strategy.candles[0].timestamp == datetime(2023, 6, 20, 9, 15)

    def test_engine_with_mock_adapter(self):
        """Engine should work with a mock adapter returning dict rows."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read_timeframe.return_value = [
            {"datetime": "20230620 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "10"},
            {"datetime": "20230621 10:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "20"},
        ]
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        strategy = TestStrategy()
        engine = BacktestEngine(
            [InstrumentSpec(symbol="COPPER", adapter=mock_adapter)],
            strategy,
            BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
        )

        engine.run()

        assert len(strategy.candles) == 2
        assert strategy.candles[0].close == 100.0
        assert strategy.candles[1].close == 101.0

    def test_engine_exports_closed_trades_csv(self):
        """Engine should export closed trades to CSV after backtest completes."""
        # Create CSV with 4 candles: buy on 1st, sell on 3rd
        # Use NSE market hours (9:15-15:30) to pass alignment
        rows = [
            ["20230620", "09:15", "100.00", "101.00", "99.00", "100.50", "100", "50"],
            ["20230620", "09:16", "100.50", "101.50", "100.00", "101.00", "100", "50"],
            ["20230620", "09:17", "101.00", "102.00", "100.50", "101.50", "100", "50"],
            ["20230620", "09:18", "101.50", "102.50", "101.00", "102.00", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(
                temp_path,
                has_header=False,
                datetime_format="%Y%m%d %H:%M",
                datetime_column=[0, 1],
            )
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = TradeRecordingStrategy()
            engine = BacktestEngine(
                [InstrumentSpec(symbol="COPPER", adapter=adapter)],
                strategy,
                BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
            )

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
            assert rows[0] == [
                "symbol", "side", "quantity",
                "entry_timestamp", "entry_price",
                "exit_timestamp", "exit_price", "pnl",
            ]
            
            trade = rows[1]
            assert trade[0] == "COPPER"
            assert trade[1] == "LONG"
            assert float(trade[2]) == 10.0
            # T+1: BUY on candle 0 → filled at candle 1 open (100.50)
            assert float(trade[4]) == 100.50
            # T+1: SELL on candle 2 → filled at candle 3 open (101.50)
            assert float(trade[6]) == 101.50
            # P&L = (101.50 - 100.50) * 10.0 * 1.0 = 10.0
            assert abs(float(trade[7]) - 10.0) < 0.01

    def test_engine_exports_partial_close_trades_csv(self):
        """Engine should export multiple trades for partial position closes."""
        # Create CSV with 4 candles: buy 20 on 1st, sell 10 on 2nd, sell 10 on 3rd
        # Use NSE market hours (9:15-15:30) to pass alignment
        rows = [
            ["20230620", "09:15", "100.00", "101.00", "99.00", "100.50", "100", "50"],
            ["20230620", "09:16", "100.50", "101.50", "100.00", "101.00", "100", "50"],
            ["20230620", "09:17", "101.00", "102.00", "100.50", "101.50", "100", "50"],
            ["20230620", "09:18", "101.50", "102.50", "101.00", "102.00", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(
                temp_path,
                has_header=False,
                datetime_format="%Y%m%d %H:%M",
                datetime_column=[0, 1],
            )
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = PartialCloseStrategy()
            engine = BacktestEngine(
                [InstrumentSpec(symbol="COPPER", adapter=adapter)],
                strategy,
                BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
            )

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
            assert rows[0] == [
                "symbol", "side", "quantity",
                "entry_timestamp", "entry_price",
                "exit_timestamp", "exit_price", "pnl",
            ]

            # First trade: partial close of 10
            trade1 = rows[1]
            assert trade1[0] == "COPPER"
            assert trade1[1] == "LONG"
            assert float(trade1[2]) == 10.0
            # T+1: BUY 20 on candle 0 → filled at candle 1 open = 100.50
            assert float(trade1[4]) == 100.50
            # T+1: SELL 10 on candle 1 → filled at candle 2 open = 101.00
            assert float(trade1[6]) == 101.00
            # P&L = (101.00 - 100.50) * 10.0 * 1.0 = 5.0
            assert abs(float(trade1[7]) - 5.0) < 0.01

            # Second trade: full close of remaining 10
            trade2 = rows[2]
            assert trade2[0] == "COPPER"
            assert trade2[1] == "LONG"
            assert float(trade2[2]) == 10.0
            assert float(trade2[4]) == 100.50  # entry_price (same as original)
            # T+1: SELL 10 on candle 2 → filled at candle 3 open = 101.50
            assert float(trade2[6]) == 101.50
            # P&L = (101.50 - 100.50) * 10.0 * 1.0 = 10.0
            assert abs(float(trade2[7]) - 10.0) < 0.01

    def test_engine_exports_empty_trades_csv(self):
        """Engine should export CSV with headers only when no trades occurred."""
        # Use NSE market hours (9:15-15:30) to pass alignment
        rows = [
            ["20230620", "09:15", "100.00", "101.00", "99.00", "100.50", "100", "50"],
            ["20230620", "09:16", "100.50", "101.50", "100.00", "101.00", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(
                temp_path,
                has_header=False,
                datetime_format="%Y%m%d %H:%M",
                datetime_column=[0, 1],
            )
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = TestStrategy()  # No orders submitted
            engine = BacktestEngine(
                [InstrumentSpec(symbol="COPPER", adapter=adapter)],
                strategy,
                BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
            )

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
            assert rows[0] == [
                "symbol", "side", "quantity",
                "entry_timestamp", "entry_price",
                "exit_timestamp", "exit_price", "pnl",
            ]

    def test_engine_short_position_trade_recording(self):
        """Engine should correctly record trades for short positions."""
        # Create CSV: sell short on 1st, buy to cover on 3rd
        # Use NSE market hours (9:15-15:30) to pass alignment
        rows = [
            ["20230620", "09:15", "100.00", "101.00", "99.00", "100.50", "100", "50"],
            ["20230620", "09:16", "100.50", "101.50", "100.00", "101.00", "100", "50"],
            ["20230620", "09:17", "101.00", "102.00", "100.50", "101.50", "100", "50"],
            ["20230620", "09:18", "101.50", "102.50", "101.00", "102.00", "100", "50"],
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
            provider = CSVDataProvider(
                temp_path,
                has_header=False,
                datetime_format="%Y%m%d %H:%M",
                datetime_column=[0, 1],
            )
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = ShortStrategy()
            engine = BacktestEngine(
                [InstrumentSpec(symbol="COPPER", adapter=adapter)],
                strategy,
                BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
            )

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
            # T+1: SELL SHORT on candle 0 → filled at candle 1 open = 100.50
            assert float(trade[4]) == 100.50
            # T+1: BUY to cover on candle 2 → filled at candle 3 open = 101.50
            assert float(trade[6]) == 101.50
            # P&L for SHORT = (entry - exit) * qty = (100.50 - 101.50) * 10.0 = -10.0
            assert abs(float(trade[7]) - (-10.0)) < 0.01

    def test_engine_logs_ohlc_per_candle_to_execution_log(self):
        """Regression: each candle must be logged with its backtest timestamp
        and full OHLCV to execution_log/{SYMBOL}_execution.log, without researcher code changes.
        """
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read_timeframe.return_value = [
            {"datetime": "20230620 09:15", "open": "100.5", "high": "101.25", "low": "99.75", "close": "100.75", "volume": "42"},
            {"datetime": "20230620 09:16", "open": "100.75", "high": "102.0", "low": "100.5", "close": "101.5", "volume": "17"},
        ]
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None
        strategy = TestStrategy()
        engine = BacktestEngine(
            [InstrumentSpec(symbol="COPPER", adapter=mock_adapter)],
            strategy,
            BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
        )

        engine.run()

        # Locate the most recent run directory written by this run.
        run_dirs = list(Path("output/backtest/TestStrategy").glob("*"))
        assert run_dirs, "no run directory was created"
        latest_dir = max(run_dirs, key=lambda d: d.stat().st_mtime)
        log_path = latest_dir / "execution_log" / "COPPER_execution.log"
        assert log_path.exists(), f"COPPER_execution.log not found at {log_path}"

        contents = log_path.read_text(encoding="utf-8")

        # Candle 1: 2023-06-20 09:15 — verify every OHLCV field appears
        # in a single line tagged with the symbol and candle timestamp.
        assert "[COPPER 2023-06-20T09:15:00]" in contents
        assert "O=100.5" in contents
        assert "H=101.25" in contents
        assert "L=99.75" in contents
        assert "C=100.75" in contents
        assert "V=42" in contents

        # Candle 2: 2023-06-20 09:16 — distinct values to ensure the line
        # is emitted per-bar, not a one-shot header.
        assert "[COPPER 2023-06-20T09:16:00]" in contents
        assert "O=100.75" in contents
        assert "H=102.0" in contents
        assert "C=101.5" in contents
        assert "V=17" in contents


class FifoLotStrategy(Strategy):
    """Test strategy that reproduces the FIFO lot-accounting regression scenario.

    Sequence (T+1 fills at next candle's open):

    * Candle 0 → BUY 2 (signal). Fill at candle 1 open.
    * Candle 2 → BUY 2 (signal). Fill at candle 3 open.
    * Candle 4 → SELL 3 (signal). Fill at candle 5 open.

    With candle opens [100.00, 100.00, 110.00, 110.00, 125.00, 125.00]:
      * Lot A: BUY 2 @ 100.00
      * Lot B: BUY 2 @ 110.00
      * Sell 3 @ 125.00 → FIFO consumes 2 of lot A + 1 of lot B.
    """

    def __init__(self) -> None:
        super().__init__()
        self.candles: list = []

    def on_candle(self, candle: Candle) -> None:
        n = len(self.candles)
        if n == 0:
            self.ctx.submit_order(candle.symbol, OrderSide.BUY, 2.0)
        elif n == 2:
            self.ctx.submit_order(candle.symbol, OrderSide.BUY, 2.0)
        elif n == 4:
            self.ctx.submit_order(candle.symbol, OrderSide.SELL, 3.0)
        self.candles.append(candle)


class TestFifoLotAccounting:
    """End-to-end FIFO lot accounting through the backtest engine.

    Regression coverage for the per-partial-close trade-reporting defect
    where the position-level single-entry basis was reused for every
    partial close, producing wrong P&L attribution and losing the actual
    lot → close mapping. The CSV is the researcher's contract — the
    columns and their semantics must remain stable and must reflect
    each consumed lot, not a position-level aggregate.
    """

    def test_engine_exports_fifo_multi_lot_close_columns(self):
        """User-reported scenario end-to-end: Buy 2@100 + Buy 2@110 → Sell 3@125.

        The CSV must contain TWO rows with DIFFERENT ``entry_price``
        (one per consumed lot) and correctly attributed P&L.
        Before the FIFO fix, this produced a single row claiming
        ``entry_price=100, quantity=3, pnl=75`` (wrong attribution of
        the lot-B unit).
        """
        # Candle opens: 100.00, 100.00, 110.00, 110.00, 125.00, 125.00.
        # All candles are 6 deep so each row has matching HLCV.
        # Use NSE market hours (9:15-15:30) to pass alignment
        rows = [
            ["20230620", "09:15", "100.00", "101.00", "99.50", "100.50", "100", "50"],
            ["20230620", "09:16", "100.00", "101.00", "99.50", "100.50", "100", "50"],
            ["20230620", "09:17", "110.00", "111.00", "109.50", "110.50", "100", "50"],
            ["20230620", "09:18", "110.00", "111.00", "109.50", "110.50", "100", "50"],
            ["20230620", "09:19", "125.00", "126.00", "124.50", "125.50", "100", "50"],
            ["20230620", "09:20", "125.00", "126.00", "124.50", "125.50", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(
                temp_path,
                has_header=False,
                datetime_format="%Y%m%d %H:%M",
                datetime_column=[0, 1],
            )
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = FifoLotStrategy()
            engine = BacktestEngine(
                [InstrumentSpec(symbol="COPPER", adapter=adapter)],
                strategy,
                BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
            )

            engine.run()

            output_dirs = list(Path("output/backtest/FifoLotStrategy").glob("*"))
            assert output_dirs, "no run directory was created"
            latest_dir = max(output_dirs, key=lambda d: d.stat().st_mtime)
            csv_file = latest_dir / "closed_trades.csv"
            assert csv_file.exists()

            with open(csv_file, "r") as f:
                reader = csv.reader(f)
                rows_out = list(reader)

            # Header + 2 FIFO trade rows (9-column CSV — partial_*
            # columns removed per user instruction).
            assert len(rows_out) == 3
            assert rows_out[0] == [
                "symbol", "side", "quantity",
                "entry_timestamp", "entry_price",
                "exit_timestamp", "exit_price", "pnl",
            ]

            # ---- Row 1: full consumption of lot A (₹100, qty=2). ----
            tr_a = rows_out[1]
            assert tr_a[0] == "COPPER"
            assert tr_a[1] == "LONG"
            assert float(tr_a[2]) == 2.0
            assert tr_a[3].startswith("2023-06-20T09:16:00")  # entry_timestamp
            assert float(tr_a[4]) == 100.00  # entry_price
            assert tr_a[5].startswith("2023-06-20T09:20:00")  # exit_timestamp
            assert float(tr_a[6]) == 125.00  # exit_price
            assert abs(float(tr_a[7]) - 50.0) < 0.01  # pnl

            # ---- Row 2: partial consumption of lot B (₹110, qty=1). ----
            tr_b = rows_out[2]
            assert tr_b[0] == "COPPER"
            assert tr_b[1] == "LONG"
            assert float(tr_b[2]) == 1.0
            assert float(tr_b[4]) == 110.00  # entry_price (lot-B basis)
            assert float(tr_b[6]) == 125.00  # exit_price (same close)
            assert abs(float(tr_b[7]) - 15.0) < 0.01  # pnl

            # Aggregate P&L = 50 + 15 = 65.
            assert abs(float(tr_a[7]) + float(tr_b[7]) - 65.0) < 0.02


class MultiTimeframeStrategy(Strategy):
    """Test strategy that uses @on_timeframe for multi-timeframe logic."""
    
    def __init__(self):
        super().__init__()
        self.candles_1m = []
        self.candles_1h = []
    
    @on_timeframe("1H")
    def on_1h_candle(self, candle: Candle) -> None:
        self.candles_1h.append(candle)
    
    def on_candle(self, candle: Candle) -> None:
        self.candles_1m.append(candle)
        # Engine manages timeframe dispatch automatically


class TestMultiTimeframeEngine:
    """Tests for multi-timeframe support in BacktestEngine."""

    def test_engine_derives_timeframes_from_strategy_registry(self):
        """Engine should read required timeframes from strategy's timeframe_registry."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read_timeframe.return_value = [
            {"datetime": "20230620 19:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "10"}
        ]
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M", "1H"]
        mock_adapter.get_origin_time.return_value = None
        
        strategy = MultiTimeframeStrategy()
        engine = BacktestEngine(
            [InstrumentSpec(symbol="COPPER", adapter=mock_adapter)],
            strategy,
            BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
        )
        
        required = engine._get_required_timeframes()
        assert "1M" in required  # base timeframe
        assert "1H" in required  # from @on_timeframe

    def test_engine_reads_all_timeframes_via_read_timeframe(self):
        """Engine should call adapter.read_timeframe() for all required timeframes."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read_timeframe.return_value = [
            {"datetime": "20230620 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "10"}
        ]
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M", "1H"]
        mock_adapter.get_origin_time.return_value = None
        
        strategy = MultiTimeframeStrategy()
        engine = BacktestEngine(
            [InstrumentSpec(symbol="COPPER", adapter=mock_adapter)],
            strategy,
            BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
        )
        
        engine.run()
        
        # Should call read_timeframe for both 1M and 1H
        assert mock_adapter.read_timeframe.call_count == 2
        calls = mock_adapter.read_timeframe.call_args_list
        timeframes_called = [call[0][0] for call in calls]
        assert "1M" in timeframes_called
        assert "1H" in timeframes_called

    def test_engine_aggregates_1h_from_1m_when_native_unsupported(self):
        """Engine should work when adapter aggregates 1H from 1M data."""
        # Create 120 minutes of 1M data (2 hours) - use NSE market hours (9:15-15:30)
        # Start from 9:15 to ensure all data is within market hours
        rows = []
        for i in range(120):
            minute = (15 + i) % 60
            hour = 9 + (15 + i) // 60
            rows.append([f"20230620", f"{hour:02d}:{minute:02d}", "100.00", "101.00", "99.00", "100.50", "10"])
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
            strategy = MultiTimeframeStrategy()
            engine = BacktestEngine(
                [InstrumentSpec(symbol="COPPER", adapter=adapter)],
                strategy,
                BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
            )
            
            engine.run()
            
            # Should have processed 120 1M candles and 2 1H candles
            assert len(strategy.candles_1m) == 120
            assert len(strategy.candles_1h) == 2

    def test_engine_raises_when_timeframe_unavailable_and_no_1m(self):
        """Engine should raise ProviderError when timeframe unavailable and 1M not available."""
        rows = [["20230620", "19:00", "100.00", "101.00", "99.00", "100.50", "10"]]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False, minute_data_available=False)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            strategy = MultiTimeframeStrategy()
            engine = BacktestEngine(
                [InstrumentSpec(symbol="COPPER", adapter=adapter)],
                strategy,
                BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
            )
            
            try:
                engine.run()
                assert False, "Should have raised ProviderError"
            except ProviderError as e:
                # Error now comes from DataOrchestrator which wraps adapter error
                assert "Failed to read data" in str(e)
                assert "1M" in str(e)
                assert "1-minute data is unavailable" in str(e)

    def test_engine_computes_indicators_per_timeframe(self):
        """Engine should call compute_indicators once per timeframe."""
        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read_timeframe.return_value = [
            {"datetime": "20230620 19:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "10"}
        ]
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M", "1H"]
        mock_adapter.get_origin_time.return_value = None
        
        class IndicatorStrategy(MultiTimeframeStrategy):
            def __init__(self):
                super().__init__()
                self.compute_calls = []
            
            def compute_indicators(self, candles, timeframe=None):
                self.compute_calls.append(timeframe)
                return [{} for _ in candles]
        
        strategy = IndicatorStrategy()
        engine = BacktestEngine(
            [InstrumentSpec(symbol="COPPER", adapter=mock_adapter)],
            strategy,
            BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
        )
        
        engine.run()
        
        # Should call compute_indicators for both timeframes
        assert "1M" in strategy.compute_calls
        assert "1H" in strategy.compute_calls
        assert len(strategy.compute_calls) == 2