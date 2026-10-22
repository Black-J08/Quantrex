"""Tests for disk cache."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import pyarrow as pa

from quantrex.core.data.cache.cache_key import CacheKey
from quantrex.core.data.cache.disk_cache import DiskCache
from quantrex.core.models import Timeframe, TimeframeUnit


class TestDiskCache:
    """Tests for DiskCache base class."""

    def test_init_creates_directory(self) -> None:
        """Test that initialization creates base directory."""
        with TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "test_cache"
            _TestCache(cache_dir)
            assert cache_dir.exists()

    def test_exists_false_for_missing_key(self) -> None:
        """Test exists returns False for missing key."""
        with TemporaryDirectory() as tmpdir:
            cache = _TestCache(Path(tmpdir))
            key = CacheKey.create(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            assert cache.exists(key) is False

    def test_get_returns_none_for_missing_key(self) -> None:
        """Test get returns None for missing key."""
        with TemporaryDirectory() as tmpdir:
            cache = _TestCache(Path(tmpdir))
            key = CacheKey.create(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            assert cache.get(key) is None

    def test_set_and_get(self) -> None:
        """Test setting and getting data."""
        with TemporaryDirectory() as tmpdir:
            cache = _TestCache(Path(tmpdir))
            key = CacheKey.create(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            
            test_data = "test_value"
            cache.set(key, test_data)
            
            assert cache.exists(key)
            retrieved = cache.get(key)
            assert retrieved == test_data

    def test_delete(self) -> None:
        """Test deleting cache entry."""
        with TemporaryDirectory() as tmpdir:
            cache = _TestCache(Path(tmpdir))
            key = CacheKey.create(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            
            cache.set(key, "test_value")
            assert cache.exists(key)
            
            deleted = cache.delete(key)
            assert deleted is True
            assert not cache.exists(key)
            
            # Deleting again returns False
            deleted = cache.delete(key)
            assert deleted is False

    def test_invalidate_symbol_timeframe(self) -> None:
        """Test invalidating all entries for symbol/timeframe."""
        with TemporaryDirectory() as tmpdir:
            cache = _TestCache(Path(tmpdir))
            
            # Create multiple cache entries for same symbol/timeframe
            key1 = CacheKey.create(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            key2 = CacheKey.create(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 16),
                to_date=date(2024, 1, 16),
            )
            key3 = CacheKey.create(
                symbol="NSE:RELIANCE",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            
            cache.set(key1, "value1")
            cache.set(key2, "value2")
            cache.set(key3, "value3")
            
            # Invalidate NSE:INFY 1m
            count = cache.invalidate("NSE:INFY", "1m")
            assert count == 2
            assert not cache.exists(key1)
            assert not cache.exists(key2)
            assert cache.exists(key3)  # Different symbol should remain

    def test_clear(self) -> None:
        """Test clearing all cache entries."""
        with TemporaryDirectory() as tmpdir:
            cache = _TestCache(Path(tmpdir))
            
            key1 = CacheKey.create(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            key2 = CacheKey.create(
                symbol="NSE:RELIANCE",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            
            cache.set(key1, "value1")
            cache.set(key2, "value2")
            
            count = cache.clear()
            assert count == 2
            assert not cache.exists(key1)
            assert not cache.exists(key2)

    def test_list_keys(self) -> None:
        """Test listing all cache keys."""
        with TemporaryDirectory() as tmpdir:
            cache = _TestCache(Path(tmpdir))
            
            key1 = CacheKey.create(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            key2 = CacheKey.create(
                symbol="NSE:RELIANCE",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            
            cache.set(key1, "value1")
            cache.set(key2, "value2")
            
            keys = cache.list_keys()
            assert len(keys) == 2
            symbols = {k.symbol for k in keys}
            assert symbols == {"NSE:INFY", "NSE:RELIANCE"}

    def test_get_stats(self) -> None:
        """Test getting cache statistics."""
        with TemporaryDirectory() as tmpdir:
            cache = _TestCache(Path(tmpdir))
            
            # Empty cache stats
            stats = cache.get_stats()
            assert stats["total_files"] == 0
            assert stats["total_size_bytes"] == 0
            
            # Add some data
            key1 = CacheKey.create(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            cache.set(key1, "test_value")
            
            stats = cache.get_stats()
            assert stats["total_files"] == 1
            assert stats["total_size_bytes"] > 0
            assert stats["symbols"] == 1
            assert stats["timeframes"] == 1


class _TestCache(DiskCache[str]):
    """Concrete implementation for testing."""
    
    def _serialize(self, data: str) -> pa.Table:
        return pa.Table.from_pydict({"data": [data]})
    
    def _deserialize(self, table: pa.Table) -> str:
        return table.column("data")[0].as_py()