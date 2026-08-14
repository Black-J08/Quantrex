"""Tests for DataFeeder protocol compliance."""

from quantrex_data.providers.csv_reader import CSVReader
from quantrex_backtest.feeders.data_feeder import DataFeeder
from quantrex_test_support.csv import (
    make_ohlc_series,
    csv_rows_to_string,
    create_temp_csv,
)


class TestDataFeederProtocol:
    """Verify CSVReader satisfies the DataFeeder protocol."""

    def test_csv_reader_implements_data_feeder(self):
        """CSVReader should satisfy DataFeeder protocol via duck typing."""
        # Create a minimal CSV file using test-support
        rows = make_ohlc_series(num_rows=1, seed=42)
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

    def test_csv_reader_read_returns_expected_shape(self):
        """CSVReader.read() returns list of dicts with required keys."""
        rows = make_ohlc_series(num_rows=2, seed=42)
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
            result = reader.read()

            assert len(result) == 2
            for row in result:
                assert set(row.keys()) >= {"datetime", "open", "high", "low", "close", "volume"}