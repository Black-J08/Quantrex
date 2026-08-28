"""Instrument Master CSV handling for Dhan symbol resolution."""

import csv
import time
from pathlib import Path
from typing import Any

import httpx

from .config import DhanProviderConfig
from .exceptions import DhanInstrumentMasterError, DhanSymbolNotFoundError
from .models import InstrumentMasterRow


class InstrumentMaster:
    """Manages Dhan instrument master CSV for symbol-to-securityId resolution.

    Downloads the compact instrument master CSV from Dhan, caches it locally,
    and provides fast lookup from (exchange_segment, trading_symbol) to security_id.
    """

    # Dhan instrument master URLs
    COMPACT_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
    DETAILED_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"

    # Canonical column names used in Dhan's compact scrip-master CSV.
    # Reference: https://images.dhan.co/api-data/api-scrip-master.csv
    COMPACT_COLUMNS = [
        "SEM_EXM_EXCH_ID", "SEM_SEGMENT", "SEM_SMST_SECURITY_ID", "SEM_INSTRUMENT_NAME",
        "SEM_EXPIRY_CODE", "SEM_TRADING_SYMBOL", "SEM_LOT_UNITS", "SEM_CUSTOM_SYMBOL",
        "SEM_EXPIRY_DATE", "SEM_STRIKE_PRICE", "SEM_OPTION_TYPE", "SEM_TICK_SIZE",
        "SEM_EXPIRY_FLAG", "SEM_EXCH_INSTRUMENT_TYPE", "SEM_SERIES", "SM_SYMBOL_NAME",
    ]

    # Header aliases accepted by the parser, in priority order. The first
    # alias present in the CSV header is used. This makes the parser tolerant
    # of upstream schema renames (e.g. EXCH_ID -> SEM_EXM_EXCH_ID).
    _COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
        "exch_id": ("SEM_EXM_EXCH_ID", "EXCH_ID"),
        "segment": ("SEM_SEGMENT", "SEGMENT"),
        "security_id": ("SEM_SMST_SECURITY_ID", "SECURITY_ID"),
        "trading_symbol": ("SEM_TRADING_SYMBOL",),
    }

    def __init__(self, config: DhanProviderConfig) -> None:
        """Initialize instrument master manager.

        Args:
            config: Provider configuration containing cache settings.
        """
        self._config = config
        self._cache_file = config.cache_dir / "instrument_master.csv"
        self._lookup: dict[tuple[str, str], str] = {}  # (exchange_segment, trading_symbol) -> security_id
        self._loaded = False
        self._load_time: float | None = None

    def _is_cache_valid(self) -> bool:
        """Check if cached instrument master is still valid."""
        if not self._cache_file.exists():
            return False
        if self._load_time is None:
            return False
        age_hours = (time.time() - self._load_time) / 3600
        return age_hours < self._config.cache_ttl_hours

    def _download_csv(self, url: str) -> str:
        """Download CSV content from URL.

        Args:
            url: URL to download from.

        Returns:
            CSV content as string.

        Raises:
            DhanInstrumentMasterError: If download fails.
        """
        try:
            with httpx.Client(timeout=self._config.timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.text
        except httpx.HTTPError as e:
            raise DhanInstrumentMasterError(f"Failed to download instrument master from {url}: {e}") from e

    def _parse_csv(self, csv_content: str) -> dict[tuple[str, str], str]:
        """Parse CSV content and build lookup dictionary.

        Resolves the four required columns via ``_COLUMN_ALIASES`` so the parser
        keeps working if Dhan renames headers upstream. Raises
        ``DhanInstrumentMasterError`` if any required column is missing, since
        a silent empty lookup would otherwise surface as a misleading
        ``DhanSymbolNotFoundError`` for every symbol.

        Args:
            csv_content: Raw CSV content.

        Returns:
            Dictionary mapping (exchange_segment, trading_symbol) to security_id.

        Raises:
            DhanInstrumentMasterError: If required columns are missing from the
                header or no usable rows are found.
        """
        reader = csv.DictReader(csv_content.splitlines())
        fieldnames = reader.fieldnames or []

        resolved: dict[str, str] = {}
        missing: list[str] = []
        for key, aliases in self._COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in fieldnames:
                    resolved[key] = alias
                    break
            else:
                missing.append(f"{key} (tried: {', '.join(aliases)})")

        if missing:
            header_preview = ", ".join(fieldnames[:8]) + (
                "..." if len(fieldnames) > 8 else ""
            )
            raise DhanInstrumentMasterError(
                "Instrument master CSV is missing required columns: "
                f"{'; '.join(missing)}. Header was: [{header_preview}]. "
                "The Dhan scrip-master schema may have changed; please update "
                "_COLUMN_ALIASES in instrument_master.py."
            )

        lookup: dict[tuple[str, str], str] = {}
        for row in reader:
            try:
                exch_id = row.get(resolved["exch_id"], "").strip()
                segment = row.get(resolved["segment"], "").strip()
                security_id = row.get(resolved["security_id"], "").strip()
                trading_symbol = row.get(resolved["trading_symbol"], "").strip()

                if not all([exch_id, segment, security_id, trading_symbol]):
                    continue

                # Convert to our exchange_segment format
                exchange_segment = self._map_exchange_segment(exch_id, segment)
                if exchange_segment is None:
                    continue

                key = (exchange_segment, trading_symbol)
                lookup[key] = security_id

            except Exception:
                # Skip malformed rows
                continue

        if not lookup:
            raise DhanInstrumentMasterError(
                "Parsed instrument master CSV produced 0 usable rows. "
                "The Dhan scrip-master schema may have changed; please verify "
                "the file format and update _COLUMN_ALIASES in instrument_master.py."
            )

        return lookup

    def _map_exchange_segment(self, exch_id: str, segment: str) -> str | None:
        """Map Dhan's EXCH_ID and SEGMENT to our exchange_segment format.

        Args:
            exch_id: Exchange ID (NSE, BSE, MCX)
            segment: Segment code (E, D, C, M)

        Returns:
            Our exchange_segment format or None if unknown.
        """
        mapping = {
            ("NSE", "E"): "NSE_EQ",
            ("NSE", "D"): "NSE_FNO",
            ("NSE", "C"): "NSE_CURRENCY",
            ("BSE", "E"): "BSE_EQ",
            ("BSE", "D"): "BSE_FNO",
            ("BSE", "C"): "BSE_CURRENCY",
            ("MCX", "M"): "MCX_COMM",
        }
        return mapping.get((exch_id, segment))

    def load(self, force_refresh: bool = False) -> None:
        """Load instrument master from cache or download.

        Args:
            force_refresh: If True, bypass cache and download fresh.

        Raises:
            DhanInstrumentMasterError: If loading fails.
        """
        if not force_refresh and self._is_cache_valid() and self._loaded:
            return

        # Try to load from cache first
        if not force_refresh and self._cache_file.exists():
            try:
                csv_content = self._cache_file.read_text(encoding="utf-8")
                self._lookup = self._parse_csv(csv_content)
                self._loaded = True
                self._load_time = time.time()
                return
            except Exception:
                # Cache corrupted, will download fresh
                pass

        # Download fresh
        try:
            csv_content = self._download_csv(self.COMPACT_URL)
        except DhanInstrumentMasterError:
            # Try detailed URL as fallback
            try:
                csv_content = self._download_csv(self.DETAILED_URL)
            except DhanInstrumentMasterError as e:
                raise DhanInstrumentMasterError("Failed to download instrument master from both URLs") from e

        # Parse and cache
        self._lookup = self._parse_csv(csv_content)

        # Save to cache
        try:
            self._cache_file.write_text(csv_content, encoding="utf-8")
        except Exception:
            # Non-fatal: cache write failed but we have data in memory
            pass

        self._loaded = True
        self._load_time = time.time()

    def resolve_symbol(self, symbol: str, exchange_segment: str) -> str:
        """Resolve a trading symbol to security_id.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE").
            exchange_segment: Exchange segment (e.g., "NSE_EQ").

        Returns:
            Security ID as string.

        Raises:
            DhanSymbolNotFoundError: If symbol not found.
        """
        if not self._loaded:
            self.load()

        key = (exchange_segment, symbol)
        if key not in self._lookup:
            raise DhanSymbolNotFoundError(symbol=symbol, exchange_segment=exchange_segment)

        return self._lookup[key]

    def get_all_symbols(self, exchange_segment: str | None = None) -> list[str]:
        """Get all trading symbols, optionally filtered by exchange segment.

        Args:
            exchange_segment: Optional filter by exchange segment.

        Returns:
            List of trading symbols.
        """
        if not self._loaded:
            self.load()

        if exchange_segment is None:
            return list({k[1] for k in self._lookup.keys()})

        return [k[1] for k in self._lookup.keys() if k[0] == exchange_segment]

    def refresh(self) -> None:
        """Force refresh the instrument master from Dhan."""
        self.load(force_refresh=True)

    @property
    def is_loaded(self) -> bool:
        """Check if instrument master is loaded."""
        return self._loaded

    @property
    def cache_path(self) -> Path:
        """Get the cache file path."""
        return self._cache_file

    @property
    def symbol_count(self) -> int:
        """Get the number of symbols in the lookup."""
        return len(self._lookup)