import csv
import tempfile
import os
from pathlib import Path
import pytest

from quantrex_data.providers.csv_reader import CSVReader

EXAMPLE_DATA_DIR = Path(__file__).parent.parent.parent.parent / "example_csv_data"


class TestCSVReaderIndexMode:
    """Tests for index mode (headerless CSV)"""

    def test_index_mode_basic(self):
        """Test basic index mode with example data format"""
        mapping = {
            "datetime": [0, 1],
            "open": 2,
            "high": 3,
            "low": 4,
            "close": 5,
            "volume": 6,
        }
        reader = CSVReader(str(EXAMPLE_DATA_DIR / "COPPER23AUGFUT.csv"), mapping)
        results = reader.read()

        assert len(results) > 0
        first = results[0]
        assert "datetime" in first
        assert "open" in first
        assert "high" in first
        assert "low" in first
        assert "close" in first
        assert "volume" in first
        assert first["datetime"] == "20230620 19:00"
        assert first["open"] == "737.20"
        assert first["high"] == "737.20"
        assert first["low"] == "737.20"
        assert first["close"] == "737.20"
        assert first["volume"] == "1"

    def test_index_mode_with_additional_fields(self):
        """Test index mode with extra fields beyond OHLCV"""
        mapping = {
            "datetime": [0, 1],
            "open": 2,
            "high": 3,
            "low": 4,
            "close": 5,
            "volume": 6,
            "oi": 7,
        }
        reader = CSVReader(str(EXAMPLE_DATA_DIR / "COPPER23AUGFUT.csv"), mapping)
        results = reader.read()

        assert len(results) > 0
        assert "oi" in results[0]
        assert results[0]["oi"] == "1"

    def test_index_mode_single_datetime_column(self):
        """Test index mode with datetime as single column"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("20230620 19:00,737.20,737.20,737.20,737.20,1\n")
            f.write("20230621 10:06,740.00,740.00,740.00,740.00,2\n")
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
            results = reader.read()

            assert len(results) == 2
            assert results[0]["datetime"] == "20230620 19:00"
            assert results[1]["datetime"] == "20230621 10:06"
        finally:
            os.unlink(temp_path)


class TestCSVReaderHeaderMode:
    """Tests for header mode (CSV with headers)"""

    def test_header_mode_basic(self):
        """Test header mode with standard CSV headers"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("timestamp,open,high,low,close,volume\n")
            f.write("20230620 19:00,737.20,737.20,737.20,737.20,1\n")
            f.write("20230621 10:06,740.00,740.00,740.00,740.00,2\n")
            temp_path = f.name

        try:
            mapping = {
                "datetime": "timestamp",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            }
            reader = CSVReader(temp_path, mapping)
            results = reader.read()

            assert len(results) == 2
            assert results[0]["datetime"] == "20230620 19:00"
            assert results[0]["open"] == "737.20"
            assert results[1]["datetime"] == "20230621 10:06"
        finally:
            os.unlink(temp_path)

    def test_header_mode_with_additional_fields(self):
        """Test header mode with extra fields"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("timestamp,open,high,low,close,volume,open_interest\n")
            f.write("20230620 19:00,737.20,737.20,737.20,737.20,1,100\n")
            temp_path = f.name

        try:
            mapping = {
                "datetime": "timestamp",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
                "open_interest": "open_interest",
            }
            reader = CSVReader(temp_path, mapping)
            results = reader.read()

            assert len(results) == 1
            assert results[0]["open_interest"] == "100"
        finally:
            os.unlink(temp_path)

    def test_header_mode_multi_column_datetime(self):
        """Test header mode with datetime split across multiple columns"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("date,time,open,high,low,close,volume\n")
            f.write("20230620,19:00,737.20,737.20,737.20,737.20,1\n")
            temp_path = f.name

        try:
            mapping = {
                "datetime": ["date", "time"],
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            }
            reader = CSVReader(temp_path, mapping)
            results = reader.read()

            assert len(results) == 1
            assert results[0]["datetime"] == "20230620 19:00"
        finally:
            os.unlink(temp_path)


