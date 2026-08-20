"""Tests for DataAdapter protocol compliance."""

from quantrex_data.providers.csv_provider import CSVDataProvider
from quantrex_data.adapters.csv_adapter import CSVDataAdapter
from quantrex_core.protocols import DataAdapter
from quantrex_test_support.csv import (
    make_ohlc_series,
    csv_rows_to_string,
    create_temp_csv,
)


class TestDataAdapterProtocol:
    """Verify CSVDataAdapter satisfies the DataAdapter protocol."""

    def test_csv_adapter_implements_data_adapter(self):
        """CSVDataAdapter should satisfy DataAdapter protocol via duck typing."""
        # Create a minimal CSV file using test-support
        rows = make_ohlc_series(num_rows=1, seed=42)
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

            # Verify it has the required read() method
            assert hasattr(adapter, "read")
            assert callable(adapter.read)

            # Verify it has close() method
            assert hasattr(adapter, "close")
            assert callable(adapter.close)

            # Verify it returns list[dict]
            result = adapter.read()
            assert isinstance(result, list)
            assert len(result) == 1
            assert isinstance(result[0], dict)
            assert "datetime" in result[0]
            assert "open" in result[0]
            assert "high" in result[0]
            assert "low" in result[0]
            assert "close" in result[0]
            assert "volume" in result[0]

            # Protocol compliance: can be used where DataAdapter is expected
            adapter_instance: DataAdapter = adapter
            assert adapter_instance.read() == result

    def test_csv_adapter_read_returns_expected_shape(self):
        """CSVDataAdapter.read() returns list of dicts with required keys."""
        rows = make_ohlc_series(num_rows=2, seed=42)
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
            result = adapter.read()

            assert len(result) == 2
            for row in result:
                assert set(row.keys()) >= {"datetime", "open", "high", "low", "close", "volume"}