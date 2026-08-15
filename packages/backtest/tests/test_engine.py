"""Tests for BacktestEngine."""

from unittest.mock import Mock, MagicMock
from datetime import datetime

from quantrex_core.models import Candle
from quantrex_core.strategy.base import Strategy
from quantrex_data.providers.csv_reader import CSVReader
from quantrex_backtest import BacktestEngine
from quantrex_backtest.exceptions.backtest_error import ProviderError
from quantrex_core.protocols import DataFeeder
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


class TestBacktestEngine:
    """Tests for BacktestEngine core functionality."""

    def test_engine_rejects_none_feeder(self):
        """Engine should raise ProviderError when feeder is None."""
        strategy = TestStrategy()
        try:
            BacktestEngine(None, strategy, symbol="COPPER")
            assert False, "Should have raised ProviderError"
        except ProviderError as e:
            assert "DataFeeder is required" in str(e)

    def test_engine_rejects_none_strategy(self):
        """Engine should raise ProviderError when strategy is None."""
        mock_feeder = Mock(spec=DataFeeder)
        mock_feeder.read.return_value = []
        try:
            BacktestEngine(mock_feeder, None, symbol="COPPER")
            assert False, "Should have raised ProviderError"
        except ProviderError as e:
            assert "Strategy is required" in str(e)

    def test_engine_accepts_valid_feeder_and_strategy(self):
        """Engine should accept a valid DataFeeder and Strategy."""
        mock_feeder = Mock(spec=DataFeeder)
        mock_feeder.read.return_value = []
        strategy = TestStrategy()

        engine = BacktestEngine(mock_feeder, strategy, symbol="COPPER")
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
            mapping = {
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            }
            reader = CSVReader(temp_path, mapping)
            strategy = TestStrategy()
            engine = BacktestEngine(reader, strategy, symbol="COPPER")

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
            mapping = {
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            }
            reader = CSVReader(temp_path, mapping)
            strategy = TestStrategy()
            engine = BacktestEngine(reader, strategy, symbol="COPPER")

            engine.run()

            assert len(strategy.candles) == 3
            for candle in strategy.candles:
                assert isinstance(candle, Candle)
                assert candle.symbol == "COPPER"

    def test_engine_calls_lifecycle_methods(self):
        """Engine should call on_start before and on_stop after processing."""
        mock_feeder = Mock(spec=DataFeeder)
        mock_feeder.read.return_value = [
            {"datetime": "20230620 19:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "10"}
        ]
        strategy = TestStrategy()
        engine = BacktestEngine(mock_feeder, strategy, symbol="COPPER")

        engine.run()

        assert strategy.started is True
        assert strategy.stopped is True
        assert len(strategy.candles) == 1

    def test_engine_handles_empty_data(self):
        """Engine should handle empty data gracefully."""
        mock_feeder = Mock(spec=DataFeeder)
        mock_feeder.read.return_value = []

        strategy = TestStrategy()
        engine = BacktestEngine(mock_feeder, strategy, symbol="COPPER")

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
            mapping = {
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            }
            reader = CSVReader(temp_path, mapping)
            strategy = TestStrategy()
            engine = BacktestEngine(reader, strategy, symbol="COPPER")

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

    def test_engine_raises_on_feeder_read_failure(self):
        """Engine should wrap feeder read() failures in ProviderError."""
        mock_feeder = Mock(spec=DataFeeder)
        mock_feeder.read.side_effect = IOError("Disk error")
        strategy = TestStrategy()

        engine = BacktestEngine(mock_feeder, strategy, symbol="COPPER")

        try:
            engine.run()
            assert False, "Should have raised ProviderError"
        except ProviderError as e:
            assert "Failed to read data from feeder" in str(e)
            assert "Disk error" in str(e)

    def test_engine_raises_on_invalid_candle_data(self):
        """Engine should raise ProviderError for malformed candle data."""
        # CSV with invalid float value
        rows = [
            ["20230620", "19:00", "not_a_number", "738.00", "736.50", "737.50", "100", "50"],
        ]
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            mapping = {
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            }
            reader = CSVReader(temp_path, mapping)
            strategy = TestStrategy()
            engine = BacktestEngine(reader, strategy, symbol="COPPER")

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
            mapping = {
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            }
            reader = CSVReader(temp_path, mapping)
            
            strategy1 = TestStrategy()
            engine1 = BacktestEngine(reader, strategy1, symbol="COPPER")
            engine1.run()
            run1_timestamps = [c.timestamp for c in strategy1.candles]

            strategy2 = TestStrategy()
            engine2 = BacktestEngine(reader, strategy2, symbol="COPPER")
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
            mapping = {
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            }
            reader = CSVReader(temp_path, mapping)
            strategy = TestStrategy()
            engine = BacktestEngine(reader, strategy, symbol="COPPER", datetime_format="%d-%m-%Y %H:%M")

            engine.run()

            assert len(strategy.candles) == 1
            assert strategy.candles[0].timestamp == datetime(2023, 6, 20, 19, 0)

    def test_engine_with_mock_feeder(self):
        """Engine should work with a mock feeder returning dict rows."""
        mock_feeder = Mock(spec=DataFeeder)
        mock_feeder.read.return_value = [
            {"datetime": "20230620 19:00", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "10"},
            {"datetime": "20230621 10:00", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "20"},
        ]
        strategy = TestStrategy()
        engine = BacktestEngine(mock_feeder, strategy, symbol="COPPER")

        engine.run()

        assert len(strategy.candles) == 2
        assert strategy.candles[0].close == 100.0
        assert strategy.candles[1].close == 101.0