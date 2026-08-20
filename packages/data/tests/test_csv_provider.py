"""Tests for CSVDataProvider."""

import pytest
from quantrex_data.providers.csv_provider import CSVDataProvider
from quantrex_test_support.csv import csv_rows_to_string, create_temp_csv


class TestCSVDataProvider:
    """Tests for CSVDataProvider raw CSV reading."""

    def test_provider_reads_csv_without_header(self):
        """Provider should read raw rows from CSV without header."""
        rows = [
            ["20230620", "19:00", "737.20", "737.20", "737.20", "737.20", "1"],
            ["20230621", "10:06", "740.00", "740.00", "740.00", "740.00", "2"],
        ]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            result = provider.fetch()
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == ["20230620", "19:00", "737.20", "737.20", "737.20", "737.20", "1"]
        assert result[1] == ["20230621", "10:06", "740.00", "740.00", "740.00", "740.00", "2"]

    def test_provider_reads_csv_with_header(self):
        """Provider should separate header from data rows."""
        rows = [
            ["timestamp", "open", "high", "low", "close", "volume"],
            ["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"],
            ["20230621 10:06", "740.00", "740.00", "740.00", "740.00", "2"],
        ]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=True)
            result = provider.fetch()
        
        assert isinstance(result, tuple)
        header, data_rows = result
        assert header == ["timestamp", "open", "high", "low", "close", "volume"]
        assert len(data_rows) == 2
        assert data_rows[0] == ["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"]
        assert data_rows[1] == ["20230621 10:06", "740.00", "740.00", "740.00", "740.00", "2"]

    def test_provider_header_property(self):
        """Provider should expose header property when has_header=True."""
        rows = [
            ["timestamp", "open", "high", "low", "close", "volume"],
            ["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"],
        ]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=True)
            provider.fetch()  # Must call fetch first
            assert provider.header == ["timestamp", "open", "high", "low", "close", "volume"]

    def test_provider_header_property_none_without_header(self):
        """Provider header should be None when has_header=False."""
        rows = [
            ["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"],
        ]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            provider.fetch()
            assert provider.header is None

    def test_provider_empty_csv(self):
        """Provider should handle empty CSV files."""
        csv_content = ""
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            result = provider.fetch()
        
        assert result == []

    def test_provider_empty_csv_with_header(self):
        """Provider should handle CSV with only header."""
        rows = [["timestamp", "open", "high", "low", "close", "volume"]]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=True)
            result = provider.fetch()
        
        assert isinstance(result, tuple)
        header, data_rows = result
        assert header == ["timestamp", "open", "high", "low", "close", "volume"]
        assert data_rows == []

    def test_provider_file_not_found(self):
        """Provider should raise FileNotFoundError for missing file."""
        provider = CSVDataProvider("/nonexistent/path.csv", has_header=False)
        with pytest.raises(FileNotFoundError):
            provider.fetch()

    def test_provider_close_method(self):
        """Provider close() should not raise."""
        rows = [["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"]]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            provider.fetch()
            provider.close()  # Should not raise

    def test_provider_file_path_property(self):
        """Provider should expose file_path property."""
        rows = [["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"]]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            from pathlib import Path
            assert provider.file_path == Path(temp_path)