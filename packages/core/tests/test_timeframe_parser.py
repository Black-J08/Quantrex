"""Unit tests for timeframe parser module."""

import pytest
from quantrex_core.timeframe.parser import (
    parse_interval,
    interval_to_minutes,
    validate_interval,
    get_supported_units,
    ParsedInterval,
)


class TestParseInterval:
    """Tests for parse_interval function."""

    def test_parse_minute_intervals(self):
        """Test parsing minute-based intervals."""
        assert parse_interval("1M") == ParsedInterval(value=1, unit="M", total_minutes=1)
        assert parse_interval("5M") == ParsedInterval(value=5, unit="M", total_minutes=5)
        assert parse_interval("15M") == ParsedInterval(value=15, unit="M", total_minutes=15)
        assert parse_interval("30M") == ParsedInterval(value=30, unit="M", total_minutes=30)

    def test_parse_hour_intervals(self):
        """Test parsing hour-based intervals."""
        assert parse_interval("1H") == ParsedInterval(value=1, unit="H", total_minutes=60)
        assert parse_interval("4H") == ParsedInterval(value=4, unit="H", total_minutes=240)

    def test_parse_day_intervals(self):
        """Test parsing day-based intervals."""
        assert parse_interval("1D") == ParsedInterval(value=1, unit="D", total_minutes=1440)

    def test_parse_week_intervals(self):
        """Test parsing week-based intervals."""
        assert parse_interval("1W") == ParsedInterval(value=1, unit="W", total_minutes=10080)

    def test_parse_case_insensitive(self):
        """Test that parsing is case-insensitive."""
        assert parse_interval("1h") == ParsedInterval(value=1, unit="H", total_minutes=60)
        assert parse_interval("1d") == ParsedInterval(value=1, unit="D", total_minutes=1440)

    def test_parse_whitespace(self):
        """Test that whitespace is handled."""
        assert parse_interval(" 1H ") == ParsedInterval(value=1, unit="H", total_minutes=60)

    def test_parse_invalid_format(self):
        """Test that invalid formats raise ValueError."""
        with pytest.raises(ValueError, match="Invalid interval format"):
            parse_interval("invalid")
        with pytest.raises(ValueError, match="Invalid interval format"):
            parse_interval("H1")
        with pytest.raises(ValueError, match="Invalid interval format"):
            parse_interval("1X")

    def test_parse_zero_value(self):
        """Test that zero value raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            parse_interval("0H")

    def test_parse_negative_value(self):
        """Test that negative value raises ValueError (regex rejects it)."""
        with pytest.raises(ValueError, match="Invalid interval format"):
            parse_interval("-1H")

    def test_parse_empty_string(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="non-empty string"):
            parse_interval("")

    def test_parse_none(self):
        """Test that None raises ValueError."""
        with pytest.raises(ValueError, match="non-empty string"):
            parse_interval(None)  # type: ignore


class TestIntervalToMinutes:
    """Tests for interval_to_minutes function."""

    def test_minute_intervals(self):
        assert interval_to_minutes("1M") == 1
        assert interval_to_minutes("5M") == 5
        assert interval_to_minutes("15M") == 15
        assert interval_to_minutes("30M") == 30

    def test_hour_intervals(self):
        assert interval_to_minutes("1H") == 60
        assert interval_to_minutes("4H") == 240

    def test_day_intervals(self):
        assert interval_to_minutes("1D") == 1440

    def test_week_intervals(self):
        assert interval_to_minutes("1W") == 10080


class TestValidateInterval:
    """Tests for validate_interval function."""

    def test_valid_intervals(self):
        assert validate_interval("1M") is True
        assert validate_interval("5M") is True
        assert validate_interval("1H") is True
        assert validate_interval("1D") is True
        assert validate_interval("1W") is True

    def test_invalid_intervals(self):
        assert validate_interval("invalid") is False
        assert validate_interval("1X") is False
        assert validate_interval("") is False
        assert validate_interval(None) is False  # type: ignore


class TestGetSupportedUnits:
    """Tests for get_supported_units function."""

    def test_returns_expected_units(self):
        units = get_supported_units()
        assert units == ("D", "H", "M", "W")