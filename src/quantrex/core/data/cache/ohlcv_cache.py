"""OHLCV-specific Feather cache implementation."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]

from quantrex.core.data.cache.cache_key import CacheKey
from quantrex.core.data.cache.disk_cache import DiskCache
from quantrex.core.models import OHLCVCandle, Timeframe

logger = logging.getLogger(__name__)

# Feather schema for OHLCV data
OHLCV_SCHEMA = pa.schema([
    pa.field("timestamp", pa.timestamp("us", tz="UTC")),
    pa.field("open", pa.decimal128(38, 16)),
    pa.field("high", pa.decimal128(38, 16)),
    pa.field("low", pa.decimal128(38, 16)),
    pa.field("close", pa.decimal128(38, 16)),
    pa.field("volume", pa.decimal128(38, 16)),
    pa.field("symbol", pa.string()),
    pa.field("timeframe", pa.string()),
])


class OHLCVCache(DiskCache[list[OHLCVCandle]]):
    """Feather-based disk cache for OHLCV candle data.
    
    Stores OHLCVCandle lists as Feather files with a fixed schema.
    Provides efficient columnar storage with zero-copy reads.
    """

    def __init__(
        self,
        base_dir: Path | str = "~/.quantrex/cache/zerodha/historical",
        *,
        create_dirs: bool = True,
    ) -> None:
        """Initialize OHLCV cache.
        
        Args:
            base_dir: Base directory for cache files (default: ~/.quantrex/cache/zerodha/historical)
            create_dirs: Whether to create directories on init
        """
        super().__init__(base_dir, create_dirs=create_dirs)

    def _serialize(self, candles: list[OHLCVCandle]) -> pa.Table:
        """Serialize OHLCV candles to PyArrow Table.
        
        Args:
            candles: List of OHLCVCandle objects
            
        Returns:
            PyArrow Table with OHLCV schema
        """
        if not candles:
            # Return empty table with correct schema
            return pa.Table.from_pydict({
                "timestamp": [],
                "open": [],
                "high": [],
                "low": [],
                "close": [],
                "volume": [],
                "symbol": [],
                "timeframe": [],
            }, schema=OHLCV_SCHEMA)

        # Extract data from candles
        timestamps = []
        opens = []
        highs = []
        lows = []
        closes = []
        volumes = []
        symbols = []
        timeframes = []

        for candle in candles:
            timestamps.append(candle.timestamp)
            opens.append(candle.open)
            highs.append(candle.high)
            lows.append(candle.low)
            closes.append(candle.close)
            volumes.append(candle.volume)
            symbols.append(candle.symbol)
            timeframes.append(str(candle.timeframe))

        return pa.Table.from_pydict({
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
            "symbol": symbols,
            "timeframe": timeframes,
        }, schema=OHLCV_SCHEMA)

    def _deserialize(self, table: pa.Table) -> list[OHLCVCandle]:
        """Deserialize PyArrow Table to OHLCV candles.
        
        Args:
            table: PyArrow Table with OHLCV schema
            
        Returns:
            List of OHLCVCandle objects
        """
        if len(table) == 0:
            return []

        candles = []
        # Convert to pandas for easier iteration (zero-copy)
        df = table.to_pandas()
        
        for _, row in df.iterrows():
            candle = OHLCVCandle(
                symbol=row["symbol"],
                timeframe=Timeframe.from_string(row["timeframe"]),
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
            )
            candles.append(candle)

        return candles

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        from_date: Any,
        to_date: Any,
        version: int = 1,
    ) -> list[OHLCVCandle] | None:
        """Get cached candles for a symbol/timeframe/date range.
        
        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            from_date: Start date
            to_date: End date
            version: Cache version
            
        Returns:
            List of OHLCVCandle or None if not cached
        """
        key = CacheKey.create(symbol, timeframe, from_date, to_date, version)
        return self.get(key)

    def set_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        from_date: Any,
        to_date: Any,
        candles: list[OHLCVCandle],
        version: int = 1,
    ) -> None:
        """Cache candles for a symbol/timeframe/date range.
        
        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            from_date: Start date
            to_date: End date
            candles: List of OHLCVCandle to cache
            version: Cache version
        """
        key = CacheKey.create(symbol, timeframe, from_date, to_date, version)
        self.set(key, candles)

    def invalidate_symbol_timeframe(self, symbol: str, timeframe: Timeframe) -> int:
        """Invalidate all cache entries for a symbol/timeframe.
        
        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            
        Returns:
            Number of files deleted
        """
        return self.invalidate(symbol, str(timeframe))

    def get_cached_date_ranges(self, symbol: str, timeframe: Timeframe) -> list[tuple[Any, Any, int]]:
        """Get all cached date ranges for a symbol/timeframe.
        
        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            
        Returns:
            List of (from_date, to_date, version) tuples
        """
        safe_symbol = symbol.replace(":", "_").replace("/", "_")
        tf_str = str(timeframe)
        cache_dir = self._base_dir / safe_symbol / tf_str
        
        if not cache_dir.exists():
            return []

        ranges = []
        for file_path in cache_dir.glob("*.feather"):
            key = CacheKey.from_filename(file_path.name)
            if key and key.symbol == symbol and key.timeframe == timeframe:
                ranges.append((key.from_date, key.to_date, key.version))
        
        return sorted(ranges, key=lambda x: (x[0], x[1]))