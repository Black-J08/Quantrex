import pytest

from quantrex_data.providers.csv_reader import CSVReader
from quantrex_test_support.csv import (
    make_ohlc_series,
    csv_rows_to_string,
    create_temp_csv,
)


def _make_header_mode_rows(headers: list[str], num_rows: int = 3) -> tuple[list[str], list[list[str]]]:
    """Generate CSV with header row and data rows for header mode testing."""
    index_rows = make_ohlc_series(num_rows=num_rows, seed=42)
    header_row = headers
    data_rows = []

    for row in index_rows:
        date_str, time_str, open_str, high_str, low_str, close_str, volume_str = row
        datetime_str = f"{date_str} {time_str}"

        new_row = []
        for header in headers:
            if header in ("timestamp", "datetime"):
                new_row.append(datetime_str)
            elif header == "date":
                new_row.append(date_str)
            elif header == "time":
                new_row.append(time_str)
            elif header == "open":
                new_row.append(open_str)
            elif header == "high":
                new_row.append(high_str)
            elif header == "low":
                new_row.append(low_str)
            elif header == "close":
                new_row.append(close_str)
            elif header == "volume":
                new_row.append(volume_str)
            elif header in ("oi", "open_interest"):
                new_row.append("1")
            else:
                new_row.append(f"value_{header}_0")
        data_rows.append(new_row)

    return header_row, data_rows


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
        rows = make_ohlc_series(num_rows=3, seed=42)
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
        # Verify datetime format (YYYYMMDD HH:MM)
        assert len(first["datetime"]) == 14
        assert first["datetime"][8] == " "
        # Verify OHLCV are valid numeric strings
        assert float(first["open"]) > 0
        assert float(first["high"]) >= float(first["open"])
        assert float(first["low"]) <= float(first["open"])
        assert float(first["close"]) > 0
        assert int(first["volume"]) > 0

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
        rows = make_ohlc_series(num_rows=3, seed=42)
        # Add extra column (open interest)
        for i, row in enumerate(rows):
            row.append(str((i % 3) + 1))
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
        header_row, data_rows = _make_header_mode_rows(headers, num_rows=2)
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
            # Verify datetime format and OHLCV validity
            for result in results:
                assert "datetime" in result
                assert len(result["datetime"]) == 14
                assert result["datetime"][8] == " "
                assert float(result["open"]) > 0
                assert float(result["high"]) >= float(result["open"])
                assert float(result["low"]) <= float(result["open"])
                assert float(result["close"]) > 0
                assert int(result["volume"]) > 0

    def test_header_mode_with_additional_fields(self):
        """Test header mode with extra fields"""
        headers = ["timestamp", "open", "high", "low", "close", "volume", "open_interest"]
        header_row, data_rows = _make_header_mode_rows(headers, num_rows=1)
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
        header_row, data_rows = _make_header_mode_rows(headers, num_rows=1)
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
            # Verify datetime format and OHLCV validity
            result = results[0]
            assert "datetime" in result
            assert len(result["datetime"]) == 14
            assert result["datetime"][8] == " "
            assert float(result["open"]) > 0
            assert float(result["high"]) >= float(result["open"])
            assert float(result["low"]) <= float(result["open"])
            assert float(result["close"]) > 0
            assert int(result["volume"]) > 0


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
        rows = make_ohlc_series(num_rows=1, seed=42)
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
        rows = make_ohlc_series(num_rows=1, seed=42)
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
        rows = make_ohlc_series(num_rows=1, seed=42)
        csv_content = csv_rows_to_string(rows)
        
        with create_temp_csv(csv_content) as temp_path:
            with pytest.raises(ValueError, match="datetime mapping must be"):
                CSVReader(temp_path, mapping).read()

    def test_header_not_found(self):
        """Test that missing header raises ValueError"""
        headers = ["timestamp", "open", "high", "low", "close", "volume"]
        header_row, data_rows = _make_header_mode_rows(headers, num_rows=1)
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
        rows = make_ohlc_series(num_rows=3, seed=42)
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
        rows = make_ohlc_series(num_rows=1, seed=42)
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
        header_row, data_rows = _make_header_mode_rows(headers, num_rows=0)
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