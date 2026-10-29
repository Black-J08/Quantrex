"""Zerodha instrument master - manages instrument data lifecycle."""

from __future__ import annotations

import asyncio
import csv
import gzip
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiofiles

from quantrex.core.broker.exceptions.exceptions import (
    AmbiguousSymbolError,
    SymbolNotFoundError,
)
from quantrex.core.broker.zerodha.exceptions.exceptions import InstrumentMasterError
from quantrex.core.broker.zerodha.instrument_master.models import ZerodhaInstrument
from quantrex.core.broker.zerodha.session.session import ZerodhaSession
from quantrex.core.models.timezone import IST

logger = logging.getLogger(__name__)

# Constants
INSTRUMENTS_ENDPOINT = "/instruments"
DEFAULT_CACHE_DIR = Path.home() / ".quantrex" / "cache" / "zerodha"
CACHE_CSV_FILENAME = "instruments.csv"
CACHE_META_FILENAME = "metadata.json"
# 8:30 AM IST = 03:00 UTC (Kite generates instrument master daily around this time)
CACHE_EXPIRY_HOUR_IST = 8
CACHE_EXPIRY_MINUTE_IST = 30
# Owner read/write only for cache files containing instrument data
_CACHE_FILE_MODE = 0o600
# Seconds per hour, used for cache age calculation.
_SECONDS_PER_HOUR = 3600


@dataclass(slots=True)
class CacheMetadata:
    """Metadata for instrument master cache."""

    timestamp: str  # ISO format with timezone
    record_count: int
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "record_count": self.record_count,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheMetadata:
        return cls(
            timestamp=data["timestamp"],
            record_count=data["record_count"],
            version=data.get("version", 1),
        )

    def is_stale(self) -> bool:
        """Check if cache is stale (expired before today's 8:30 AM IST)."""
        cache_time = datetime.fromisoformat(self.timestamp)
        now = datetime.now(IST)

        # Calculate today's expiry time (8:30 AM IST)
        today_expiry = now.replace(hour=CACHE_EXPIRY_HOUR_IST, minute=CACHE_EXPIRY_MINUTE_IST, second=0, microsecond=0)

        # If it's before today's expiry, use yesterday's expiry
        if now < today_expiry:
            today_expiry = today_expiry - timedelta(days=1)

        # Cache is stale if it was created before the last expiry time
        return cache_time < today_expiry


