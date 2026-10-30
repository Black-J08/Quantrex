"""Feather-backed disk cache for canonical OHLCV candles.

Candles are grouped into one file per (symbol, timeframe, calendar month), so
a growing cache stays a set of bounded files instead of one file per query.
Each file records the intervals it covers in its Arrow schema metadata, which
lets a caller work out which part of a requested range is already on disk
without reading any rows.

This is an internal implementation detail of the historical data providers; it
is not part of the public API.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
from pyarrow import feather  # type: ignore[import-untyped]

from quantrex.core.data.cache.cache_key import CacheKey
from quantrex.core.data.exceptions.exceptions import CacheReadError, CacheWriteError
from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe

logger = logging.getLogger(__name__)

#: Arrow schema for a month's worth of candles.
#:
#: The timestamp column carries a fixed +05:30 offset so a bar keeps the
#: exact offset the vendor reported. A UTC column would re-label every bar
#: in UTC, which shifts a daily bar onto the previous calendar day.
OHLCV_SCHEMA = pa.schema([
    pa.field("timestamp", pa.timestamp("us", tz="+05:30")),
    pa.field("open", pa.decimal128(38, 16)),
    pa.field("high", pa.decimal128(38, 16)),
    pa.field("low", pa.decimal128(38, 16)),
    pa.field("close", pa.decimal128(38, 16)),
    pa.field("volume", pa.decimal128(38, 16)),
    pa.field("symbol", pa.string()),
    pa.field("timeframe", pa.string()),
])

#: Schema metadata key holding the JSON-encoded covered intervals.
COVERAGE_KEY = b"coverage"

#: Bytes per mebibyte, used for cache statistics display.
BYTES_PER_MIB = 1024 * 1024


def _month_key(dt: datetime) -> str:
    """Return the calendar month an instant belongs to, in UTC."""
    return dt.astimezone(UTC).strftime("%Y-%m")


def _merge_intervals(
    intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """Merge overlapping or touching intervals into a minimal set."""
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def missing_intervals(
    start: datetime,
    end: datetime,
    covered: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """Return the parts of ``[start, end)`` that ``covered`` does not cover."""
    gaps: list[tuple[datetime, datetime]] = []
    cursor = start
    for cover_start, cover_end in covered:
        if cover_end <= cursor:
            continue
        if cover_start >= end:
            break
        if cover_start > cursor:
            gaps.append((cursor, min(cover_start, end)))
        cursor = max(cursor, cover_end)
        if cursor >= end:
            break
    if cursor < end:
        gaps.append((cursor, end))
    return gaps


class OHLCVCache:
    """Disk cache for canonical OHLCV candles, stored as monthly Feather files.

    The cache is keyed by symbol, timeframe, calendar month and vendor
    options. Within a month, candles are merged by bar time and the set of
    covered intervals is tracked in the file's schema metadata.
    """

    def __init__(
        self,
        base_dir: Path | str = "~/.quantrex/cache/zerodha/historical",
        *,
        create_dirs: bool = True,
    ) -> None:
        """Initialize the cache.

        Args:
            base_dir: Root directory for the cache files.
            create_dirs: Whether to create the root directory on init.
        """
        self._base_dir = Path(base_dir).expanduser().resolve()
        if create_dirs:
            self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        """Get the root cache directory."""
        return self._base_dir

    def _series_dir(self, key: CacheKey) -> Path:
        """Get the directory holding one series' monthly files."""
        return self._base_dir / CacheKey.encode_symbol(key.symbol) / key.series_name()

    def _month_path(self, key: CacheKey, month: str) -> Path:
        """Get the path of one series' monthly file."""
        return self._series_dir(key) / f"{month}.feather"

    def _read_table(self, path: Path) -> pa.Table | None:
        """Read a Feather file, returning None when it is missing or corrupt."""
        if not path.exists():
            return None
        try:
            return feather.read_table(path)
        except (OSError, pa.ArrowException, ValueError) as e:
            logger.warning("Failed to read cache file %s: %s", path, e)
            try:
                path.unlink()
            except OSError as unlink_error:
                logger.warning("Failed to delete corrupt cache file %s: %s", path, unlink_error)
                raise CacheReadError(f"Corrupt cache file {path} and cannot be deleted: {unlink_error}") from unlink_error
            return None

    def _read_coverage(self, path: Path) -> list[tuple[datetime, datetime]]:
        """Read the covered intervals recorded in a file's schema metadata.

        Only the schema is read, so this stays cheap even for a large file.
        """
        if not path.exists():
            return []
        try:
            with pa.ipc.open_file(path) as reader:
                metadata = reader.schema.metadata
        except (OSError, pa.ArrowException, ValueError) as e:
            logger.warning("Failed to read coverage from cache file %s: %s", path, e)
            raise CacheReadError(f"Failed to read coverage from {path}: {e}") from e

        if not metadata or COVERAGE_KEY not in metadata:
            return []

        try:
            raw = json.loads(metadata[COVERAGE_KEY].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.warning("Failed to decode coverage metadata from cache file %s: %s", path, e)
            raise CacheReadError(f"Failed to decode coverage metadata from {path}: {e}") from e

        intervals = []
        for pair in raw:
            try:
                start, end = pair
                intervals.append((
                    datetime.fromisoformat(start),
                    datetime.fromisoformat(end),
                ))
            except (TypeError, ValueError) as e:
                logger.warning("Skipping malformed coverage interval: %s", e)
                continue
        return _merge_intervals(intervals)

    def _write_table(
        self,
        path: Path,
        table: pa.Table,
        coverage: list[tuple[datetime, datetime]],
    ) -> None:
        """Write a table and its coverage metadata atomically."""
        path.parent.mkdir(parents=True, exist_ok=True)

        encoded = json.dumps(
            [[start.isoformat(), end.isoformat()] for start, end in coverage]
        ).encode("utf-8")
        table = table.replace_schema_metadata({COVERAGE_KEY: encoded})

        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.tmp.",
            suffix=".feather",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            try:
                feather.write_feather(table, tmp_path)
                tmp_path.rename(path)
            except Exception:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError as unlink_error:
                    logger.warning("Failed to delete temp cache file %s: %s", tmp_path, unlink_error)
                    raise CacheWriteError(f"Failed to delete temp cache file {tmp_path}: {unlink_error}") from unlink_error
                raise

    @staticmethod
    def _serialize(candles: list[OHLCVCandle]) -> pa.Table:
        """Serialize candles into an Arrow table."""
        if not candles:
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

        return pa.Table.from_pydict({
            "timestamp": [c.timestamp for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
            "symbol": [c.symbol for c in candles],
            "timeframe": [str(c.timeframe) for c in candles],
        }, schema=OHLCV_SCHEMA)

    @staticmethod
    def _deserialize(table: pa.Table) -> list[OHLCVCandle]:
        """Deserialize an Arrow table into candles.

        The bar time is read back from the ``timestamp`` column so a cached
        candle carries the same bar time as a freshly fetched one.
        """
        if len(table) == 0:
            return []

        frame = table.to_pandas()
        candles = []
        for row in frame.itertuples(index=False):
            candles.append(
                OHLCVCandle(
                    symbol=row.symbol,
                    timeframe=Timeframe.from_string(row.timeframe),
                    timestamp=row.timestamp.to_pydatetime(),
                    open=Decimal(str(row.open)),
                    high=Decimal(str(row.high)),
                    low=Decimal(str(row.low)),
                    close=Decimal(str(row.close)),
                    volume=Decimal(str(row.volume)),
                )
            )
        return candles

    def get_coverage(self, key: CacheKey) -> list[tuple[datetime, datetime]]:
        """Return the intervals already covered on disk, across all months."""
        intervals: list[tuple[datetime, datetime]] = []
        directory = self._series_dir(key)
        if not directory.exists():
            return []

        for path in sorted(directory.glob("*.feather")):
            intervals.extend(self._read_coverage(path))
        return _merge_intervals(intervals)

    def get_cached_candles(self, key: CacheKey) -> list[OHLCVCandle]:
        """Return the cached candles within the key's range.

        Args:
            key: The query whose candles are wanted.

        Returns:
            The cached candles within the range, sorted by bar time.
        """
        candles: list[OHLCVCandle] = []
        directory = self._series_dir(key)
        if not directory.exists():
            return candles

        for path in sorted(directory.glob("*.feather")):
            table = self._read_table(path)
            if table is None:
                continue
            for candle in self._deserialize(table):
                # Compare instants: the key is normalized to UTC while the
                # candle keeps the offset the vendor reported.
                if key.from_date <= candle.timestamp < key.to_date:
                    candles.append(candle)

        candles.sort(key=lambda c: c.timestamp)
        return candles

    def store_candles(
        self,
        key: CacheKey,
        candles: list[OHLCVCandle],
    ) -> None:
        """Merge candles into the monthly files and record what is covered.

        Candles are grouped by the calendar month of their bar time, merged
        with whatever is already stored for that month, and written back.
        The requested range is recorded as covered even when the vendor
        returned no bars for it, so a holiday is not requested repeatedly.

        Args:
            key: The query the candles were fetched for.
            candles: The fetched candles.
        """
        by_month: dict[str, list[OHLCVCandle]] = {}
        for candle in candles:
            by_month.setdefault(_month_key(candle.timestamp), []).append(candle)

        for month in self._months_between(key.from_date, key.to_date):
            path = self._month_path(key, month)
            existing = self._read_table(path)
            merged_candles = self._merge_candles(
                self._deserialize(existing) if existing is not None else [],
                by_month.get(month, []),
            )
            coverage = _merge_intervals(
                self._read_coverage(path) + [(key.from_date, key.to_date)]
            )
            self._write_table(path, self._serialize(merged_candles), coverage)

    @staticmethod
    def _merge_candles(
        existing: list[OHLCVCandle],
        incoming: list[OHLCVCandle],
    ) -> list[OHLCVCandle]:
        """Merge two candle lists by bar time, keeping the first of each.

        Bars are keyed by their instant, so the same bar reported with two
        different UTC offsets is still recognized as one bar.
        """
        merged: dict[datetime, OHLCVCandle] = {}
        for candle in existing:
            merged.setdefault(candle.timestamp.astimezone(UTC), candle)
        for candle in incoming:
            merged.setdefault(candle.timestamp.astimezone(UTC), candle)
        return [merged[ts] for ts in sorted(merged)]

    @staticmethod
    def _months_between(from_date: datetime, to_date: datetime) -> list[str]:
        """List the calendar months spanned by a range, in order."""
        months: list[str] = []
        start = from_date.astimezone(UTC)
        last = to_date.astimezone(UTC)
        year, month = start.year, start.month
        while (year, month) <= (last.year, last.month):
            months.append(f"{year:04d}-{month:02d}")
            month += 1
            if month == 13:
                year, month = year + 1, 1
        return months

    def invalidate(self, key: CacheKey) -> int:
        """Delete every cached file for one series.

        Args:
            key: The series to clear.

        Returns:
            The number of files deleted.
        """
        directory = self._series_dir(key)
        if not directory.exists():
            return 0

        count = 0
        for path in directory.glob("*.feather"):
            try:
                path.unlink()
                count += 1
            except OSError as e:
                logger.warning("Failed to delete %s: %s", path, e)
                raise CacheWriteError(f"Failed to delete cache file {path}: {e}") from e

        try:
            directory.rmdir()
            directory.parent.rmdir()
        except OSError as e:
            logger.warning("Failed to remove cache directories for %s: %s", key.symbol, e)
            raise CacheWriteError(f"Failed to remove cache directories for {key.symbol}: {e}") from e

        logger.info("Invalidated %d cache files for %s/%s", count, key.symbol, key.timeframe)
        return count

    def clear(self) -> int:
        """Delete every cached file.

        Returns:
            The number of files deleted.
        """
        if not self._base_dir.exists():
            return 0

        count = 0
        for path in self._base_dir.rglob("*.feather"):
            try:
                path.unlink()
                count += 1
            except OSError as e:
                logger.warning("Failed to delete %s: %s", path, e)
                raise CacheWriteError(f"Failed to delete cache file {path}: {e}") from e

        try:
            shutil.rmtree(self._base_dir)
        except OSError as e:
            logger.warning("Failed to remove cache directory %s: %s", self._base_dir, e)
            raise CacheWriteError(f"Failed to remove cache directory {self._base_dir}: {e}") from e
        logger.info("Cleared %d cache files", count)
        return count

    def get_stats(self) -> dict[str, Any]:
        """Return statistics about the cache contents."""
        if not self._base_dir.exists():
            return {
                "base_dir": str(self._base_dir),
                "total_files": 0,
                "total_size_bytes": 0,
                "symbols": 0,
                "timeframes": 0,
            }

        files = list(self._base_dir.rglob("*.feather"))
        total_size = sum(f.stat().st_size for f in files)
        symbols = {f.parent.parent.name for f in files}
        timeframes = {f.parent.name for f in files}

        return {
            "base_dir": str(self._base_dir),
            "total_files": len(files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / BYTES_PER_MIB, 2),
            "symbols": len(symbols),
            "timeframes": len(timeframes),
        }
