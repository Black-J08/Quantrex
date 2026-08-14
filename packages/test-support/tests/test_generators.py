"""Pytest test cases for the test-support package CSV generators."""

import pytest

from datetime import datetime

from quantrex_test_support.csv import make_ohlc_series, csv_rows_to_string


class TestMakeOHLCSeries:
    """Tests for make_ohlc_series function."""

    def test_default_parameters(self):
        """Test with default parameters."""
        rows = make_ohlc_series()
        assert len(rows) == 100

    def test_custom_num_rows(self):
        """Test with custom number of rows."""
        rows = make_ohlc_series(num_rows=10)
        assert len(rows) == 10

    def test_custom_start_datetime(self):
        """Test with custom start datetime."""
        start = datetime(2023, 6, 15, 10, 0)
        rows = make_ohlc_series(start_datetime=start, num_rows=5)
        assert len(rows) == 5
        # Check first row's datetime
        first_date, first_time = rows[0][0], rows[0][1]
        assert first_date == "20230615"
        assert first_time == "10:00"

    def test_custom_interval(self):
        """Test with custom interval in minutes."""
        rows = make_ohlc_series(num_rows=3, interval_minutes=5)
        # With interval_minutes=5 and start at 09:30, next should be 09:35, then 09:40
        assert rows[0][1] == "09:30"
        assert rows[1][1] == "09:35"
        assert rows[2][1] == "09:40"

    def test_custom_start_price(self):
        """Test with custom start price."""
        rows = make_ohlc_series(start_price=200.0, num_rows=3)
        # First row open should be 200.00
        assert rows[0][2] == "200.00"

    def test_volatility_parameter(self):
        """Test volatility parameter affects price movement."""
        # With seed for reproducibility
        rows1 = make_ohlc_series(volatility=0.5, seed=42)
        rows2 = make_ohlc_series(volatility=0.5, seed=42)
        # Same seed should produce same results
        assert rows1 == rows2

    def test_drift_parameter(self):
        """Test drift parameter affects price trend."""
        # Positive drift should increase price over time
        rows = make_ohlc_series(drift=0.02, num_rows=10, seed=42)
        first_open = float(rows[0][2])
        last_close = float(rows[-1][5])
        assert last_close >= first_open  # With positive drift, price should generally increase

    def test_volume_range(self):
        """Test volume range parameter."""
        rows = make_ohlc_series(volume_range=(1000, 5000), num_rows=5, seed=42)
        for row in rows:
            volume = int(row[6])
            assert 1000 <= volume <= 5000

    def test_ohlc_relationships(self):
        """Test OHLC relationships: high >= max(open, close), low <= min(open, close)."""
        rows = make_ohlc_series(num_rows=50, seed=42)
        for row in rows:
            open_price = float(row[2])
            high_price = float(row[3])
            low_price = float(row[4])
            close_price = float(row[5])

            # High should be >= max(open, close)
            assert high_price >= max(open_price, close_price), (
                f"High {high_price} < max(open {open_price}, close {close_price})"
            )

            # Low should be <= min(open, close)
            assert low_price <= min(open_price, close_price), (
                f"Low {low_price} > min(open {open_price}, close {close_price})"
            )

    def test_sequential_datetimes(self):
        """Test that datetimes are strictly sequential."""
        rows = make_ohlc_series(num_rows=10, interval_minutes=1, seed=42)
        dates = []
        for row in rows:
            date_str = row[0]
            time_str = row[1]
            # Combine date and time into a comparable format
            full_dt = datetime.strptime(f"{date_str} {time_str}", "%Y%m%d %H:%M")
            dates.append(full_dt)

        # Check sequentiality
        for i in range(1, len(dates)):
            assert dates[i] > dates[i - 1], f"Datetimes not sequential at index {i}"

    def test_price_positive(self):
        """Test that all prices remain positive."""
        rows = make_ohlc_series(num_rows=100, seed=42)
        for row in rows:
            open_price = float(row[2])
            high_price = float(row[3])
            low_price = float(row[4])
            close_price = float(row[5])
            assert open_price > 0, f"Non-positive open price: {open_price}"
            assert high_price > 0, f"Non-positive high price: {high_price}"
            assert low_price > 0, f"Non-positive low price: {low_price}"
            assert close_price > 0, f"Non-positive close price: {close_price}"

    def test_column_format(self):
        """Test that columns are properly formatted strings."""
        rows = make_ohlc_series(num_rows=3, seed=42)
        for row in rows:
            assert len(row) == 7, f"Expected 7 columns, got {len(row)}"
            # Check date format YYYYMMDD
            assert len(row[0]) == 8, f"Date format incorrect: {row[0]}"
            # Check time format HH:MM
            assert len(row[1]) == 5, f"Time format incorrect: {row[1]}"
            # Check prices have 2 decimal places
            assert "." in row[2], f"Open price missing decimal: {row[2]}"
            assert "." in row[3], f"High price missing decimal: {row[3]}"
            assert "." in row[4], f"Low price missing decimal: {row[4]}"
            assert "." in row[5], f"Close price missing decimal: {row[5]}"
            # Check volume is integer string
            assert row[6].isdigit(), f"Volume not integer: {row[6]}"


class TestCSVRowsToString:
    """Tests for csv_rows_to_string function."""

    def test_basic_conversion(self):
        """Test basic conversion of rows to CSV string."""
        rows = [
            ["20230101", "09:30", "100.00", "105.00", "95.00", "102.00", "1000"],
            ["20230101", "09:31", "102.00", "106.00", "97.00", "104.00", "1500"],
        ]
        result = csv_rows_to_string(rows)
        expected = "20230101,09:30,100.00,105.00,95.00,102.00,1000\n20230101,09:31,102.00,106.00,97.00,104.00,1500\n"
        assert result == expected

    def test_single_row(self):
        """Test with single row."""
        rows = [["20230101", "09:30", "100.00", "105.00", "95.00", "102.00", "1000"]]
        result = csv_rows_to_string(rows)
        expected = "20230101,09:30,100.00,105.00,95.00,102.00,1000\n"
        assert result == expected

    def test_empty_rows(self):
        """Test with empty list."""
        rows = []
        result = csv_rows_to_string(rows)
        expected = "\n"
        assert result == expected