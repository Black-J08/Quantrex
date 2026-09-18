"""Parquet caching layer for Quantrex data."""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd

from quantrex_core.logging import get_logger

logger = get_logger(__name__)


class ParquetCache:
    """Parquet-based caching for market data."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> Path:
        """Generate cache file path."""
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")
        filename = f"{symbol}_{timeframe}_{start_str}_{end_str}.parquet"
        return self.cache_dir / filename

    def save(self, symbol: str, timeframe: str, start: datetime, end: datetime, data: List[Dict[str, Any]]) -> None:
        """Save data to Parquet cache."""
        if not data:
            logger.warning("No data to cache for %s %s", symbol, timeframe)
            return

        path = self._get_cache_path(symbol, timeframe, start, end)
        df = pd.DataFrame(data)

        # Ensure datetime column is proper datetime type
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"])

        try:
            df.to_parquet(path, index=False)
            logger.info("Cached %d rows for %s %s to %s", len(data), symbol, timeframe, path)
        except Exception as e:
            logger.exception("Failed to cache data for %s: %s", symbol, e)
            raise

    def load(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> Optional[List[Dict[str, Any]]]:
        """Load data from Parquet cache."""
        path = self._get_cache_path(symbol, timeframe, start, end)

        if not path.exists():
            logger.debug("Cache miss for %s %s %s-%s", symbol, timeframe, start, end)
            return None

        try:
            df = pd.read_parquet(path)
            # Keep datetime as-is (don't convert format) - let the adapter handle parsing
            data = df.to_dict("records")
            logger.info("Loaded %d rows for %s %s from cache", len(data), symbol, timeframe)
            return data
        except Exception as e:
            logger.exception("Failed to load cache for %s: %s", symbol, e)
            return None

    def exists(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> bool:
        """Check if cache exists for given parameters."""
        path = self._get_cache_path(symbol, timeframe, start, end)
        return path.exists()

    def clear(self, symbol: Optional[str] = None, timeframe: Optional[str] = None) -> int:
        """Clear cache files matching criteria.

        Args:
            symbol: Optional symbol to filter.
            timeframe: Optional timeframe to filter.

        Returns:
            Number of files deleted.
        """
        pattern = "*"
        if symbol:
            pattern = f"{symbol}_*"
        if timeframe:
            pattern = f"{pattern}{timeframe}_*"
        pattern = f"{pattern}*.parquet"

        deleted = 0
        for path in self.cache_dir.glob(pattern):
            try:
                path.unlink()
                deleted += 1
            except Exception as e:
                logger.warning("Failed to delete cache file %s: %s", path, e)

        logger.info("Cleared %d cache files", deleted)
        return deleted


def get_cache_dir() -> Path:
    """Get default cache directory from environment or use default."""
    cache_dir = os.getenv("QUANTREX_CACHE_DIR", "data/cache")
    return Path(cache_dir)