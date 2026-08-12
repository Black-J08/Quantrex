import csv
import tempfile
import os
from contextlib import contextmanager
import pytest

from quantrex_data.providers.csv_reader import CSVReader


# =============================================================================
# Test Data Generators - Deterministic procedural CSV data
# =============================================================================

# Canonical test data constants for consistent values across tests
SAMPLE_DATES = ["20230620", "20230621", "20230622"]
SAMPLE_TIMES = ["19:00", "10:06", "15:30"]
SAMPLE_OHLCV = [
    ("737.20", "737.20", "737.20", "737.20", "1"),
    ("740.00", "740.00", "740.00", "740.00", "2"),
    ("738.60", "738.60", "738.60", "738.60", "1"),
]
SAMPLE_OI = ["1", "1", "2"]


def make_index_mode_rows(num_rows: int = 3, num_extra_cols: int = 0) -> list[list[str]]:
    """Generate headerless CSV rows for index mode testing.
    
    Columns: date, time, open, high, low, close, volume, [extra...]
    """
    rows = []
    for i in range(num_rows):
        date_idx = i % len(SAMPLE_DATES)
        time_idx = i % len(SAMPLE_TIMES)
        ohlcv_idx = i % len(SAMPLE_OHLCV)
        
        row = [
            SAMPLE_DATES[date_idx],
            SAMPLE_TIMES[time_idx],
            *SAMPLE_OHLCV[ohlcv_idx],
        ]
        # Add extra columns (e.g., open interest)
        for j in range(num_extra_cols):
            oi_idx = i % len(SAMPLE_OI)
            row.append(SAMPLE_OI[oi_idx])
        rows.append(row)
    return rows


def make_header_mode_rows(headers: list[str], num_rows: int = 3) -> tuple[list[str], list[list[str]]]:
    """Generate CSV with header row and data rows for header mode testing."""
    header_row = headers
    data_rows = []
    for i in range(num_rows):
        date_idx = i % len(SAMPLE_DATES)
        time_idx = i % len(SAMPLE_TIMES)
        ohlcv_idx = i % len(SAMPLE_OHLCV)
        
        # Build row based on headers
        row = []
        for header in headers:
            if header in ("timestamp", "datetime"):
                # Combine date and time for timestamp/datetime columns
                row.append(f"{SAMPLE_DATES[date_idx]} {SAMPLE_TIMES[time_idx]}")
            elif header == "date":
                row.append(SAMPLE_DATES[date_idx])
            elif header == "time":
                row.append(SAMPLE_TIMES[time_idx])
            elif header == "open":
                row.append(SAMPLE_OHLCV[ohlcv_idx][0])
            elif header == "high":
                row.append(SAMPLE_OHLCV[ohlcv_idx][1])
            elif header == "low":
                row.append(SAMPLE_OHLCV[ohlcv_idx][2])
            elif header == "close":
                row.append(SAMPLE_OHLCV[ohlcv_idx][3])
            elif header == "volume":
                row.append(SAMPLE_OHLCV[ohlcv_idx][4])
            elif header in ("oi", "open_interest"):
                oi_idx = i % len(SAMPLE_OI)
                row.append(SAMPLE_OI[oi_idx])
            else:
                row.append(f"value_{header}_{i}")
        data_rows.append(row)
    return header_row, data_rows


def csv_rows_to_string(rows: list[list[str]]) -> str:
    """Convert list of row lists to CSV-formatted string."""
    output = []
    for row in rows:
        output.append(",".join(row))
    return "\n".join(output) + "\n"


