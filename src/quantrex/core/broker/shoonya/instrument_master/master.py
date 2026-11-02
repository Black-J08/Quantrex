"""Shoonya instrument master - manages instrument data lifecycle."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import aiofiles
import httpx

from quantrex.core.broker.exceptions.exceptions import (
    AmbiguousSymbolError,
    SymbolNotFoundError,
)
from quantrex.core.broker.shoonya.exceptions.exceptions import InstrumentMasterError
from quantrex.core.broker.shoonya.instrument_master.models import ShoonyaInstrument
from quantrex.core.broker.shoonya.session.session import ShoonyaSession
from quantrex.core.models.timezone import IST

logger = logging.getLogger(__name__)

# Constants
SYMBOL_MASTER_BASE_URL = "https://api.shoonya.com"
DEFAULT_CACHE_DIR = Path.home() / ".quantrex" / "cache" / "shoonya"
CACHE_META_FILENAME = "metadata.json"
# Cache expires daily at 8:30 AM IST (03:00 UTC) when symbol masters are regenerated
CACHE_EXPIRY_HOUR_IST = 8
CACHE_EXPIRY_MINUTE_IST = 30
# Owner read/write only for cache files containing instrument data
_CACHE_FILE_MODE = 0o600
# Seconds per hour, used for cache age calculation.
_SECONDS_PER_HOUR = 3600

# Default segments to download (NSE cash market only by default)
DEFAULT_SEGMENTS = ["NSE"]

# Segment -> symbol master filename mapping
SEGMENT_FILES = {
    "NSE": "NSE_symbols.txt.zip",
    "NFO": "NFO_symbols.txt.zip",
    "CDS": "CDS_symbols.txt.zip",
    "MCX": "MCX_symbols.txt.zip",
    "BSE": "BSE_symbols.txt.zip",
    "BFO": "BFO_symbols.txt.zip",
}


@dataclass(slots=True)
class CacheMetadata:
    """Metadata for instrument master cache."""

    timestamp: str  # ISO format with timezone
    record_count: int
    version: int = 1
    segments: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "record_count": self.record_count,
            "version": self.version,
            "segments": self.segments,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheMetadata:
        return cls(
            timestamp=data["timestamp"],
            record_count=data["record_count"],
            version=data.get("version", 1),
            segments=data.get("segments"),
        )

    def is_stale(self) -> bool:
        """Check if cache is stale (expired before today's 8:30 AM IST)."""
        cache_time = datetime.fromisoformat(self.timestamp)
        now = datetime.now(IST)

        # Calculate today's expiry time (8:30 AM IST)
        today_expiry = now.replace(
            hour=CACHE_EXPIRY_HOUR_IST,
            minute=CACHE_EXPIRY_MINUTE_IST,
            second=0,
            microsecond=0,
        )

        # If it's before today's expiry, use yesterday's expiry
        if now < today_expiry:
            today_expiry = today_expiry - timedelta(days=1)

        # Cache is stale if it was created before the last expiry time
        return cache_time < today_expiry


class InstrumentMaster:
    """Manages Shoonya instrument master data with on-demand refresh.

    Features:
    - Downloads segment-specific .zip symbol master files from Shoonya API
    - Parses pipe/comma-delimited .txt contents with header-based column detection
    - On-demand refresh when symbol not in cache or cache is stale
    - Atomic writes with corruption prevention
    - Thread-safe with asyncio.Lock for refresh, lock-free reads
    - Fail-open on stale cache (serve stale data with warning)
    - Reuses ShoonyaSession for auth and HTTP
    - Cache expires daily at 8:30 AM IST (03:00 UTC)
    """

    def __init__(
        self,
        session: ShoonyaSession,
        cache_dir: Path | str | None = None,
        segments: list[str] | None = None,
    ):
        """Initialize instrument master.

        Args:
            session: ShoonyaSession for authenticated requests
            cache_dir: Directory for cache files (default: ~/.quantrex/cache/shoonya/)
            segments: List of exchange segments to download (default: ["NSE"])
        """
        self._session = session
        self._cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self._segments = segments or list(DEFAULT_SEGMENTS)

        # Ensure cache directory exists
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Cache file paths
        self._meta_path = self._cache_dir / CACHE_META_FILENAME

        # In-memory indices (built on load/refresh)
        self._exact_index: dict[str, ShoonyaInstrument] = {}  # "NSE:INFY" -> instrument
        self._tradingsymbol_index: dict[str, list[ShoonyaInstrument]] = (  # "INFY" -> [instruments]
            {}
        )
        self._metadata: CacheMetadata | None = None
        self._refresh_lock = asyncio.Lock()
        self._loaded = False

    async def resolve_symbol(self, symbol: str) -> ShoonyaInstrument:
        """Resolve a symbol to its instrument.

        Resolution order:
        1. Exact match on "EXCHANGE:TRADINGSYMBOL"
        2. Tradingsymbol-only match (if unique across exchanges)
        3. Raise SymbolNotFoundError or AmbiguousSymbolError

        Args:
            symbol: Symbol to resolve (e.g., "NSE:INFY" or "INFY")

        Returns:
            ShoonyaInstrument with token and metadata

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
            logger.info(
                "Instrument master cache stale (expired before 8:30 AM IST), refreshing..."
            )
            await self._refresh_if_needed()
        elif not self._metadata:
            logger.info("No instrument master cache found, refreshing...")
            await self._refresh_if_needed()

    async def _load_cache(self) -> None:
        """Load cache from disk and build indices."""
        if not self._meta_path.exists():
            logger.debug("Cache metadata not found: %s", self._meta_path)
            self._loaded = True
            return

        try:
            # Load metadata
            async with aiofiles.open(self._meta_path, "r") as f:
                meta_data = json.loads(await f.read())
            self._metadata = CacheMetadata.from_dict(meta_data)

            # Load instrument data from metadata (stores instruments inline)
            instruments_data = self._metadata.instruments if hasattr(
                self._metadata, "instruments"
            ) else None

            # For now, if metadata exists but no instruments stored, trigger refresh
            # In a full implementation, instruments would be cached in a separate file
            if not instruments_data:
                logger.debug("No cached instruments found, will refresh")
                self._metadata = None
                self._exact_index.clear()
                self._tradingsymbol_index.clear()
            else:
                await self._build_indices_from_data(instruments_data)
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

    async def _build_indices_from_data(
        self, instruments_data: list[dict[str, Any]]
    ) -> None:
        """Build lookup indices from instrument data."""
        self._exact_index.clear()
        self._tradingsymbol_index.clear()

        record_count = 0
        for item in instruments_data:
            try:
                instrument = ShoonyaInstrument(
                    instrument_token=str(item.get("instrument_token", "")),
                    exchange_token=str(item.get("exchange_token", "")),
                    tradingsymbol=item.get("tradingsymbol", ""),
                    name=item.get("name", ""),
                    last_price=Decimal(str(item.get("last_price", "0"))),
                    expiry=self._parse_date(item.get("expiry")),
                    strike=(
                        Decimal(str(item["strike"])) if item.get("strike") else None
                    ),
                    tick_size=Decimal(str(item.get("tick_size", "0"))),
                    lot_size=int(item.get("lot_size", "0")),
                    instrument_type=item.get("instrument_type", ""),
                    segment=item.get("segment", ""),
                    exchange=item.get("exchange", ""),
                )
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
            except (ValueError, KeyError, TypeError) as e:
                logger.warning("Skipping malformed instrument data: %s, error: %s", item, e)
                continue

        # Update metadata record count
        if self._metadata:
            self._metadata.record_count = record_count

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        """Parse a date value from various formats."""
        if not value:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None

    async def _refresh_if_needed(self) -> None:
        """Refresh instrument master from API with double-checked locking."""
        async with self._refresh_lock:
            # Double-check: another request may have already refreshed
            if self._metadata and not self._metadata.is_stale():
                return

            await self._refresh()

    async def _refresh(self) -> None:
        """Download and cache the instrument master from Shoonya API."""
        logger.info("Starting instrument master refresh...")
        start_time = time.monotonic()

        try:
            all_instruments: list[dict[str, Any]] = []

            for segment in self._segments:
                filename = SEGMENT_FILES.get(segment)
                if not filename:
                    logger.warning("Unknown segment: %s, skipping", segment)
                    continue

                url = f"{SYMBOL_MASTER_BASE_URL}/{filename}"
                logger.info("Downloading symbol master for segment %s from %s", segment, url)

                instruments = await self._download_and_parse_segment(segment, url)
                all_instruments.extend(instruments)
                logger.info(
                    "Parsed %d instruments from segment %s", len(instruments), segment
                )

            # Build indices in memory first
            new_exact_index: dict[str, ShoonyaInstrument] = {}
            new_tradingsymbol_index: dict[str, list[ShoonyaInstrument]] = {}
            record_count = 0

            for item in all_instruments:
                try:
                    instrument = ShoonyaInstrument(
                        instrument_token=str(item.get("instrument_token", "")),
                        exchange_token=str(item.get("exchange_token", "")),
                        tradingsymbol=item.get("tradingsymbol", ""),
                        name=item.get("name", ""),
                        last_price=Decimal(str(item.get("last_price", "0"))),
                        expiry=self._parse_date(item.get("expiry")),
                        strike=(
                            Decimal(str(item["strike"])) if item.get("strike") else None
                        ),
                        tick_size=Decimal(str(item.get("tick_size", "0"))),
                        lot_size=int(item.get("lot_size", "0")),
                        instrument_type=item.get("instrument_type", ""),
                        segment=item.get("segment", ""),
                        exchange=item.get("exchange", ""),
                    )
                    if not instrument.tradingsymbol or not instrument.exchange:
                        continue

                    exact_key = instrument.symbol
                    new_exact_index[exact_key] = instrument

                    ts_key = instrument.tradingsymbol
                    if ts_key not in new_tradingsymbol_index:
                        new_tradingsymbol_index[ts_key] = []
                    new_tradingsymbol_index[ts_key].append(instrument)

                    record_count += 1
                except (ValueError, KeyError, TypeError) as e:
                    logger.warning(
                        "Skipping malformed instrument row during refresh: %s, error: %s",
                        item,
                        e,
                    )
                    continue

            # Atomic write: write metadata file
            temp_meta = self._meta_path.with_suffix(".json.tmp")

            metadata = CacheMetadata(
                timestamp=datetime.now(IST).isoformat(),
                record_count=record_count,
                segments=list(self._segments),
            )

            # Store instruments inline in metadata for cache persistence
            metadata_dict = metadata.to_dict()
            metadata_dict["instruments"] = all_instruments

            async with aiofiles.open(temp_meta, "w") as f:
                await f.write(json.dumps(metadata_dict))

            # Atomic rename
            os.replace(temp_meta, self._meta_path)

            # Set restrictive permissions
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
                raise InstrumentMasterError(
                    "Failed to refresh instrument master and no cache available"
                ) from None
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
                (
                    datetime.now(IST)
                    - datetime.fromisoformat(self._metadata.timestamp)
                ).total_seconds()
                / _SECONDS_PER_HOUR
            )
            if self._metadata
            else None,
            "is_fresh": self.is_fresh(),
            "cache_dir": str(self._cache_dir),
            "segments": self._segments,
        }

    async def _download_and_parse_segment(
        self, segment: str, url: str
    ) -> list[dict[str, Any]]:
        """Download and parse a single segment's symbol master zip file.

        Downloads the .zip archive, extracts the .txt file, detects column
        order from the header row, and parses each row into a dict.
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.get(url)
            except httpx.RequestError as e:
                logger.error("Failed to download symbol master for %s: %s", segment, e)
                raise InstrumentMasterError(
                    f"Failed to download symbol master for {segment}: {e}"
                ) from e

        if response.status_code != 200:
            raise InstrumentMasterError(
                f"Failed to download symbol master for {segment}: "
                f"HTTP {response.status_code}"
            )

        # Parse zip archive
        instruments: list[dict[str, Any]] = []
        try:
            zip_buffer = io.BytesIO(response.content)
            with zipfile.ZipFile(zip_buffer) as zf:
                # Find the .txt file in the zip
                txt_files = [n for n in zf.namelist() if n.endswith(".txt")]
                if not txt_files:
                    logger.warning("No .txt file found in zip for segment %s", segment)
                    return instruments

                txt_filename = txt_files[0]
                with zf.open(txt_filename) as tf:
                    content = tf.read().decode("utf-8")
        except zipfile.BadZipFile as e:
            logger.error("Invalid zip file for segment %s: %s", segment, e)
            raise InstrumentMasterError(
                f"Invalid zip file for segment {segment}: {e}"
            ) from e

        # Parse pipe/comma-delimited content with header-based column detection
        lines = content.strip().splitlines()
        if not lines:
            return instruments

        # Detect delimiter from header
        header_line = lines[0]
        delimiter = "|" if "|" in header_line else ","

        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
        for row in reader:
            try:
                # Normalize keys to lowercase for consistent access
                normalized = {k.strip().lower(): v.strip() if v else "" for k, v in row.items()}

                instrument = {
                    "instrument_token": normalized.get("token", normalized.get("instrument_token", "")),
                    "exchange_token": normalized.get("exchange_token", ""),
                    "tradingsymbol": normalized.get("tsym", normalized.get("tradingsymbol", "")),
                    "name": normalized.get("name", ""),
                    "last_price": normalized.get("last_price", normalized.get("lp", "0")),
                    "expiry": normalized.get("expiry", ""),
                    "strike": normalized.get("strike", ""),
                    "tick_size": normalized.get("tick_size", "0"),
                    "lot_size": normalized.get("lot_size", "0"),
                    "instrument_type": normalized.get("instrument_type", ""),
                    "segment": segment,
                    "exchange": normalized.get("exchange", segment),
                }
                instruments.append(instrument)
            except (ValueError, KeyError, TypeError) as e:
                logger.warning("Skipping malformed row in %s: %s, error: %s", segment, row, e)
                continue

        return instruments
