"""Tests for the raw vendor candle model."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from quantrex.core.models import RawCandle

IST = ZoneInfo("Asia/Kolkata")


class TestRawCandle:
    """Tests for RawCandle."""

    def test_from_api_response_with_offset(self) -> None:
        """Test that a vendor timestamp with an offset is preserved as-is."""
        raw = RawCandle.from_api_response(
            ["2024-01-15T09:15:00+05:30", 1500.0, 1510.0, 1495.0, 1505.0, 100000]
        )

        assert raw.timestamp.isoformat() == "2024-01-15T09:15:00+05:30"
        assert raw.open == Decimal("1500.0")
        assert raw.high == Decimal("1510.0")
        assert raw.low == Decimal("1495.0")
        assert raw.close == Decimal("1505.0")
        assert raw.volume == Decimal(100000)
        assert raw.oi is None

    def test_from_api_response_compact_offset(self) -> None:
        """Test that Kite's '+0530' offset format is parsed."""
        raw = RawCandle.from_api_response(
            ["2019-12-04T09:15:00+0530", 12009.9, 12019.35, 12001.25, 12001.5, 163275]
        )

        assert raw.timestamp.isoformat() == "2019-12-04T09:15:00+05:30"

    def test_from_api_response_posix_timestamp(self) -> None:
        """Test that a POSIX timestamp is read as UTC."""
        raw = RawCandle.from_api_response([1705292700, 1500.0, 1510.0, 1495.0, 1505.0, 100000])

        assert raw.timestamp.tzinfo is not None
        assert raw.timestamp.utcoffset() == timedelta(0)

    def test_from_api_response_naive_without_default_tz_raises(self) -> None:
        """Test that a naive timestamp is rejected when no default is given.

        A bare wall clock cannot be placed on the timeline unambiguously, so
        the shared model refuses to guess.
        """
        with pytest.raises(ValueError, match="no UTC offset"):
            RawCandle.from_api_response(
                ["2024-01-15T09:15:00", 1500.0, 1510.0, 1495.0, 1505.0, 100000]
            )

    def test_from_api_response_naive_uses_default_tz(self) -> None:
        """Test that a naive timestamp is localized to the supplied timezone."""
        raw = RawCandle.from_api_response(
            ["2024-01-15T09:15:00", 1500.0, 1510.0, 1495.0, 1505.0, 100000],
            default_tz=IST,
        )

        assert raw.timestamp.tzinfo is not None
        assert raw.timestamp.isoformat() == "2024-01-15T09:15:00+05:30"

    def test_from_api_response_with_oi(self) -> None:
        """Test that an optional open interest value is captured."""
        raw = RawCandle.from_api_response(
            ["2024-01-15T09:15:00+05:30", 1500.0, 1510.0, 1495.0, 1505.0, 100000, 5000]
        )

        assert raw.oi == Decimal(5000)

    def test_from_api_response_too_short_raises(self) -> None:
        """Test that a malformed candle array is rejected."""
        with pytest.raises(ValueError, match="expected at least 6 elements"):
            RawCandle.from_api_response(["2024-01-15T09:15:00+05:30", 1500.0, 1510.0])

    def test_from_api_response_preserves_decimal_precision(self) -> None:
        """Test that the price is held as a Decimal, not a float.

        The vendor sends JSON numbers, so the value arrives as a float and
        carries float precision. Converting through ``str`` keeps the exact
        decimal the float represents, with no binary-float artefacts.
        """
        raw = RawCandle.from_api_response(
            ["2024-01-15T09:15:00+05:30", 1500.1234567890123456, 1510.0, 1495.0, 1505.0, 100000]
        )

        assert isinstance(raw.open, Decimal)
        assert raw.open == Decimal(str(1500.1234567890123456))
        # A binary float would render artefacts such as 1495.0000000000002.
        assert str(raw.low) == "1495.0"

    def test_from_api_response_utc_offset_preserved(self) -> None:
        """Test that a UTC vendor timestamp is not shifted."""
        raw = RawCandle.from_api_response(
            ["2024-01-15T09:15:00+00:00", 1500.0, 1510.0, 1495.0, 1505.0, 100000]
        )

        assert raw.timestamp == datetime(2024, 1, 15, 9, 15, tzinfo=UTC)
        assert raw.timestamp.utcoffset() == timedelta(0)
        assert raw.timestamp.tzinfo != timezone(timedelta(hours=5, minutes=30))
