"""Arrow/Feather caching layer for Quantrex data.

Provides hierarchical, provider-isolated Feather (Apache Arrow) caching
with delta fetching for current partitions and background writes.
"""

import os
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.feather as feather

from quantrex_core.logging import get_logger

logger = get_logger(__name__)

# Arrow schema for cached market data
CACHE_SCHEMA = pa.schema([
    pa.field("datetime", pa.timestamp("us")),
    pa.field("open", pa.float64()),
    pa.field("high", pa.float64()),
    pa.field("low", pa.float64()),
    pa.field("close", pa.float64()),
    pa.field("volume", pa.float64()),
    pa.field("oi", pa.float64(), nullable=True),
    pa.field("symbol", pa.string()),
    pa.field("timeframe", pa.string()),
    pa.field("exchange", pa.string()),
    pa.field("provider", pa.string()),
])


def get_arrow_cache_dir() -> Path:
    """Get default cache directory from environment or use default."""
    cache_dir = os.getenv("QUANTREX_CACHE_DIR", "~/.quantrex/cache")
    return Path(cache_dir).expanduser()


class ArrowCache:
    """Low-level Feather cache operations. No fetch logic — pure storage.

    Features:
    - Hierarchical partitioning: provider/symbol/timeframe/year/month/
    - Provider isolation (dhan vs zerodha separate trees)
    - Immutable closed partitions (month < current month)
    - Delta fetching for current open partition
    - Background writes via ThreadPoolExecutor
    """

    def __init__(self, cache_root: Path | None = None, max_workers: int = 2):
        """Initialize ArrowCache.

        Args:
            cache_root: Root cache directory. Defaults to ~/.quantrex/cache
                       (or QUANTREX_CACHE_DIR env var).
            max_workers: Thread pool size for background writes.
        """
        self.cache_root = cache_root or get_arrow_cache_dir()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="arrow-cache")

    def _partition_path(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> Path:
        """Generate cache file path for a closed historical partition."""
        year = start.strftime("%Y")
        month = start.strftime("%m")
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")
        filename = f"{symbol}_{timeframe}_{start_str}_{end_str}.feather"
        return self.cache_root / provider / "historical" / symbol / timeframe / year / month / filename

    def _current_partition_path(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
    ) -> Path:
        """Generate cache file path for the current open partition (current month)."""
        now = datetime.now()
        year = now.strftime("%Y")
        month = now.strftime("%m")
        start_str = now.replace(day=1).strftime("%Y%m%d")
        end_str = now.strftime("%Y%m%d")
        filename = f"{symbol}_{timeframe}_{start_str}_{end_str}.feather"
        return self.cache_root / provider / "historical" / symbol / timeframe / year / month / filename

    def _is_current_partition(self, start: datetime) -> bool:
        """Check if a date range falls in the current month."""
        now = datetime.now()
        return start.year == now.year and start.month == now.month

    def _rows_to_table(self, rows: List[Dict[str, Any]]) -> pa.Table:
        """Convert list of dicts to Arrow Table with schema validation."""
        if not rows:
            return pa.Table.from_pylist([], schema=CACHE_SCHEMA)

        # Ensure all required fields exist
        for row in rows:
            row.setdefault("oi", None)
            row.setdefault("symbol", "")
            row.setdefault("timeframe", "")
            row.setdefault("exchange", "")
            row.setdefault("provider", "")

        # Convert datetime strings to timestamps
        for row in rows:
            dt_val = row.get("datetime")
            if isinstance(dt_val, str):
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        row["datetime"] = datetime.strptime(dt_val, fmt)
                        break
                    except ValueError:
                        continue
            elif isinstance(dt_val, datetime):
                row["datetime"] = dt_val

        return pa.Table.from_pylist(rows, schema=CACHE_SCHEMA)

    def _table_to_rows(self, table: pa.Table) -> List[Dict[str, Any]]:
        """Convert Arrow Table to list of dicts with datetime as formatted strings."""
        if table.num_rows == 0:
            return []

        # Convert to pandas for easier dict conversion, then format datetime
        df = table.to_pandas()
        df["datetime"] = df["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
        # Convert NaN to None for optional fields
        df = df.where(pd.notnull(df), None)
        return df.to_dict("records")

    def load_partition(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> List[Dict[str, Any]] | None:
        """Load cached data for an exact date range (closed partition).

        Args:
            provider: Provider name ("dhan" or "zerodha")
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "1M", "5M", "1H", "1D")
            start: Start datetime
            end: End datetime

        Returns:
            List of dicts if cache exists and is valid, None otherwise.
        """
        path = self._partition_path(provider, symbol, timeframe, start, end)

        if not path.exists():
            logger.debug("Cache miss for %s/%s/%s %s-%s", provider, symbol, timeframe, start, end)
            return None

        try:
            table = feather.read_table(path)
            rows = self._table_to_rows(table)
            logger.info("Loaded %d rows from cache: %s", len(rows), path)
            return rows
        except Exception as e:
            logger.warning("Failed to load cache from %s: %s", path, e)
            return None

    def load_current_partition(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
    ) -> List[Dict[str, Any]] | None:
        """Load all data from the current month's partition.

        Args:
            provider: Provider name ("dhan" or "zerodha")
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "1M", "5M", "1H", "1D")

        Returns:
            List of dicts if current partition exists, None otherwise.
        """
        path = self._current_partition_path(provider, symbol, timeframe)

        if not path.exists():
            logger.debug("No current partition for %s/%s/%s", provider, symbol, timeframe)
            return None

        try:
            table = feather.read_table(path)
            rows = self._table_to_rows(table)
            logger.info("Loaded %d rows from current partition: %s", len(rows), path)
            return rows
        except Exception as e:
            logger.warning("Failed to load current partition from %s: %s", path, e)
            return None

    def save_partition(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        data: List[Dict[str, Any]],
    ) -> None:
        """Save data to a closed historical partition (background write).

        Args:
            provider: Provider name ("dhan" or "zerodha")
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "1M", "5M", "1H", "1D")
            start: Start datetime
            end: End datetime
            data: List of OHLCV dicts
        """
        if not data:
            logger.warning("No data to cache for %s/%s/%s", provider, symbol, timeframe)
            return

        path = self._partition_path(provider, symbol, timeframe, start, end)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Enrich rows with metadata
        enriched = []
        for row in data:
            enriched_row = dict(row)
            enriched_row.setdefault("symbol", symbol)
            enriched_row.setdefault("timeframe", timeframe)
            enriched_row.setdefault("exchange", "NSE")  # Default, could be from config
            enriched_row.setdefault("provider", provider)
            enriched.append(enriched_row)

        table = self._rows_to_table(enriched)

        def _write():
            try:
                feather.write_feather(table, path, compression="zstd")
                logger.info("Cached %d rows to %s", len(data), path)
            except Exception as e:
                logger.warning("Background cache write failed for %s: %s", path, e)

        self._executor.submit(_write)

    def save_partition_sync(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        data: List[Dict[str, Any]],
    ) -> None:
        """Save data to a closed historical partition (synchronous write).

        For testing and cases where immediate persistence is required.

        Args:
            provider: Provider name ("dhan" or "zerodha")
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "1M", "5M", "1H", "1D")
            start: Start datetime
            end: End datetime
            data: List of OHLCV dicts
        """
        path = self._partition_path(provider, symbol, timeframe, start, end)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Enrich rows with metadata
        enriched = []
        for row in data:
            enriched_row = dict(row)
            enriched_row.setdefault("symbol", symbol)
            enriched_row.setdefault("timeframe", timeframe)
            enriched_row.setdefault("exchange", "NSE")
            enriched_row.setdefault("provider", provider)
            enriched.append(enriched_row)

        table = self._rows_to_table(enriched)

        try:
            feather.write_feather(table, path, compression="zstd")
            logger.info("Cached %d rows to %s (sync)", len(data), path)
        except Exception as e:
            logger.warning("Sync cache write failed for %s: %s", path, e)
            raise

    def append_to_current_partition(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
        new_rows: List[Dict[str, Any]],
    ) -> None:
        """Append new rows to the current month's partition (background write).

        Performs read-merge-write atomically for delta updates.

        Args:
            provider: Provider name ("dhan" or "zerodha")
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "1M", "5M", "1H", "1D")
            new_rows: New OHLCV dicts to append
        """
        if not new_rows:
            return

        path = self._current_partition_path(provider, symbol, timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)

        def _append():
            try:
                # Read existing data
                existing_rows = []
                if path.exists():
                    try:
                        existing_table = feather.read_table(path)
                        existing_rows = self._table_to_rows(existing_table)
                    except Exception:
                        logger.warning("Could not read existing partition, starting fresh: %s", path)

                # Merge: deduplicate by datetime (keep latest)
                all_rows = existing_rows + new_rows
                seen = {}
                for row in all_rows:
                    dt = row.get("datetime")
                    if dt:
                        seen[dt] = row  # Last write wins

                merged = list(seen.values())
                merged.sort(key=lambda r: r.get("datetime", ""))

                # Enrich with metadata
                enriched = []
                for row in merged:
                    enriched_row = dict(row)
                    enriched_row.setdefault("symbol", symbol)
                    enriched_row.setdefault("timeframe", timeframe)
                    enriched_row.setdefault("exchange", "NSE")
                    enriched_row.setdefault("provider", provider)
                    enriched.append(enriched_row)

                table = self._rows_to_table(enriched)
                feather.write_feather(table, path, compression="zstd")
                logger.info("Appended %d rows to current partition (total: %d): %s",
                           len(new_rows), len(merged), path)
            except Exception as e:
                logger.warning("Background append to current partition failed for %s: %s", path, e)

        self._executor.submit(_append)

    def append_to_current_partition_sync(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
        new_rows: List[Dict[str, Any]],
    ) -> None:
        """Append new rows to the current month's partition (synchronous write).

        For testing and cases where immediate persistence is required.

        Args:
            provider: Provider name ("dhan" or "zerodha")
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "1M", "5M", "1H", "1D")
            new_rows: New OHLCV dicts to append
        """
        if not new_rows:
            return

        path = self._current_partition_path(provider, symbol, timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Read existing data
            existing_rows = []
            if path.exists():
                try:
                    existing_table = feather.read_table(path)
                    existing_rows = self._table_to_rows(existing_table)
                except Exception:
                    logger.warning("Could not read existing partition, starting fresh: %s", path)

            # Merge: deduplicate by datetime (keep latest)
            all_rows = existing_rows + new_rows
            seen = {}
            for row in all_rows:
                dt = row.get("datetime")
                if dt:
                    seen[dt] = row  # Last write wins

            merged = list(seen.values())
            merged.sort(key=lambda r: r.get("datetime", ""))

            # Enrich with metadata
            enriched = []
            for row in merged:
                enriched_row = dict(row)
                enriched_row.setdefault("symbol", symbol)
                enriched_row.setdefault("timeframe", timeframe)
                enriched_row.setdefault("exchange", "NSE")
                enriched_row.setdefault("provider", provider)
                enriched.append(enriched_row)

            table = self._rows_to_table(enriched)
            feather.write_feather(table, path, compression="zstd")
            logger.info("Appended %d rows to current partition (total: %d) (sync): %s",
                       len(new_rows), len(merged), path)
        except Exception as e:
            logger.warning("Sync append to current partition failed for %s: %s", path, e)
            raise

    def get_last_timestamp(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
    ) -> datetime | None:
        """Get the latest timestamp from the current partition.

        Used for delta fetching to determine where to resume.

        Args:
            provider: Provider name ("dhan" or "zerodha")
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "1M", "5M", "1H", "1D")

        Returns:
            Latest datetime in current partition, or None if no partition exists.
        """
        path = self._current_partition_path(provider, symbol, timeframe)

        if not path.exists():
            return None

        try:
            table = feather.read_table(path, columns=["datetime"])
            if table.num_rows == 0:
                return None

            # Get max datetime - convert to pandas for easier max computation
            df = table.to_pandas()
            max_ts = df["datetime"].max()
            if max_ts is None or pd.isna(max_ts):
                return None

            return max_ts.to_pydatetime()
        except Exception as e:
            logger.warning("Failed to get last timestamp from %s: %s", path, e)
            return None

    def clear(
        self,
        provider: str | None = None,
        symbol: str | None = None,
    ) -> int:
        """Clear cache files matching criteria.

        Args:
            provider: Optional provider to filter ("dhan" or "zerodha")
            symbol: Optional symbol to filter

        Returns:
            Number of files deleted.
        """
        pattern = "**/*.feather"
        if provider:
            pattern = f"{provider}/**/*.feather"
        if symbol:
            pattern = f"**/{symbol}/**/*.feather"

        deleted = 0
        for path in self.cache_root.glob(pattern):
            try:
                path.unlink()
                deleted += 1
            except Exception as e:
                logger.warning("Failed to delete cache file %s: %s", path, e)

        logger.info("Cleared %d cache files", deleted)
        return deleted

    def shutdown(self) -> None:
        """Shutdown background thread pool."""
        self._executor.shutdown(wait=True)