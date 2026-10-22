"""Tests for OHLCV cache."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from quantrex.core.data.cache.ohlcv_cache import OHLCVCache
from quantrex.core.models import OHLCVCandle, Timeframe, TimeframeUnit


class TestOHLCVCache:
    """Tests for OHLCVCache."""

    def test_init_creates_directory(self) -> None:
        """Test that initialization creates base directory."""
        with TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "ohlcv_cache"
            OHLCVCache(cache_dir)
            assert cache_dir.exists()

    def test_get_candles_returns_none_for_missing(self) -> None:
        """Test get_candles returns None for missing cache."""
        with TemporaryDirectory() as tmpdir:
            cache = OHLCVCache(Path(tmpdir))
            candles = cache.get_candles(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            assert candles is None

    def test_set_and_get_candles(self) -> None:
        """Test setting and getting candles."""
        with TemporaryDirectory() as tmpdir:
            cache = OHLCVCache(Path(tmpdir))
            
            candles = [
                OHLCVCandle(
                    symbol="NSE:INFY",
                    timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                    open=Decimal("1500.0"),
                    high=Decimal("1510.0"),
                    low=Decimal("1495.0"),
                    close=Decimal("1505.0"),
                    volume=Decimal(100000),
                ),
                OHLCVCandle(
                    symbol="NSE:INFY",
                    timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                    open=Decimal("1505.0"),
                    high=Decimal("1515.0"),
                    low=Decimal("1500.0"),
                    close=Decimal("1510.0"),
                    volume=Decimal(80000),
                ),
            ]
            
            cache.set_candles(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
                candles=candles,
            )
            
            retrieved = cache.get_candles(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            
            assert retrieved is not None
            assert len(retrieved) == 2
            assert retrieved[0].symbol == "NSE:INFY"
            assert retrieved[0].open == Decimal("1500.0")
            assert retrieved[0].high == Decimal("1510.0")
            assert retrieved[0].low == Decimal("1495.0")
            assert retrieved[0].close == Decimal("1505.0")
            assert retrieved[0].volume == Decimal(100000)

    def test_invalidate_symbol_timeframe(self) -> None:
        """Test invalidating all entries for symbol/timeframe."""
        with TemporaryDirectory() as tmpdir:
            cache = OHLCVCache(Path(tmpdir))
            
            candles = [
                OHLCVCandle(
                    symbol="NSE:INFY",
                    timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                    open=Decimal("1500.0"),
                    high=Decimal("1510.0"),
                    low=Decimal("1495.0"),
                    close=Decimal("1505.0"),
                    volume=Decimal(100000),
                ),
            ]
            
            # Set candles for two different date ranges
            cache.set_candles(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
                candles=candles,
            )
            cache.set_candles(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 16),
                to_date=date(2024, 1, 16),
                candles=candles,
            )
            # Different symbol
            cache.set_candles(
                symbol="NSE:RELIANCE",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
                candles=candles,
            )
            
            # Invalidate NSE:INFY 1m
            count = cache.invalidate_symbol_timeframe("NSE:INFY", Timeframe(value=1, unit=TimeframeUnit.MINUTE))
            assert count == 2
            
            # Check they're gone
            assert cache.get_candles("NSE:INFY", Timeframe(value=1, unit=TimeframeUnit.MINUTE), date(2024, 1, 15), date(2024, 1, 15)) is None
            assert cache.get_candles("NSE:INFY", Timeframe(value=1, unit=TimeframeUnit.MINUTE), date(2024, 1, 16), date(2024, 1, 16)) is None
            # Different symbol should remain
            assert cache.get_candles("NSE:RELIANCE", Timeframe(value=1, unit=TimeframeUnit.MINUTE), date(2024, 1, 15), date(2024, 1, 15)) is not None

    def test_get_cached_date_ranges(self) -> None:
        """Test getting all cached date ranges for symbol/timeframe."""
        with TemporaryDirectory() as tmpdir:
            cache = OHLCVCache(Path(tmpdir))
            
            candles = [
                OHLCVCandle(
                    symbol="NSE:INFY",
                    timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                    open=Decimal("1500.0"),
                    high=Decimal("1510.0"),
                    low=Decimal("1495.0"),
                    close=Decimal("1505.0"),
                    volume=Decimal(100000),
                ),
            ]
            
            # Set candles for multiple date ranges
            cache.set_candles("NSE:INFY", Timeframe(value=1, unit=TimeframeUnit.MINUTE), date(2024, 1, 15), date(2024, 1, 15), candles)
            cache.set_candles("NSE:INFY", Timeframe(value=1, unit=TimeframeUnit.MINUTE), date(2024, 1, 16), date(2024, 1, 16), candles)
            cache.set_candles("NSE:INFY", Timeframe(value=1, unit=TimeframeUnit.MINUTE), date(2024, 1, 17), date(2024, 1, 17), candles, version=2)
            
            ranges = cache.get_cached_date_ranges("NSE:INFY", Timeframe(value=1, unit=TimeframeUnit.MINUTE))
            
            assert len(ranges) == 3
            assert ranges[0] == (date(2024, 1, 15), date(2024, 1, 15), 1)
            assert ranges[1] == (date(2024, 1, 16), date(2024, 1, 16), 1)
            assert ranges[2] == (date(2024, 1, 17), date(2024, 1, 17), 2)

    def test_empty_candles(self) -> None:
        """Test handling empty candle list."""
        with TemporaryDirectory() as tmpdir:
            cache = OHLCVCache(Path(tmpdir))
            
            cache.set_candles(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
                candles=[],
            )
            
            retrieved = cache.get_candles(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            
            assert retrieved == []

    def test_datetime_from_date(self) -> None:
        """Test that datetime objects work for from_date/to_date."""
        with TemporaryDirectory() as tmpdir:
            cache = OHLCVCache(Path(tmpdir))
            
            candles = [
                OHLCVCandle(
                    symbol="NSE:INFY",
                    timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                    open=Decimal("1500.0"),
                    high=Decimal("1510.0"),
                    low=Decimal("1495.0"),
                    close=Decimal("1505.0"),
                    volume=Decimal(100000),
                ),
            ]
            
            cache.set_candles(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=datetime(2024, 1, 15, 9, 15, tzinfo=UTC),
                to_date=datetime(2024, 1, 15, 15, 30, tzinfo=UTC),
                candles=candles,
            )
            
            retrieved = cache.get_candles(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=date(2024, 1, 15),
                to_date=date(2024, 1, 15),
            )
            
            assert retrieved is not None
            assert len(retrieved) == 1