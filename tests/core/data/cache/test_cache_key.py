"""Tests for cache key utilities."""

from __future__ import annotations

from datetime import UTC, date, datetime

from quantrex.core.data.cache.cache_key import CacheKey, generate_cache_key
from quantrex.core.models import Timeframe, TimeframeUnit


class TestCacheKey:
    """Tests for CacheKey."""

    def test_create_basic(self) -> None:
        """Test basic cache key creation."""
        key = CacheKey.create(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=date(2024, 1, 15),
            to_date=date(2024, 1, 15),
        )
        
        assert key.symbol == "NSE:INFY"
        assert key.timeframe == Timeframe(value=1, unit=TimeframeUnit.MINUTE)
        assert key.from_date == date(2024, 1, 15)
        assert key.to_date == date(2024, 1, 15)
        assert key.version == 1

    def test_create_with_datetime(self) -> None:
        """Test cache key creation with datetime objects."""
        key = CacheKey.create(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=datetime(2024, 1, 15, 9, 15, tzinfo=UTC),
            to_date=datetime(2024, 1, 15, 15, 30, tzinfo=UTC),
            version=2,
        )
        
        assert key.from_date == date(2024, 1, 15)
        assert key.to_date == date(2024, 1, 15)
        assert key.version == 2

    def test_to_filename(self) -> None:
        """Test filename generation."""
        key = CacheKey.create(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=date(2024, 1, 15),
            to_date=date(2024, 1, 15),
            version=1,
        )
        
        filename = key.to_filename()
        assert filename == "NSE_INFY_1m_2024-01-15_2024-01-15_v1.feather"

    def test_to_filename_different_timeframes(self) -> None:
        """Test filename generation for different timeframes."""
        key_5m = CacheKey.create(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=5, unit=TimeframeUnit.MINUTE),
            from_date=date(2024, 1, 15),
            to_date=date(2024, 1, 15),
        )
        assert key_5m.to_filename() == "NSE_INFY_5m_2024-01-15_2024-01-15_v1.feather"
        
        key_1h = CacheKey.create(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.HOUR),
            from_date=date(2024, 1, 15),
            to_date=date(2024, 1, 15),
        )
        assert key_1h.to_filename() == "NSE_INFY_1h_2024-01-15_2024-01-15_v1.feather"
        
        key_1d = CacheKey.create(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.DAY),
            from_date=date(2024, 1, 15),
            to_date=date(2024, 1, 15),
        )
        assert key_1d.to_filename() == "NSE_INFY_1d_2024-01-15_2024-01-15_v1.feather"

    def test_to_path(self) -> None:
        """Test path generation."""
        from pathlib import Path
        
        key = CacheKey.create(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=date(2024, 1, 15),
            to_date=date(2024, 1, 15),
        )
        
        base_dir = Path("/tmp/cache")
        path = key.to_path(base_dir)
        expected = Path("/tmp/cache/NSE_INFY/1m/NSE_INFY_1m_2024-01-15_2024-01-15_v1.feather")
        assert path == expected

    def test_from_filename_valid(self) -> None:
        """Test parsing cache key from valid filename."""
        filename = "NSE_INFY_1m_2024-01-15_2024-01-15_v1.feather"
        key = CacheKey.from_filename(filename)
        
        assert key is not None
        assert key.symbol == "NSE:INFY"
        assert key.timeframe == Timeframe(value=1, unit=TimeframeUnit.MINUTE)
        assert key.from_date == date(2024, 1, 15)
        assert key.to_date == date(2024, 1, 15)
        assert key.version == 1

    def test_from_filename_version_2(self) -> None:
        """Test parsing cache key with version 2."""
        filename = "NSE_INFY_1m_2024-01-15_2024-01-15_v2.feather"
        key = CacheKey.from_filename(filename)
        
        assert key is not None
        assert key.version == 2

    def test_from_filename_invalid_extension(self) -> None:
        """Test parsing fails for invalid extension."""
        key = CacheKey.from_filename("NSE_INFY_1m_2024-01-15_2024-01-15_v1.parquet")
        assert key is None

    def test_from_filename_invalid_format(self) -> None:
        """Test parsing fails for invalid format."""
        key = CacheKey.from_filename("invalid_filename.feather")
        assert key is None

    def test_from_filename_missing_version(self) -> None:
        """Test parsing fails when version is missing."""
        key = CacheKey.from_filename("NSE_INFY_1m_2024-01-15_2024-01-15.feather")
        assert key is None

    def test_generate_cache_key_convenience(self) -> None:
        """Test generate_cache_key convenience function."""
        key = generate_cache_key(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=date(2024, 1, 15),
            to_date=date(2024, 1, 15),
        )
        
        assert key.symbol == "NSE:INFY"
        assert key.timeframe == Timeframe(value=1, unit=TimeframeUnit.MINUTE)