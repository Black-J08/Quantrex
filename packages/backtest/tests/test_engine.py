"""Tests for BacktestEngine."""

import tempfile
import os
from unittest.mock import Mock, MagicMock
from datetime import datetime

from quantrex_data.providers.csv_reader import CSVReader
from quantrex_backtest import BacktestEngine, Candle
from quantrex_backtest.exceptions.backtest_error import ProviderError
from quantrex_backtest.feeders.data_feeder import DataFeeder


class TestBacktestEngine:
    """Tests for BacktestEngine core functionality."""

    def test_engine_rejects_none_feeder(self):
        """Engine should raise ProviderError when feeder is None."""
        try:
            BacktestEngine(None, symbol="COPPER")
            assert False, "Should have raised ProviderError"
        except ProviderError as e:
            assert "DataFeeder is required" in str(e)

    def test_engine_accepts_valid_feeder(self):
        """Engine should accept a valid DataFeeder."""
        mock_feeder = Mock(spec=DataFeeder)
        mock_feeder.read.return_value = []

        engine = BacktestEngine(mock_feeder, symbol="COPPER")
        assert engine is not None

    def test_engine_processes_candles_in_timestamp_order(self):
        """Engine should process candles sorted by timestamp."""
        # Create CSV with out-of-order timestamps
        csv_content = (
            "20230621,10:06,740.00,740.00,740.00,740.00,2,1\n"  # Later
            "20230620,19:00,737.20,737.20,737.20,737.20,1,1\n"  # Earlier
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            mapping = {
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            }
            reader = CSVReader(temp_path, mapping)
            engine = BacktestEngine(reader, symbol="COPPER")

            received_candles = []
            engine.run(lambda c: received_candles.append(c))

            assert len(received_candles) == 2
            # Should be sorted by timestamp (earlier first)
            assert received_candles[0].timestamp == datetime(2023, 6, 20, 19, 0)
            assert received_candles[1].timestamp == datetime(2023, 6, 21, 10, 6)
        finally:
            os.unlink(temp_path)

    def test_engine_calls_callback_for_each_candle(self):
        """Engine should invoke on_candle callback for each candle."""
        csv_content = (
            "20230620,19:00,737.20,737.20,737.20,737.20,1,1\n"
            "20230621,10:06,740.00,740.00,740.00,740.00,2,1\n"
            "20230621,10:36,738.60,738.60,738.60,738.60,1,2\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            mapping = {
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            }
            reader = CSVReader(temp_path, mapping)
            engine = BacktestEngine(reader, symbol="COPPER")

            callback = Mock()
            engine.run(callback)

            assert callback.call_count == 3
            for call_args in callback.call_args_list:
                candle = call_args[0][0]
                assert isinstance(candle, Candle)
                assert candle.symbol == "COPPER"
        finally:
            os.unlink(temp_path)

    def test_engine_handles_empty_data(self):
        """Engine should handle empty data gracefully."""
        mock_feeder = Mock(spec=DataFeeder)
        mock_feeder.read.return_value = []

        engine = BacktestEngine(mock_feeder, symbol="COPPER")
        callback = Mock()

        engine.run(callback)

        callback.assert_not_called()

    def test_engine_passes_candle_with_correct_values(self):
        """Engine should pass correctly parsed Candle to callback."""
        csv_content = "20230620,19:00,737.20,738.00,736.50,737.50,100,50\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            mapping = {
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            }
            reader = CSVReader(temp_path, mapping)
            engine = BacktestEngine(reader, symbol="COPPER")

            received = []
            engine.run(lambda c: received.append(c))

            assert len(received) == 1
            candle = received[0]
            assert candle.symbol == "COPPER"
            assert candle.timestamp == datetime(2023, 6, 20, 19, 0)
            assert candle.open == 737.20
            assert candle.high == 738.00
            assert candle.low == 736.50
            assert candle.close == 737.50
            assert candle.volume == 100.0
        finally:
            os.unlink(temp_path)

    def test_engine_raises_on_feeder_read_failure(self):
        """Engine should wrap feeder read() failures in ProviderError."""
        mock_feeder = Mock(spec=DataFeeder)
        mock_feeder.read.side_effect = IOError("Disk error")

        engine = BacktestEngine(mock_feeder, symbol="COPPER")

        try:
            engine.run(lambda c: None)
            assert False, "Should have raised ProviderError"
        except ProviderError as e:
            assert "Failed to read data from feeder" in str(e)
            assert "Disk error" in str(e)

    def test_engine_raises_on_invalid_candle_data(self):
        """Engine should raise ProviderError for malformed candle data."""
        # CSV with invalid float value
        csv_content = "20230620,19:00,not_a_number,738.00,736.50,737.50,100,50\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            mapping = {
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            }
            reader = CSVReader(temp_path, mapping)
            engine = BacktestEngine(reader, symbol="COPPER")

            try:
                engine.run(lambda c: None)
                assert False, "Should have raised ProviderError"
            except ProviderError as e:
                assert "Failed to process candle" in str(e)
        finally:
            os.unlink(temp_path)

    def test_engine_deterministic_order(self):
        """Engine should produce identical callback sequence on repeated runs."""
        csv_content = (
            "20230621,10:06,740.00,740.00,740.00,740.00,2,1\n"
            "20230620,19:00,737.20,737.20,737.20,737.20,1,1\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            mapping = {
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            }
            reader = CSVReader(temp_path, mapping)
            engine = BacktestEngine(reader, symbol="COPPER")

            run1_timestamps = []
            engine.run(lambda c: run1_timestamps.append(c.timestamp))

            run2_timestamps = []
            engine.run(lambda c: run2_timestamps.append(c.timestamp))

            assert run1_timestamps == run2_timestamps
            assert run1_timestamps == [datetime(2023, 6, 20, 19, 0), datetime(2023, 6, 21, 10, 6)]
        finally:
            os.unlink(temp_path)

    def test_engine_custom_datetime_format(self):
        """Engine should respect custom datetime_format parameter."""
        csv_content = "2023-06-20 19:00:00,737.20,738.00,736.50,737.50,100\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            mapping = {
                "datetime": 0,
                "open": 1,
                "high": 2,
                "low": 3,
                "close": 4,
                "volume": 5,
            }
            reader = CSVReader(temp_path, mapping)
            engine = BacktestEngine(reader, symbol="COPPER", datetime_format="%Y-%m-%d %H:%M:%S")

            received = []
            engine.run(lambda c: received.append(c))

            assert len(received) == 1
            assert received[0].timestamp == datetime(2023, 6, 20, 19, 0, 0)
        finally:
            os.unlink(temp_path)

    def test_engine_with_mock_feeder(self):
        """Engine should work with any DataFeeder implementation."""
        mock_feeder = Mock(spec=DataFeeder)
        mock_feeder.read.return_value = [
            {"datetime": "20230620 19:00", "open": "100", "high": "101", "low": "99", "close": "100.5", "volume": "10"},
            {"datetime": "20230621 10:00", "open": "100.5", "high": "102", "low": "100", "close": "101", "volume": "20"},
        ]

        engine = BacktestEngine(mock_feeder, symbol="TEST")
        received = []
        engine.run(lambda c: received.append(c))

        assert len(received) == 2
        assert received[0].symbol == "TEST"
        assert received[0].open == 100.0
        assert received[1].close == 101.0