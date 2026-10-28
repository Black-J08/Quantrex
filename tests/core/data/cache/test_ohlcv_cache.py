"""Tests for the OHLCV disk cache."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from quantrex.core.data.cache.cache_key import CacheKey
from quantrex.core.data.cache.ohlcv_cache import OHLCVCache
from quantrex.core.models.market_data import OHLCVCandle
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
        "version": 2,
    }
    params.update(kwargs)
    return CacheKey.create(**params)


def make_candle(
    timestamp: datetime,
    symbol: str = "NSE:INFY",
    timeframe: Timeframe = TIMEFRAME,
) -> OHLCVCandle:
    """Build a candle with a known bar time."""
    return OHLCVCandle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=Decimal("1500.1234567890123456"),
        high=Decimal(1510),
        low=Decimal(1495),
        close=Decimal(1505),
        volume=Decimal(100),
    )


class TestOHLCVCache:
    """Tests for OHLCVCache."""

    def test_init_creates_directory(self, tmp_path: Path) -> None:
        """Test that initialization creates the base directory."""
        cache_dir = tmp_path / "ohlcv_cache"
        OHLCVCache(cache_dir)

        assert cache_dir.exists()

    def test_store_and_get_candles(self, tmp_path: Path) -> None:
        """Test storing and reading back candles."""
        cache = OHLCVCache(tmp_path)
        key = make_key()
        candles = [
            make_candle(FROM_DATE),
            make_candle(FROM_DATE + timedelta(minutes=1)),
        ]

        cache.store_candles(key, candles)
        retrieved = cache.get_candles(key)

        assert len(retrieved) == 2
        assert retrieved[0].symbol == "NSE:INFY"
        assert retrieved[0].open == Decimal("1500.1234567890123456")
        assert retrieved[0].high == Decimal(1510)
        assert retrieved[0].low == Decimal(1495)
        assert retrieved[0].close == Decimal(1505)
        assert retrieved[0].volume == Decimal(100)

    def test_bar_time_survives_the_round_trip(self, tmp_path: Path) -> None:
        """Test that the stored bar time is read back unchanged.

        Regression test: the cache wrote a timestamp column but never read
        it, so a cached candle carried the time of the read rather than the
        time of the bar.
        """
        cache = OHLCVCache(tmp_path)
        key = make_key()
        bar_time = datetime(2024, 1, 15, 9, 15, tzinfo=UTC)

        cache.store_candles(key, [make_candle(bar_time)])
        retrieved = cache.get_candles(key)

        assert retrieved[0].timestamp == bar_time

    def test_monthly_file_layout(self, tmp_path: Path) -> None:
        """Test that data is stored one file per calendar month."""
        cache = OHLCVCache(tmp_path)
        key = make_key()

        cache.store_candles(key, [make_candle(FROM_DATE)])
        files = list(tmp_path.rglob("*.feather"))

        assert len(files) == 1
        assert files[0].name == "2024-01.feather"

    def test_candles_spanning_two_months_use_two_files(self, tmp_path: Path) -> None:
        """Test that a range crossing a month boundary uses two files."""
        cache = OHLCVCache(tmp_path)
        feb = datetime(2024, 2, 1, 9, 15, tzinfo=UTC)
        key = make_key(from_date=FROM_DATE, to_date=feb + timedelta(minutes=1))

        cache.store_candles(key, [make_candle(FROM_DATE), make_candle(feb)])
        files = sorted(p.name for p in tmp_path.rglob("*.feather"))

        assert files == ["2024-01.feather", "2024-02.feather"]

    def test_coverage_is_recorded(self, tmp_path: Path) -> None:
        """Test that the fetched range is recorded as covered."""
        cache = OHLCVCache(tmp_path)
        key = make_key()

        cache.store_candles(key, [make_candle(FROM_DATE)])

        assert cache.get_coverage(key) == [(FROM_DATE, TO_DATE)]

    def test_empty_range_is_still_covered(self, tmp_path: Path) -> None:
        """Test that a range with no bars is recorded as covered.

        A holiday must not be requested from the vendor on every call.
        """
        cache = OHLCVCache(tmp_path)
        key = make_key()

        cache.store_candles(key, [])

        assert cache.get_coverage(key) == [(FROM_DATE, TO_DATE)]
        assert cache.get_candles(key) == []

    def test_overlapping_fetch_merges_without_duplicates(self, tmp_path: Path) -> None:
        """Test that a second, overlapping fetch merges into the same file."""
        cache = OHLCVCache(tmp_path)
        first = make_key()
        second = make_key(
            from_date=FROM_DATE + timedelta(minutes=1),
            to_date=FROM_DATE + timedelta(minutes=3),
        )

        cache.store_candles(first, [
            make_candle(FROM_DATE),
            make_candle(FROM_DATE + timedelta(minutes=1)),
        ])
        cache.store_candles(second, [
            make_candle(FROM_DATE + timedelta(minutes=1)),
            make_candle(FROM_DATE + timedelta(minutes=2)),
        ])

        everything = make_key(
            from_date=FROM_DATE,
            to_date=FROM_DATE + timedelta(minutes=5),
        )
        retrieved = cache.get_candles(everything)

        assert len(retrieved) == 3
        assert [c.timestamp for c in retrieved] == sorted(c.timestamp for c in retrieved)

    def test_coverage_merges_touching_intervals(self, tmp_path: Path) -> None:
        """Test that adjacent covered ranges become one interval."""
        cache = OHLCVCache(tmp_path)
        first = make_key()
        second = make_key(
            from_date=TO_DATE,
            to_date=TO_DATE + timedelta(hours=1),
        )

        cache.store_candles(first, [make_candle(FROM_DATE)])
        cache.store_candles(second, [make_candle(TO_DATE)])

        assert cache.get_coverage(first) == [
            (FROM_DATE, TO_DATE + timedelta(hours=1)),
        ]

    def test_vendor_options_use_separate_series(self, tmp_path: Path) -> None:
        """Test that continuous and non-continuous data do not share a file.

        Regression test: the monthly file name did not carry the vendor
        options, so a continuous-contract request could read a
        non-continuous entry.
        """
        cache = OHLCVCache(tmp_path)
        plain = make_key()
        continuous = make_key(continuous=True)

        cache.store_candles(plain, [make_candle(FROM_DATE)])
        cache.store_candles(continuous, [make_candle(FROM_DATE)])

        files = list(tmp_path.rglob("*.feather"))
        assert len(files) == 2

        assert len(cache.get_candles(plain)) == 1
        assert len(cache.get_candles(continuous)) == 1

    def test_version_uses_separate_series(self, tmp_path: Path) -> None:
        """Test that data written by a different version is not reused."""
        cache = OHLCVCache(tmp_path)
        old = make_key(version=1)
        new = make_key(version=2)

        cache.store_candles(old, [make_candle(FROM_DATE)])
        cache.store_candles(new, [make_candle(FROM_DATE)])

        assert len(list(tmp_path.rglob("*.feather"))) == 2

    def test_get_candles_outside_the_range_returns_nothing(self, tmp_path: Path) -> None:
        """Test that only bars inside the key's range are returned."""
        cache = OHLCVCache(tmp_path)
        key = make_key()
        cache.store_candles(key, [make_candle(FROM_DATE)])

        later = make_key(
            from_date=datetime(2024, 1, 16, 9, 15, tzinfo=UTC),
            to_date=datetime(2024, 1, 16, 10, 0, tzinfo=UTC),
        )

        assert cache.get_candles(later) == []

    def test_corrupt_file_is_discarded(self, tmp_path: Path) -> None:
        """Test that a corrupt file is removed and reported as a miss."""
        cache = OHLCVCache(tmp_path)
        key = make_key()
        cache.store_candles(key, [make_candle(FROM_DATE)])

        for path in tmp_path.rglob("*.feather"):
            path.write_bytes(b"not a feather file")

        assert cache.get_candles(key) == []

    def test_invalidate_removes_the_series(self, tmp_path: Path) -> None:
        """Test that invalidating a series deletes its files."""
        cache = OHLCVCache(tmp_path)
        key = make_key()
        cache.store_candles(key, [make_candle(FROM_DATE)])

        count = cache.invalidate(key)

        assert count == 1
        assert cache.get_candles(key) == []
        assert cache.get_coverage(key) == []

    def test_invalidate_leaves_other_series(self, tmp_path: Path) -> None:
        """Test that invalidating one series keeps the others."""
        cache = OHLCVCache(tmp_path)
        infy = make_key()
        reliance = make_key(symbol="NSE:RELIANCE")
        cache.store_candles(infy, [make_candle(FROM_DATE)])
        cache.store_candles(reliance, [make_candle(FROM_DATE, symbol="NSE:RELIANCE")])

        cache.invalidate(infy)

        assert cache.get_candles(infy) == []
        assert len(cache.get_candles(reliance)) == 1

    def test_clear_removes_everything(self, tmp_path: Path) -> None:
        """Test that clearing removes all cached files."""
        cache = OHLCVCache(tmp_path)
        cache.store_candles(make_key(), [make_candle(FROM_DATE)])
        cache.store_candles(
            make_key(symbol="NSE:RELIANCE"),
            [make_candle(FROM_DATE, symbol="NSE:RELIANCE")],
        )

        count = cache.clear()

        assert count == 2
        assert not list(tmp_path.rglob("*.feather"))

    def test_get_stats(self, tmp_path: Path) -> None:
        """Test that cache statistics are reported."""
        cache = OHLCVCache(tmp_path)

        stats = cache.get_stats()
        assert stats["total_files"] == 0
        assert stats["total_size_bytes"] == 0

        cache.store_candles(make_key(), [make_candle(FROM_DATE)])

        stats = cache.get_stats()
        assert stats["total_files"] == 1
        assert stats["total_size_bytes"] > 0
        assert stats["symbols"] == 1
        assert stats["timeframes"] == 1