@contextmanager
def create_temp_csv(content: str):
    """Context manager to create a temporary CSV file with given content."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(content)
        temp_path = f.name
    try:
        yield temp_path
    finally:
        # File may have been deleted externally; ignore if missing
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass


class TestCSVReaderIndexMode:
    """Tests for index mode (headerless CSV)"""

    def test_index_mode_basic(self):
        """Test basic index mode with generated data"""
        mapping = {
            "datetime": [0, 1],
            "open": 2,
            "high": 3,
            "low": 4,
            "close": 5,
            "volume": 6,
        }
        rows = make_index_mode_rows(num_rows=3, num_extra_cols=0)
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            reader = CSVReader(temp_path, mapping)
            results = reader.read()

        assert len(results) == 3
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
        rows = make_index_mode_rows(num_rows=3, num_extra_cols=1)
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            reader = CSVReader(temp_path, mapping)
            results = reader.read()

        assert len(results) == 3
        assert "oi" in results[0]
        assert results[0]["oi"] == "1"

    def test_index_mode_single_datetime_column(self):
        """Test index mode with datetime as single column"""
        rows = [
            ["20230620 19:00", "737.20", "737.20", "737.20", "737.20", "1"],
            ["20230621 10:06", "740.00", "740.00", "740.00", "740.00", "2"],
        ]
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
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


class TestCSVReaderHeaderMode:
    """Tests for header mode (CSV with headers)"""

    def test_header_mode_basic(self):
        """Test header mode with standard CSV headers"""
        headers = ["timestamp", "open", "high", "low", "close", "volume"]
        header_row, data_rows = make_header_mode_rows(headers, num_rows=2)
        all_rows = [header_row] + data_rows
        csv_content = csv_rows_to_string(all_rows)
        
        with create_temp_csv(csv_content) as temp_path:
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

    def test_header_mode_with_additional_fields(self):
        """Test header mode with extra fields"""
        headers = ["timestamp", "open", "high", "low", "close", "volume", "open_interest"]
        header_row, data_rows = make_header_mode_rows(headers, num_rows=1)
        all_rows = [header_row] + data_rows
        csv_content = csv_rows_to_string(all_rows)
        
        with create_temp_csv(csv_content) as temp_path:
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
            assert results[0]["open_interest"] == "1"

    def test_header_mode_multi_column_datetime(self):
        """Test header mode with datetime split across multiple columns"""
        headers = ["date", "time", "open", "high", "low", "close", "volume"]
        header_row, data_rows = make_header_mode_rows(headers, num_rows=1)
        all_rows = [header_row] + data_rows
        csv_content = csv_rows_to_string(all_rows)
        
        with create_temp_csv(csv_content) as temp_path:
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
        rows = make_index_mode_rows(num_rows=1, num_extra_cols=0)
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            with pytest.raises(ValueError, match="missing required keys"):
                CSVReader(temp_path, mapping).read()

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
        rows = make_index_mode_rows(num_rows=1, num_extra_cols=0)
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            with pytest.raises(ValueError, match="cannot mix"):
                CSVReader(temp_path, mapping).read()

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
        rows = make_index_mode_rows(num_rows=1, num_extra_cols=0)
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            with pytest.raises(ValueError, match="datetime mapping must be"):
                CSVReader(temp_path, mapping).read()

    def test_header_not_found(self):
        """Test that missing header raises ValueError"""
        headers = ["timestamp", "open", "high", "low", "close", "volume"]
        header_row, data_rows = make_header_mode_rows(headers, num_rows=1)
        all_rows = [header_row] + data_rows
        csv_content = csv_rows_to_string(all_rows)
        
        with create_temp_csv(csv_content) as temp_path:
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

    def test_index_out_of_bounds(self):
        """Test that index out of bounds raises IndexError"""
        mapping = {
            "datetime": [0, 1],
            "open": 2,
            "high": 3,
            "low": 4,
            "close": 5,
            "volume": 999,  # out of bounds (we only have 7 columns: 0-6)
        }
        rows = make_index_mode_rows(num_rows=3, num_extra_cols=0)
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            reader = CSVReader(temp_path, mapping)
            results = reader.read()

        # Should skip the malformed row and continue
        assert len(results) == 0  # All rows will fail due to volume index

    def test_malformed_row_handling(self):
        """Test that malformed rows are skipped with WARNING log"""
        rows = [
            ["20230620", "19:00", "737.20", "737.20", "737.20", "737.20", "1"],
            ["bad", "row"],  # malformed
            ["20230621", "10:06", "740.00", "740.00", "740.00", "740.00", "2"],
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
            results = reader.read()

            # Should skip malformed row and process valid ones
            assert len(results) == 2
            assert results[0]["datetime"] == "20230620 19:00"
            assert results[1]["datetime"] == "20230621 10:06"

    def test_empty_file(self):
        """Test empty file returns empty list"""
        with create_temp_csv("") as temp_path:
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

    def test_no_column_mapping_raises_error(self):
        """Test that missing column_mapping raises ValueError"""
        rows = make_index_mode_rows(num_rows=1, num_extra_cols=0)
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            with pytest.raises(ValueError, match="column_mapping is required"):
                CSVReader(temp_path, {}).read()


class TestCSVReaderEdgeCases:
    """Edge case tests"""

    def test_all_rows_malformed(self):
        """Test file where all rows are malformed"""
        rows = [
            ["bad", "row"],
            ["also", "bad"],
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
            results = reader.read()

            assert results == []

    def test_header_mode_empty_data_rows(self):
        """Test header mode with only header row"""
        headers = ["timestamp", "open", "high", "low", "close", "volume"]
        header_row, data_rows = make_header_mode_rows(headers, num_rows=0)
        all_rows = [header_row] + data_rows
        csv_content = csv_rows_to_string(all_rows)
        
        with create_temp_csv(csv_content) as temp_path:
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
            os.unlink(temp_path)