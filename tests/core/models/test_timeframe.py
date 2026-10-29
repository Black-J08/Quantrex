"""Tests for the Timeframe model."""

from __future__ import annotations

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