class InstrumentMaster:
    """Manages Zerodha instrument master data with on-demand refresh.

    Features:
    - On-demand refresh when symbol not in cache or cache is stale
    - Atomic writes with corruption prevention
    - Thread-safe with asyncio.Lock for refresh, lock-free reads
    - Fail-open on stale cache (serve stale data with warning)
    - Reuses ZerodhaSession for auth and HTTP
    - Cache expires daily at 8:30 AM IST (03:00 UTC) when Kite generates new master
    """

    def __init__(
        self,
        session: ZerodhaSession,
        cache_dir: Path | str | None = None,
    ):
        """Initialize instrument master.

        Args:
            session: ZerodhaSession for authenticated requests
            cache_dir: Directory for cache files (default: ~/.quantrex/cache/zerodha/)
        """
        self._session = session
        self._cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR

        # Ensure cache directory exists
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Cache file paths
        self._csv_path = self._cache_dir / CACHE_CSV_FILENAME
        self._meta_path = self._cache_dir / CACHE_META_FILENAME

        # In-memory indices (built on load/refresh)
        self._exact_index: dict[str, ZerodhaInstrument] = {}  # "NSE:INFY" -> instrument
        self._tradingsymbol_index: dict[str, list[ZerodhaInstrument]] = {}  # "INFY" -> [instruments]
        self._metadata: CacheMetadata | None = None
        self._refresh_lock = asyncio.Lock()
        self._loaded = False

    async def resolve_symbol(self, symbol: str) -> ZerodhaInstrument:
        """Resolve a symbol to its instrument.

        Resolution order:
        1. Exact match on "EXCHANGE:TRADINGSYMBOL"
        2. Tradingsymbol-only match (if unique across exchanges)
        3. Raise SymbolNotFoundError or AmbiguousSymbolError

        Args:
            symbol: Symbol to resolve (e.g., "NSE:INFY" or "INFY")

        Returns:
            ZerodhaInstrument with token and metadata

        Raises:
            SymbolNotFoundError: If symbol not found
            AmbiguousSymbolError: If tradingsymbol matches multiple exchanges
        """
        # Ensure cache is loaded/refreshed
        await self._ensure_loaded()

        # Try exact match first (e.g., "NSE:INFY")
        if symbol in self._exact_index:
            return self._exact_index[symbol]

        # Try tradingsymbol-only match (e.g., "INFY")
        if symbol in self._tradingsymbol_index:
            candidates = self._tradingsymbol_index[symbol]
            if len(candidates) == 1:
                return candidates[0]
            # Ambiguous - multiple exchanges have this tradingsymbol
            raise AmbiguousSymbolError(symbol, candidates)

        # Not found - try to find suggestions
        suggestions = self._find_suggestions(symbol)
        raise SymbolNotFoundError(symbol, suggestions)

    def _find_suggestions(self, symbol: str, max_suggestions: int = 5) -> list[str]:
        """Find similar symbols for error suggestions."""
        suggestions = []
        symbol_upper = symbol.upper()

        # Check exact index for partial matches
        for key in self._exact_index:
            if symbol_upper in key.upper() or key.upper() in symbol_upper:
                suggestions.append(key)
                if len(suggestions) >= max_suggestions:
                    break

        # Check tradingsymbol index
        if len(suggestions) < max_suggestions:
            for key in self._tradingsymbol_index:
                if symbol_upper in key.upper() or key.upper() in symbol_upper:
                    suggestions.append(key)
                    if len(suggestions) >= max_suggestions:
                        break

        return suggestions[:max_suggestions]

    async def _ensure_loaded(self) -> None:
        """Ensure cache is loaded and fresh, refreshing if needed."""
        if not self._loaded:
            await self._load_cache()

        # Check if refresh needed (cache expires daily at 8:30 AM IST / 03:00 UTC)
        if self._metadata and self._metadata.is_stale():
            logger.info("Instrument master cache stale (expired before 8:30 AM IST), refreshing...")
            await self._refresh_if_needed()
        elif not self._metadata:
            logger.info("No instrument master cache found, refreshing...")
            await self._refresh_if_needed()

    async def _load_cache(self) -> None:
        """Load cache from disk and build indices."""
        if not self._csv_path.exists() or not self._meta_path.exists():
            logger.debug("Cache files not found: %s, %s", self._csv_path, self._meta_path)
            self._loaded = True
            return

        try:
            # Load metadata
            async with aiofiles.open(self._meta_path, "r") as f:
                meta_data = json.loads(await f.read())
            self._metadata = CacheMetadata.from_dict(meta_data)

            # Load CSV and build indices
            await self._parse_csv_and_build_indices()

            logger.info(
                "Loaded instrument master cache: %d instruments, cached at %s",
                self._metadata.record_count,
                self._metadata.timestamp,
            )
        except (json.JSONDecodeError, KeyError, ValueError, OSError) as e:
            logger.warning("Failed to load instrument master cache: %s", e)
            # Corrupted cache - will trigger refresh on next resolve
            self._metadata = None
            self._exact_index.clear()
            self._tradingsymbol_index.clear()

        self._loaded = True

    async def _parse_csv_and_build_indices(self) -> None:
        """Parse CSV file and build lookup indices."""
        self._exact_index.clear()
        self._tradingsymbol_index.clear()

        record_count = 0
        async with aiofiles.open(self._csv_path, "r", newline="", encoding="utf-8") as f:
            content = await f.read()
            reader = csv.DictReader(content.splitlines())
            for row in reader:
                try:
                    instrument = ZerodhaInstrument.from_csv_row(row)
                    if not instrument.tradingsymbol or not instrument.exchange:
                        continue

                    # Build exact index: "NSE:INFY" -> instrument
                    exact_key = instrument.symbol
                    self._exact_index[exact_key] = instrument

                    # Build tradingsymbol index: "INFY" -> [instruments]
                    ts_key = instrument.tradingsymbol
                    if ts_key not in self._tradingsymbol_index:
                        self._tradingsymbol_index[ts_key] = []
                    self._tradingsymbol_index[ts_key].append(instrument)

                    record_count += 1
                except (ValueError, KeyError) as e:
                    logger.warning("Skipping malformed CSV row: %s, error: %s", row, e)
                    continue

        # Update metadata record count
        if self._metadata:
            self._metadata.record_count = record_count

    async def _refresh_if_needed(self) -> None:
        """Refresh instrument master from API with double-checked locking."""
        async with self._refresh_lock:
            # Double-check: another request may have already refreshed
            if self._metadata and not self._metadata.is_stale():
                return

            await self._refresh()

    async def _refresh(self) -> None:
        """Download and cache the instrument master from Zerodha API."""
        logger.info("Starting instrument master refresh...")
        start_time = time.monotonic()

        try:
            # Fetch from API using ZerodhaSession (handles auth, rate limiting)
            response = await self._session.get(INSTRUMENTS_ENDPOINT)

            # Decompress gzip response
            content = response.content
            if response.headers.get("Content-Encoding") == "gzip":
                content = gzip.decompress(content)

            # Parse CSV and build indices in memory first
            new_exact_index: dict[str, ZerodhaInstrument] = {}
            new_tradingsymbol_index: dict[str, list[ZerodhaInstrument]] = {}
            record_count = 0

            csv_text = content.decode("utf-8")
            reader = csv.DictReader(csv_text.splitlines())
            for row in reader:
                try:
                    instrument = ZerodhaInstrument.from_csv_row(row)
                    if not instrument.tradingsymbol or not instrument.exchange:
                        continue

                    exact_key = instrument.symbol
                    new_exact_index[exact_key] = instrument

                    ts_key = instrument.tradingsymbol
                    if ts_key not in new_tradingsymbol_index:
                        new_tradingsymbol_index[ts_key] = []
                    new_tradingsymbol_index[ts_key].append(instrument)

                    record_count += 1
                except (ValueError, KeyError) as e:
                    logger.warning("Skipping malformed CSV row during refresh: %s, error: %s", row, e)
                    continue

            # Atomic write: write to temp files first, then rename
            temp_csv = self._csv_path.with_suffix(".csv.tmp")
            temp_meta = self._meta_path.with_suffix(".json.tmp")

            # Write CSV
            async with aiofiles.open(temp_csv, "w", newline="", encoding="utf-8") as f:
                await f.write(csv_text)

            # Write metadata (timestamp in IST)
            metadata = CacheMetadata(
                timestamp=datetime.now(IST).isoformat(),
                record_count=record_count,
            )
            async with aiofiles.open(temp_meta, "w") as f:
                await f.write(json.dumps(metadata.to_dict()))

            # Atomic rename
            os.replace(temp_csv, self._csv_path)
            os.replace(temp_meta, self._meta_path)

            # Set restrictive permissions (owner read/write only)
            os.chmod(self._csv_path, _CACHE_FILE_MODE)
            os.chmod(self._meta_path, _CACHE_FILE_MODE)

            # Swap indices (lock-free for readers)
            self._exact_index = new_exact_index
            self._tradingsymbol_index = new_tradingsymbol_index
            self._metadata = metadata

            elapsed = time.monotonic() - start_time
            logger.info(
                "Instrument master refresh completed: %d instruments in %.2fs",
                record_count,
                elapsed,
            )

        except Exception:
            logger.exception("Instrument master refresh failed")
            # Fail-open: keep stale cache if available, otherwise raise
            if not self._metadata:
                raise InstrumentMasterError("Failed to refresh instrument master and no cache available") from None
            logger.warning("Serving stale cache due to refresh failure")

    def is_fresh(self) -> bool:
        """Check if cache is fresh (not expired before today's 8:30 AM IST)."""
        if not self._metadata:
            return False
        return not self._metadata.is_stale()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "loaded": self._loaded,
            "record_count": self._metadata.record_count if self._metadata else 0,
            "cache_age_hours": (
                (datetime.now(IST) - datetime.fromisoformat(self._metadata.timestamp)).total_seconds()
                / _SECONDS_PER_HOUR
                if self._metadata
                else None
            ),
            "is_fresh": self.is_fresh(),
            "cache_dir": str(self._cache_dir),
        }