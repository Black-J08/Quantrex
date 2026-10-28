"""Tests for cache key construction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from quantrex.core.data.cache.cache_key import CacheKey
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit

TIMEFRAME = Timeframe(value=1, unit=TimeframeUnit.MINUTE)
FROM_DATE = datetime(2024, 1, 15, 9, 15, tzinfo=UTC)
TO_DATE = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)


def make_key(**kwargs) -> CacheKey:
    """Build a cache key with sensible defaults."""
    params = {
        "symbol": "NSE:INFY",
        "timeframe": TIMEFRAME,
        "from_date": FROM_DATE,
        "to_date": TO_DATE,
    }
    params.update(kwargs)
    return CacheKey.create(**params)


class TestCacheKey:
    """Tests for CacheKey."""

    def test_create_basic(self) -> None:
        """Test basic cache key creation."""
        key = make_key()

        assert key.symbol == "NSE:INFY"
        assert key.timeframe == TIMEFRAME
        assert key.from_date == FROM_DATE
        assert key.to_date == TO_DATE
        assert key.continuous is False
        assert key.oi is False
        assert key.version == 1

    def test_create_normalizes_to_utc(self) -> None:
        """Test that instants are normalized to UTC."""
        ist = timezone(timedelta(hours=5, minutes=30))
        key = make_key(
            from_date=datetime(2024, 1, 15, 14, 45, tzinfo=ist),
            to_date=datetime(2024, 1, 15, 15, 30, tzinfo=ist),
        )

        assert key.from_date == FROM_DATE
        assert key.to_date == TO_DATE
        assert key.from_date.utcoffset() == timedelta(0)

    def test_same_instant_in_two_zones_gives_one_key(self) -> None:
        """Test that the same moment in two zones produces the same key."""
        ist = timezone(timedelta(hours=5, minutes=30))
        utc_key = make_key()
        ist_key = make_key(
            from_date=datetime(2024, 1, 15, 14, 45, tzinfo=ist),
            to_date=datetime(2024, 1, 15, 15, 30, tzinfo=ist),
        )

        assert utc_key == ist_key

    def test_distinct_instant_ranges_give_distinct_keys(self) -> None:
        """Test that two different ranges do not share a key.

        Regression test: keys used to truncate to whole days, so a one-minute
        request and a one-hour request for the same day collided.
        """
        short = make_key(to_date=datetime(2024, 1, 15, 9, 16, tzinfo=UTC))
        long = make_key(to_date=datetime(2024, 1, 15, 10, 0, tzinfo=UTC))

        assert short != long

    def test_continuous_and_oi_change_the_key(self) -> None:
        """Test that vendor options are part of the key.

        Regression test: the options were absent, so a continuous-contract
        request could be served a non-continuous cached entry.
        """
        base = make_key()

        assert make_key(continuous=True) != base
        assert make_key(oi=True) != base
        assert make_key(continuous=True, oi=True) != make_key(continuous=True)

    def test_version_changes_the_key(self) -> None:
        """Test that the cache version is part of the key."""
        assert make_key(version=1) != make_key(version=2)

    def test_naive_datetime_raises(self) -> None:
        """Test that timezone-naive bounds are rejected."""
        with pytest.raises(ValueError, match="timezone-aware"):
            make_key(from_date=datetime(2024, 1, 15, 9, 15))  # noqa: DTZ001 - naive on purpose

    def test_empty_symbol_raises(self) -> None:
        """Test that an empty symbol is rejected."""
        with pytest.raises(ValueError, match="symbol cannot be empty"):
            make_key(symbol="")

    @pytest.mark.parametrize("symbol", [".", ".."])
    def test_path_segment_symbols_raise(self, symbol: str) -> None:
        """Test that symbols that would escape the cache root are rejected."""
        with pytest.raises(ValueError, match="path segment"):
            make_key(symbol=symbol)

    def test_inverted_range_raises(self) -> None:
        """Test that an inverted range is rejected."""
        with pytest.raises(ValueError, match="from_date must be before to_date"):
            make_key(from_date=TO_DATE, to_date=FROM_DATE)


class TestCacheKeySymbolEncoding:
    """Tests for the reversible symbol encoding."""

    @pytest.mark.parametrize(
        "symbol",
        [
            "NSE:INFY",
            "NSE_INFY",
            "INFY",
            "INFY_EQ",
            "BRENT_CRUDE",
            "A/B:C",
            "NFO:INFY24SEP3400CE",
        ],
    )
    def test_encoding_round_trips(self, symbol: str) -> None:
        """Test that encoding and decoding is lossless."""
        encoded = CacheKey.encode_symbol(symbol)

        assert CacheKey.decode_symbol(encoded) == symbol

    def test_encoding_keeps_path_separators_out(self) -> None:
        """Test that a symbol cannot inject path separators."""
        encoded = CacheKey.encode_symbol("A/B:C")

        assert "/" not in encoded
        assert ":" not in encoded

    def test_colon_and_underscore_symbols_do_not_collide(self) -> None:
        """Test that distinct symbols map to distinct encodings.

        Regression test: the old encoding replaced ':' with '_', so
        "NSE:INFY" and "NSE_INFY" produced the same file.
        """
        assert CacheKey.encode_symbol("NSE:INFY") != CacheKey.encode_symbol("NSE_INFY")


class TestCacheKeySeriesName:
    """Tests for the on-disk series name."""

    def test_series_name_includes_options_and_version(self) -> None:
        """Test that the series name separates different queries."""
        base = make_key(version=2).series_name()
        continuous = make_key(version=2, continuous=True).series_name()
        oi = make_key(version=2, oi=True).series_name()
        other_version = make_key(version=3).series_name()

        assert base != continuous
        assert base != oi
        assert continuous != oi
        assert base != other_version

    def test_series_name_contains_no_path_separators(self) -> None:
        """Test that the series name is a single path segment."""
        name = make_key(symbol="NSE:INFY").series_name()

        assert "/" not in name
        assert ":" not in name
