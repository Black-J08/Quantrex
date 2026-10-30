"""Tests for the Timeframe model."""

from __future__ import annotations

import pytest

from quantrex.core.models.timeframe import Timeframe, TimeframeUnit


class TestTimeframeIsDerivableFrom:
    """Tests for Timeframe.is_derivable_from()."""

    def test_same_timeframe_is_derivable(self) -> None:
        """A timeframe is always derivable from itself."""
        tf = Timeframe(value=5, unit=TimeframeUnit.MINUTE)
        assert tf.is_derivable_from(tf) is True

    def test_whole_number_multiple_is_derivable(self) -> None:
        """A whole-number multiple of the source is derivable."""
        assert Timeframe(value=45, unit=TimeframeUnit.MINUTE).is_derivable_from(
            Timeframe(value=1, unit=TimeframeUnit.MINUTE)
        ) is True
        assert Timeframe(value=60, unit=TimeframeUnit.MINUTE).is_derivable_from(
            Timeframe(value=1, unit=TimeframeUnit.MINUTE)
        ) is True
        assert Timeframe(value=1, unit=TimeframeUnit.HOUR).is_derivable_from(
            Timeframe(value=1, unit=TimeframeUnit.MINUTE)
        ) is True

    def test_non_whole_number_multiple_is_not_derivable(self) -> None:
        """A non-whole-number multiple of the source is not derivable."""
        assert Timeframe(value=30, unit=TimeframeUnit.SECOND).is_derivable_from(
            Timeframe(value=1, unit=TimeframeUnit.MINUTE)
        ) is False
        assert Timeframe(value=1, unit=TimeframeUnit.HOUR).is_derivable_from(
            Timeframe(value=2, unit=TimeframeUnit.HOUR)
        ) is False

    def test_cross_unit_derivation_from_minute_to_day(self) -> None:
        """1 day is derivable from 1 minute (1440 × 1m)."""
        assert Timeframe(value=1, unit=TimeframeUnit.DAY).is_derivable_from(
            Timeframe(value=1, unit=TimeframeUnit.MINUTE)
        ) is True

    def test_cross_unit_derivation_from_day_to_week(self) -> None:
        """1 week is derivable from 1 day (7 × 1d)."""
        assert Timeframe(value=1, unit=TimeframeUnit.WEEK).is_derivable_from(
            Timeframe(value=1, unit=TimeframeUnit.DAY)
        ) is True

    def test_cross_unit_derivation_from_day_to_month(self) -> None:
        """1 month is derivable from 1 day (approx 30 × 1d)."""
        assert Timeframe(value=1, unit=TimeframeUnit.MONTH).is_derivable_from(
            Timeframe(value=1, unit=TimeframeUnit.DAY)
        ) is True

    def test_non_multiple_cross_unit_is_not_derivable(self) -> None:
        """A timeframe that is not a whole-number multiple across units is not derivable."""
        assert Timeframe(value=25, unit=TimeframeUnit.HOUR).is_derivable_from(
            Timeframe(value=1, unit=TimeframeUnit.DAY)
        ) is False


class TestTimeframeToPandasFreq:
    """Tests for Timeframe.to_pandas_freq()."""

    def test_minute(self) -> None:
        assert Timeframe(value=1, unit=TimeframeUnit.MINUTE).to_pandas_freq() == "1min"
        assert Timeframe(value=45, unit=TimeframeUnit.MINUTE).to_pandas_freq() == "45min"

    def test_hour(self) -> None:
        assert Timeframe(value=1, unit=TimeframeUnit.HOUR).to_pandas_freq() == "1h"
        assert Timeframe(value=4, unit=TimeframeUnit.HOUR).to_pandas_freq() == "4h"

    def test_day(self) -> None:
        assert Timeframe(value=1, unit=TimeframeUnit.DAY).to_pandas_freq() == "1D"
        assert Timeframe(value=2, unit=TimeframeUnit.DAY).to_pandas_freq() == "2D"

    def test_week(self) -> None:
        assert Timeframe(value=1, unit=TimeframeUnit.WEEK).to_pandas_freq() == "1W"

    def test_month(self) -> None:
        assert Timeframe(value=1, unit=TimeframeUnit.MONTH).to_pandas_freq() == "1ME"


class TestTimeframeFromString:
    """Tests for Timeframe.from_string() edge cases."""

    def test_valid_minute(self) -> None:
        """Valid minute timeframe string parses correctly."""
        tf = Timeframe.from_string("1m")
        assert tf.value == 1
        assert tf.unit == TimeframeUnit.MINUTE

    def test_valid_multi_digit_minute(self) -> None:
        """Multi-digit minute timeframe string parses correctly."""
        tf = Timeframe.from_string("45m")
        assert tf.value == 45
        assert tf.unit == TimeframeUnit.MINUTE

    def test_valid_hour(self) -> None:
        """Valid hour timeframe string parses correctly."""
        tf = Timeframe.from_string("1h")
        assert tf.value == 1
        assert tf.unit == TimeframeUnit.HOUR

    def test_valid_day(self) -> None:
        """Valid day timeframe string parses correctly."""
        tf = Timeframe.from_string("1d")
        assert tf.value == 1
        assert tf.unit == TimeframeUnit.DAY

    def test_valid_week(self) -> None:
        """Valid week timeframe string parses correctly."""
        tf = Timeframe.from_string("1w")
        assert tf.value == 1
        assert tf.unit == TimeframeUnit.WEEK

    def test_valid_month(self) -> None:
        """Valid month timeframe string parses correctly."""
        tf = Timeframe.from_string("1M")
        assert tf.value == 1
        assert tf.unit == TimeframeUnit.MONTH

    def test_valid_second(self) -> None:
        """Valid second timeframe string parses correctly."""
        tf = Timeframe.from_string("30s")
        assert tf.value == 30
        assert tf.unit == TimeframeUnit.SECOND

    def test_empty_string_raises(self) -> None:
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="timeframe string cannot be empty"):
            Timeframe.from_string("")

    def test_no_unit_raises(self) -> None:
        """String with no unit raises ValueError."""
        with pytest.raises(ValueError, match="invalid timeframe format"):
            Timeframe.from_string("45")

    def test_invalid_unit_raises(self) -> None:
        """Invalid unit raises ValueError."""
        with pytest.raises(ValueError, match="invalid timeframe unit"):
            Timeframe.from_string("1x")

    def test_invalid_value_raises(self) -> None:
        """Non-numeric value raises ValueError."""
        with pytest.raises(ValueError, match="invalid timeframe format"):
            Timeframe.from_string("abc")

    def test_zero_value_raises(self) -> None:
        """Zero value raises ValueError via __post_init__."""
        with pytest.raises(ValueError, match="value must be positive"):
            Timeframe.from_string("0m")

    def test_negative_value_raises(self) -> None:
        """Negative value raises ValueError via invalid format."""
        with pytest.raises(ValueError, match="invalid timeframe format"):
            Timeframe.from_string("-1m")

    def test_whitespace_only_raises(self) -> None:
        """Whitespace-only string raises ValueError."""
        with pytest.raises(ValueError, match="invalid timeframe format"):
            Timeframe.from_string("   ")
