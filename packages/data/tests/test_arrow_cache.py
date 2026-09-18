"""Tests for ArrowCache."""

from datetime import datetime, timedelta
from pathlib import Path
import tempfile

import pandas as pd
import pytest

from quantrex_data.operations import ArrowCache, get_arrow_cache_dir


class TestArrowCache:
    """Tests for ArrowCache class."""

    def test_cache_dir_default(self):
        """Test default cache directory."""
        cache = ArrowCache()
        assert cache.cache_root == Path("~/.quantrex/cache").expanduser()

    def test_cache_dir_custom(self):
        """Test custom cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            assert cache.cache_root == Path(tmpdir)

    def test_partition_path_generation(self):
        """Test hierarchical partition path generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            start = datetime(2026, 1, 15)
            end = datetime(2026, 1, 31)
            path = cache._partition_path("dhan", "RELIANCE", "1M", start, end)
            # Path uses start date for filename
            expected = Path(tmpdir) / "dhan" / "historical" / "RELIANCE" / "1M" / "2026" / "01" / "RELIANCE_1M_20260115_20260131.feather"
            assert path == expected

    def test_current_partition_path(self):
        """Test current partition path generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            path = cache._current_partition_path("zerodha", "INFY", "5M")
            now = datetime.now()
            expected = Path(tmpdir) / "zerodha" / "historical" / "INFY" / "5M" / now.strftime("%Y") / now.strftime("%m") / f"INFY_5M_{now.replace(day=1).strftime('%Y%m%d')}_{now.strftime('%Y%m%d')}.feather"
            assert path == expected

    def test_save_and_load_partition(self):
        """Test saving and loading a closed partition."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            data = [
                {"datetime": "2026-01-15 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
                {"datetime": "2026-01-15 09:16:00", "open": 100.5, "high": 101.5, "low": 100.0, "close": 101.0, "volume": 1500},
            ]
            start = datetime(2026, 1, 15)
            end = datetime(2026, 1, 15)

            cache.save_partition_sync("dhan", "RELIANCE", "1M", start, end, data)
            loaded = cache.load_partition("dhan", "RELIANCE", "1M", start, end)

            assert loaded is not None
            assert len(loaded) == 2
            assert loaded[0]["open"] == 100.0
            assert loaded[0]["symbol"] == "RELIANCE"
            assert loaded[0]["timeframe"] == "1M"
            assert loaded[0]["provider"] == "dhan"

    def test_load_missing_partition(self):
        """Test loading non-existent partition returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            start = datetime(2026, 1, 15)
            end = datetime(2026, 1, 15)
            loaded = cache.load_partition("dhan", "RELIANCE", "1M", start, end)
            assert loaded is None

    def test_current_partition_append(self):
        """Test appending to current partition."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            now = datetime.now()
            current_month_start = now.replace(day=1, hour=9, minute=15, second=0, microsecond=0)
            data1 = [
                {"datetime": current_month_start.strftime("%Y-%m-%d %H:%M:%S"), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            ]
            data2 = [
                {"datetime": (current_month_start + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"), "open": 100.5, "high": 101.5, "low": 100.0, "close": 101.0, "volume": 1500},
            ]

            # Use sync version for testing
            cache.append_to_current_partition_sync("dhan", "RELIANCE", "1M", data1)
            cache.append_to_current_partition_sync("dhan", "RELIANCE", "1M", data2)

            loaded = cache.load_current_partition("dhan", "RELIANCE", "1M")
            assert loaded is not None
            assert len(loaded) == 2

    def test_current_partition_deduplication(self):
        """Test deduplication when appending to current partition."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            now = datetime.now()
            current_month_start = now.replace(day=1, hour=9, minute=15, second=0, microsecond=0)
            ts = current_month_start.strftime("%Y-%m-%d %H:%M:%S")
            data1 = [
                {"datetime": ts, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            ]
            # Same timestamp, different values - should keep last
            data2 = [
                {"datetime": ts, "open": 200.0, "high": 201.0, "low": 199.0, "close": 200.5, "volume": 2000},
            ]

            # Use sync version for testing
            cache.append_to_current_partition_sync("dhan", "RELIANCE", "1M", data1)
            cache.append_to_current_partition_sync("dhan", "RELIANCE", "1M", data2)

            loaded = cache.load_current_partition("dhan", "RELIANCE", "1M")
            assert loaded is not None
            assert len(loaded) == 1
            assert loaded[0]["open"] == 200.0  # Last write wins

    def test_get_last_timestamp(self):
        """Test getting last timestamp from current partition."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            now = datetime.now()
            current_month_start = now.replace(day=1, hour=9, minute=15, second=0, microsecond=0)
            data = [
                {"datetime": current_month_start.strftime("%Y-%m-%d %H:%M:%S"), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
                {"datetime": (current_month_start + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"), "open": 100.5, "high": 101.5, "low": 100.0, "close": 101.0, "volume": 1500},
            ]
            cache.append_to_current_partition_sync("dhan", "RELIANCE", "1M", data)

            last_ts = cache.get_last_timestamp("dhan", "RELIANCE", "1M")
            assert last_ts is not None
            assert last_ts == current_month_start + timedelta(minutes=1)

    def test_get_last_timestamp_empty(self):
        """Test getting last timestamp from non-existent partition."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            last_ts = cache.get_last_timestamp("dhan", "RELIANCE", "1M")
            assert last_ts is None

    def test_provider_isolation(self):
        """Test that dhan and zerodha caches are isolated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            data = [
                {"datetime": "2026-01-15 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            ]
            start = datetime(2026, 1, 15)
            end = datetime(2026, 1, 15)

            cache.save_partition_sync("dhan", "RELIANCE", "1M", start, end, data)
            cache.save_partition_sync("zerodha", "RELIANCE", "1M", start, end, data)

            dhan_loaded = cache.load_partition("dhan", "RELIANCE", "1M", start, end)
            zerodha_loaded = cache.load_partition("zerodha", "RELIANCE", "1M", start, end)

            assert dhan_loaded is not None
            assert zerodha_loaded is not None
            assert dhan_loaded[0]["provider"] == "dhan"
            assert zerodha_loaded[0]["provider"] == "zerodha"

    def test_clear_cache(self):
        """Test clearing cache files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            data = [
                {"datetime": "2026-01-15 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            ]
            start = datetime(2026, 1, 15)
            end = datetime(2026, 1, 15)

            cache.save_partition_sync("dhan", "RELIANCE", "1M", start, end, data)
            cache.save_partition_sync("zerodha", "INFY", "1M", start, end, data)

            # Clear only dhan
            deleted = cache.clear(provider="dhan")
            assert deleted == 1

            dhan_loaded = cache.load_partition("dhan", "RELIANCE", "1M", start, end)
            zerodha_loaded = cache.load_partition("zerodha", "INFY", "1M", start, end)

            assert dhan_loaded is None
            assert zerodha_loaded is not None

    def test_clear_symbol(self):
        """Test clearing cache for specific symbol."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            data = [
                {"datetime": "2026-01-15 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            ]
            start = datetime(2026, 1, 15)
            end = datetime(2026, 1, 15)

            cache.save_partition_sync("dhan", "RELIANCE", "1M", start, end, data)
            cache.save_partition_sync("dhan", "INFY", "1M", start, end, data)

            deleted = cache.clear(symbol="RELIANCE")
            assert deleted == 1

            reliance_loaded = cache.load_partition("dhan", "RELIANCE", "1M", start, end)
            infy_loaded = cache.load_partition("dhan", "INFY", "1M", start, end)

            assert reliance_loaded is None
            assert infy_loaded is not None

    def test_oi_field_handling(self):
        """Test optional OI field handling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            now = datetime.now()
            current_month_start = now.replace(day=1, hour=9, minute=15, second=0, microsecond=0)
            ts = current_month_start.strftime("%Y-%m-%d %H:%M:%S")
            data_with_oi = [
                {"datetime": ts, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000, "oi": 500},
            ]
            data_without_oi = [
                {"datetime": ts, "open": 100.5, "high": 101.5, "low": 100.0, "close": 101.0, "volume": 1500},
            ]

            cache.save_partition_sync("dhan", "RELIANCE", "1M", current_month_start, now, data_with_oi)
            loaded = cache.load_partition("dhan", "RELIANCE", "1M", current_month_start, now)

            assert loaded is not None
            assert len(loaded) == 1
            assert loaded[0]["oi"] == 500

            # Test without OI
            cache.save_partition_sync("dhan", "INFY", "1M", current_month_start, now, data_without_oi)
            loaded2 = cache.load_partition("dhan", "INFY", "1M", current_month_start, now)
            assert loaded2 is not None
            # OI field may be NaN (float) when not provided
            oi_val = loaded2[0].get("oi")
            assert oi_val is None or (isinstance(oi_val, float) and pd.isna(oi_val))

    def test_empty_data_handling(self):
        """Test handling of empty data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            now = datetime.now()
            current_month_start = now.replace(day=1, hour=9, minute=15, second=0, microsecond=0)

            cache.save_partition_sync("dhan", "RELIANCE", "1M", current_month_start, now, [])
            loaded = cache.load_partition("dhan", "RELIANCE", "1M", current_month_start, now)
            assert loaded is not None
            assert len(loaded) == 0

    def test_datetime_format_flexibility(self):
        """Test various datetime input formats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            data = [
                {"datetime": "2026-01-15 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
                {"datetime": "20260115 09:16", "open": 100.5, "high": 101.5, "low": 100.0, "close": 101.0, "volume": 1500},
                {"datetime": "2026-01-15T09:17:00", "open": 101.0, "high": 102.0, "low": 100.5, "close": 101.5, "volume": 2000},
            ]
            start = datetime(2026, 1, 15)
            end = datetime(2026, 1, 15)

            cache.save_partition_sync("dhan", "RELIANCE", "1M", start, end, data)
            loaded = cache.load_partition("dhan", "RELIANCE", "1M", start, end)

            assert loaded is not None
            assert len(loaded) == 3
            # All should be normalized to standard format
            for row in loaded:
                assert " " in row["datetime"]
                assert ":" in row["datetime"]


class TestGetArrowCacheDir:
    """Tests for get_arrow_cache_dir function."""

    def test_default_path(self):
        """Test default path expansion."""
        path = get_arrow_cache_dir()
        assert path == Path("~/.quantrex/cache").expanduser()

    def test_env_override(self, monkeypatch):
        """Test environment variable override."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("QUANTREX_CACHE_DIR", tmpdir)
            path = get_arrow_cache_dir()
            assert path == Path(tmpdir)