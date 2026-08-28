"""Tests for CSVDataAdapter."""

import pytest
from quantrex_data.providers.csv_provider import CSVDataProvider
from quantrex_data.adapters.csv_adapter import CSVDataAdapter
from quantrex_test_support.csv import csv_rows_to_string, create_temp_csv


class TestCSVDataAdapter:
    """Tests for CSVDataAdapter normalization."""

    def test_adapter_index_mode_basic(self):
        """Adapter should normalize CSV with index-based mapping."""
        rows = [
            ["20230620", "19:00", "737.20", "737.20", "737.20", "737.20", "1"],
            ["20230621", "10:06", "740.00", "740.00", "740.00", "740.00", "2"],
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
            result = adapter.read()
        
        assert len(result) == 2
        assert result[0]["datetime"] == "20230620 19:00"
        assert result[0]["open"] == "737.20"
        assert result[0]["high"] == "737.20"
        assert result[0]["low"] == "737.20"
        assert result[0]["close"] == "737.20"
        assert result[0]["volume"] == "1"
        assert result[1]["datetime"] == "20230621 10:06"

    def test_adapter_header_mode_basic(self):
        """Adapter should normalize CSV with header-based mapping."""
        rows = [
            ["timestamp", "open", "high", "low", "close", "volume"],
            ["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"],
            ["20230621 10:06", "740.00", "740.00", "740.00", "740.00", "2"],
        ]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=True)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": "timestamp",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            })
            result = adapter.read()
        
        assert len(result) == 2
        assert result[0]["datetime"] == "20230620 19:00"
        assert result[0]["open"] == "737.20"
        assert result[1]["datetime"] == "20230621 10:06"

    def test_adapter_header_mode_multi_column_datetime(self):
        """Adapter should handle datetime split across multiple header columns."""
        rows = [
            ["date", "time", "open", "high", "low", "close", "volume"],
            ["20230620", "19:00", "737.20", "737.20", "737.20", "737.20", "1"],
            ["20230621", "10:06", "740.00", "740.00", "740.00", "740.00", "2"],
        ]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=True)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": ["date", "time"],
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            })
            result = adapter.read()
        
        assert len(result) == 2
        assert result[0]["datetime"] == "20230620 19:00"
        assert result[1]["datetime"] == "20230621 10:06"

    def test_adapter_with_additional_fields(self):
        """Adapter should include additional mapped fields."""
        rows = [
            ["timestamp", "open", "high", "low", "close", "volume", "oi"],
            ["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1", "100"],
            ["20230621 10:06", "740.00", "740.00", "740.00", "740.00", "2", "200"],
        ]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=True)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": "timestamp",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
                "oi": "oi",
            })
            result = adapter.read()
        
        assert len(result) == 2
        assert result[0]["oi"] == "100"
        assert result[1]["oi"] == "200"

    def test_adapter_missing_required_keys_raises(self):
        """Adapter should raise ValueError for missing required keys."""
        rows = [["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"]]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            with pytest.raises(ValueError, match="missing required keys"):
                CSVDataAdapter(provider, column_mapping={
                    "datetime": [0, 1],
                    "open": 2,
                    # missing high, low, close, volume
                }).read()

    def test_adapter_mixed_mode_raises(self):
        """Adapter should raise ValueError for mixed index/header mode."""
        rows = [["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"]]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            with pytest.raises(ValueError, match="cannot mix"):
                CSVDataAdapter(provider, column_mapping={
                    "datetime": [0, 1],  # index mode
                    "open": "open",      # header mode
                    "high": 3,
                    "low": 4,
                    "close": 5,
                    "volume": 6,
                }).read()

    def test_adapter_invalid_datetime_spec_raises(self):
        """Adapter should raise ValueError for invalid datetime spec."""
        rows = [["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"]]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            with pytest.raises(ValueError, match="datetime mapping must be"):
                CSVDataAdapter(provider, column_mapping={
                    "datetime": {"invalid": "spec"},
                    "open": 2,
                    "high": 3,
                    "low": 4,
                    "close": 5,
                    "volume": 6,
                }).read()

    def test_adapter_header_not_found_raises(self):
        """Adapter should raise ValueError for missing header."""
        rows = [
            ["timestamp", "open", "high", "low", "close", "volume"],
            ["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"],
        ]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=True)
            with pytest.raises(ValueError, match="not found in CSV header"):
                CSVDataAdapter(provider, column_mapping={
                    "datetime": "nonexistent",
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "volume": "volume",
                }).read()

    def test_adapter_index_out_of_bounds_skips_row(self):
        """Adapter should skip rows with out of bounds column index (with warning)."""
        rows = [["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"]]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 10,  # out of bounds
            })
            result = adapter.read()
        
        # Row should be skipped, result should be empty
        assert len(result) == 0

    def test_adapter_skips_malformed_rows(self):
        """Adapter should skip malformed rows with warning."""
        rows = [
            ["20230620", "19:00", "737.20", "737.20", "737.20", "737.20", "1"],
            ["bad", "row"],  # malformed
            ["20230621", "10:06", "740.00", "740.00", "740.00", "740.00", "2"],
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
            result = adapter.read()
        
        assert len(result) == 2  # malformed row skipped

    def test_adapter_close_delegates_to_provider(self):
        """Adapter close() should delegate to provider."""
        rows = [["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"]]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 5,
            })
            adapter.read()
            adapter.close()  # Should not raise

    def test_adapter_rejects_non_csv_provider(self):
        """Adapter should reject non-CSVDataProvider instances."""
        class FakeProvider:
            def fetch(self): return []
            def close(self): pass
        
        with pytest.raises(TypeError, match="CSVDataProvider"):
            CSVDataAdapter(FakeProvider(), column_mapping={
                "datetime": 0,
                "open": 1,
                "high": 2,
                "low": 3,
                "close": 4,
                "volume": 5,
            })

    def test_adapter_datetime_format_property(self):
        """Adapter should expose datetime_format property (single source of truth)."""
        rows = [["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"]]
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
            assert adapter.datetime_format == "%d-%m-%Y %H:%M"

    def test_adapter_datetime_format_default(self):
        """Adapter datetime_format property should return the default."""
        rows = [["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"]]
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
            )
            assert adapter.datetime_format == "%Y%m%d %H:%M"