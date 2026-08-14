"""Tests for DataFeeder protocol compliance."""

import tempfile
import os
from quantrex_data.providers.csv_reader import CSVReader
from quantrex_backtest.feeders.data_feeder import DataFeeder


class TestDataFeederProtocol:
    """Verify CSVReader satisfies the DataFeeder protocol."""

    def test_csv_reader_implements_data_feeder(self):
        """CSVReader should satisfy DataFeeder protocol via duck typing."""
        # Create a minimal CSV file
        csv_content = "20230620,19:00,737.20,737.20,737.20,737.20,1,1\n"
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

            # Verify it has the required read() method
            assert hasattr(reader, "read")
            assert callable(reader.read)

            # Verify it returns list[dict]
            result = reader.read()
            assert isinstance(result, list)
            assert len(result) == 1
            assert isinstance(result[0], dict)
            assert "datetime" in result[0]
            assert "open" in result[0]
            assert "high" in result[0]
            assert "low" in result[0]
            assert "close" in result[0]
            assert "volume" in result[0]

            # Protocol compliance: can be used where DataFeeder is expected
            feeder: DataFeeder = reader
            assert feeder.read() == result
        finally:
            os.unlink(temp_path)

    def test_csv_reader_read_returns_expected_shape(self):
        """CSVReader.read() returns list of dicts with required keys."""
        csv_content = (
            "20230620,19:00,737.20,737.20,737.20,737.20,1,1\n"
            "20230621,10:06,740.00,740.00,740.00,740.00,2,1\n"
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
            result = reader.read()

            assert len(result) == 2
            for row in result:
                assert set(row.keys()) >= {"datetime", "open", "high", "low", "close", "volume"}
        finally:
            os.unlink(temp_path)