class TestCSVReaderValidation:
    """Tests for validation and error handling"""

    def test_missing_required_keys(self):
        """Test that missing required keys raises ValueError"""
        mapping = {
            "datetime": [0, 1],
            "open": 2,
            "high": 3,
            # missing low, close, volume
        }
        with pytest.raises(ValueError, match="missing required keys"):
            CSVReader("example_csv_data/COPPER23AUGFUT.csv", mapping).read()

    def test_mixed_mode_raises_error(self):
        """Test that mixing index and header modes raises ValueError"""
        mapping = {
            "datetime": [0, 1],  # index mode
            "open": "open",      # header mode
            "high": 3,
            "low": 4,
            "close": 5,
            "volume": 6,
        }
        with pytest.raises(ValueError, match="cannot mix"):
            CSVReader("example_csv_data/COPPER23AUGFUT.csv", mapping).read()

    def test_invalid_datetime_spec(self):
        """Test that invalid datetime spec raises ValueError"""
        mapping = {
            "datetime": {"invalid": "spec"},
            "open": 2,
            "high": 3,
            "low": 4,
            "close": 5,
            "volume": 6,
        }
        with pytest.raises(ValueError, match="datetime mapping must be"):
            CSVReader("example_csv_data/COPPER23AUGFUT.csv", mapping).read()

    def test_header_not_found(self):
        """Test that missing header raises ValueError"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("timestamp,open,high,low,close,volume\n")
            f.write("20230620 19:00,737.20,737.20,737.20,737.20,1\n")
            temp_path = f.name

        try:
            mapping = {
                "datetime": "nonexistent",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            }
            with pytest.raises(ValueError, match="not found in CSV header"):
                CSVReader(temp_path, mapping).read()
        finally:
            os.unlink(temp_path)

    def test_index_out_of_bounds(self):
        """Test that index out of bounds raises IndexError"""
        mapping = {
            "datetime": [0, 1],
            "open": 2,
            "high": 3,
            "low": 4,
            "close": 5,
            "volume": 999,  # out of bounds
        }
        reader = CSVReader(str(EXAMPLE_DATA_DIR / "COPPER23AUGFUT.csv"), mapping)
        results = reader.read()

        # Should skip the malformed row and continue
        assert len(results) == 0  # All rows will fail due to volume index

    def test_malformed_row_handling(self):
        """Test that malformed rows are skipped with WARNING log"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("20230620,19:00,737.20,737.20,737.20,737.20,1\n")
            f.write("bad,row\n")  # malformed
            f.write("20230621,10:06,740.00,740.00,740.00,740.00,2\n")
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
            results = reader.read()

            # Should skip malformed row and process valid ones
            assert len(results) == 2
            assert results[0]["datetime"] == "20230620 19:00"
            assert results[1]["datetime"] == "20230621 10:06"
        finally:
            os.unlink(temp_path)

    def test_empty_file(self):
        """Test empty file returns empty list"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
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
            results = reader.read()

            assert results == []
        finally:
            os.unlink(temp_path)

    def test_no_column_mapping_raises_error(self):
        """Test that missing column_mapping raises ValueError"""
        with pytest.raises(ValueError, match="column_mapping is required"):
            CSVReader("example_csv_data/COPPER23AUGFUT.csv", {}).read()


class TestCSVReaderEdgeCases:
    """Edge case tests"""

    def test_all_rows_malformed(self):
        """Test file where all rows are malformed"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("bad,row\n")
            f.write("also,bad\n")
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
            results = reader.read()

            assert results == []
        finally:
            os.unlink(temp_path)

    def test_header_mode_empty_data_rows(self):
        """Test header mode with only header row"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("timestamp,open,high,low,close,volume\n")
            temp_path = f.name

        try:
            mapping = {
                "datetime": "timestamp",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            }
            reader = CSVReader(temp_path, mapping)
            results = reader.read()

            assert results == []
        finally:
            os.unlink(temp_path)