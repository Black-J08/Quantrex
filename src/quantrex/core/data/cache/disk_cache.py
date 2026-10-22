"""Generic Feather-based disk cache implementation."""

from __future__ import annotations

import logging
import shutil
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypeVar

import pyarrow as pa  # type: ignore[import-untyped]
from pyarrow import feather  # type: ignore[import-untyped]

from quantrex.core.data.cache.cache_key import CacheKey

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DiskCache[T](ABC):
    """Abstract base class for Feather-based disk cache.
    
    Provides atomic write operations (write to temp, then rename) and
    generic read/write interface for cached data.
    """

    def __init__(
        self,
        base_dir: Path | str,
        *,
        create_dirs: bool = True,
    ) -> None:
        """Initialize disk cache.
        
        Args:
            base_dir: Base directory for cache files
            create_dirs: Whether to create directories on init
        """
        self._base_dir = Path(base_dir).expanduser().resolve()
        if create_dirs:
            self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        """Get base cache directory."""
        return self._base_dir

    @abstractmethod
    def _serialize(self, data: T) -> pa.Table:
        """Serialize data to PyArrow Table for Feather storage."""
        ...

    @abstractmethod
    def _deserialize(self, table: pa.Table) -> T:
        """Deserialize PyArrow Table back to data."""
        ...

    def _get_cache_path(self, key: CacheKey) -> Path:
        """Get full path for a cache key."""
        return key.to_path(self._base_dir)

    def exists(self, key: CacheKey) -> bool:
        """Check if cache entry exists."""
        path = self._get_cache_path(key)
        return path.exists()

    def get(self, key: CacheKey) -> T | None:
        """Read cached data.
        
        Args:
            key: Cache key to read
            
        Returns:
            Deserialized data or None if not found/corrupted
        """
        path = self._get_cache_path(key)
        if not path.exists():
            logger.debug("Cache miss: %s", path)
            return None

        try:
            table = feather.read_table(path)
            data = self._deserialize(table)
            logger.debug("Cache hit: %s (%d rows)", path, len(table))
            return data
        except (OSError, pa.ArrowError, ValueError) as e:
            logger.warning("Failed to read cache %s: %s", path, e)
            # Optionally remove corrupted cache file
            try:
                path.unlink()
            except OSError:
                pass
            return None

    def set(self, key: CacheKey, data: T) -> None:
        """Write data to cache atomically.
        
        Uses write-to-temp-then-rename for atomicity.
        
        Args:
            key: Cache key
            data: Data to cache
        """
        path = self._get_cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        table = self._serialize(data)

        # Atomic write: write to temp file, then rename
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.tmp.",
            suffix=".feather",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            try:
                feather.write_feather(table, tmp_path)
                tmp_path.rename(path)  # Atomic on POSIX
                logger.debug("Cache written: %s (%d rows)", path, len(table))
            except Exception as e:
                logger.error("Failed to write cache %s: %s", path, e)
                # Clean up temp file on failure
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise

    def delete(self, key: CacheKey) -> bool:
        """Delete a cache entry.
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if deleted, False if didn't exist
        """
        path = self._get_cache_path(key)
        if path.exists():
            path.unlink()
            logger.debug("Cache deleted: %s", path)
            return True
        return False

    def invalidate(self, symbol: str, timeframe: str) -> int:
        """Invalidate all cache entries for a symbol/timeframe.
        
        Args:
            symbol: Trading symbol (e.g., "NSE:INFY")
            timeframe: Timeframe string (e.g., "1m", "1h", "1d")
            
        Returns:
            Number of files deleted
        """
        safe_symbol = symbol.replace(":", "_").replace("/", "_")
        cache_dir = self._base_dir / safe_symbol / timeframe
        
        if not cache_dir.exists():
            return 0

        count = 0
        for file_path in cache_dir.glob("*.feather"):
            try:
                file_path.unlink()
                count += 1
            except OSError as e:
                logger.warning("Failed to delete %s: %s", file_path, e)

        # Clean up empty directories
        try:
            cache_dir.rmdir()  # Only removes if empty
            symbol_dir = cache_dir.parent
            symbol_dir.rmdir()  # Only removes if empty
        except OSError:
            pass  # Directories not empty, that's fine

        logger.info("Invalidated %d cache files for %s/%s", count, symbol, timeframe)
        return count

    def clear(self) -> int:
        """Clear all cache entries.
        
        Returns:
            Number of files deleted
        """
        if not self._base_dir.exists():
            return 0

        count = 0
        for file_path in self._base_dir.rglob("*.feather"):
            try:
                file_path.unlink()
                count += 1
            except OSError as e:
                logger.warning("Failed to delete %s: %s", file_path, e)

        # Remove empty directories
        try:
            shutil.rmtree(self._base_dir, ignore_errors=True)
        except OSError:
            pass

        logger.info("Cleared %d cache files", count)
        return count

    def list_keys(self) -> list[CacheKey]:
        """List all cache keys in the cache.
        
        Returns:
            List of cache keys found
        """
        keys = []
        for file_path in self._base_dir.rglob("*.feather"):
            key = CacheKey.from_filename(file_path.name)
            if key:
                keys.append(key)
        return keys

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache stats
        """
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
        
        symbols = set()
        timeframes = set()
        for f in files:
            key = CacheKey.from_filename(f.name)
            if key:
                symbols.add(key.symbol)
                timeframes.add(str(key.timeframe))

        return {
            "base_dir": str(self._base_dir),
            "total_files": len(files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "symbols": len(symbols),
            "timeframes": len(timeframes),
        }