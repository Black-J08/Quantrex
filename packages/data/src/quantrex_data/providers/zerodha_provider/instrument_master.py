"""Instrument Master CSV handling for Zerodha symbol resolution."""

import csv
import time
from pathlib import Path
from typing import Any

import httpx

from quantrex_core.logging import get_logger

from .config import ZerodhaProviderConfig
from .exceptions import ZerodhaInstrumentMasterError, ZerodhaSymbolNotFoundError
from .models import InstrumentMasterRow

logger = get_logger(__name__)


class InstrumentMaster:
    """Manages Zerodha instrument master CSV for symbol-to-instrument_token resolution.

    Downloads the instrument master CSV from Zerodha, caches it locally,
    and provides fast lookup from (exchange, tradingsymbol) to instrument_token.
    """

    # Zerodha instrument master URLs
    INSTRUMENTS_URL = "https://api.kite.trade/instruments"
    INSTRUMENTS_EXCHANGE_URL = "https://api.kite.trade/instruments/{exchange}"

    # Canonical column names used in Zerodha's instrument master CSV.
    # Reference: https://api.kite.trade/instruments
    REQUIRED_COLUMNS = [
        "instrument_token",
        "exchange_token",
        "tradingsymbol",
        "name",
        "last_price",
        "expiry",
        "strike",
        "tick_size",
        "lot_size",
        "instrument_type",
        "segment",
        "exchange",
    ]

    # Header aliases accepted by the parser, in priority order.
    _COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
        "instrument_token": ("instrument_token",),
        "exchange_token": ("exchange_token",),
        "tradingsymbol": ("tradingsymbol",),
        "name": ("name",),
        "last_price": ("last_price",),
        "expiry": ("expiry",),
        "strike": ("strike",),
        "tick_size": ("tick_size",),
        "lot_size": ("lot_size",),
        "instrument_type": ("instrument_type",),
        "segment": ("segment",),
        "exchange": ("exchange",),
    }

    def __init__(self, config: ZerodhaProviderConfig, client: Any = None) -> None:
        """Initialize instrument master manager.

        Args:
            config: Provider configuration containing cache settings and auth.
            client: Optional ZerodhaAPIClient instance for authenticated requests.
                   If not provided, a temporary client will be created for downloads.
        """
        self._config = config
        self._client = client
        self._cache_file = config.cache_dir / "instrument_master.csv"
        self._lookup: dict[tuple[str, str], str] = {}  # (exchange, tradingsymbol) -> instrument_token
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

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers for API requests."""
        if not self._config.access_token:
            raise ZerodhaInstrumentMasterError("No access token available for instrument master download")
        return {
            "X-Kite-Version": "3",
            "Authorization": f"token {self._config.api_key}:{self._config.access_token}",
        }

    def _download_csv(self, exchange: str | None = None) -> str:
        """Download CSV content from Zerodha API.

        Args:
            exchange: Optional exchange to filter (e.g., "NSE", "NFO"). If None, downloads all.

        Returns:
            CSV content as string.

        Raises:
            ZerodhaInstrumentMasterError: If download fails.
        """
        if exchange:
            url = self.INSTRUMENTS_EXCHANGE_URL.format(exchange=exchange)
        else:
            url = self.INSTRUMENTS_URL

        headers = self._get_auth_headers()

        try:
            with httpx.Client(timeout=self._config.timeout) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                return response.text
        except httpx.HTTPError as e:
            raise ZerodhaInstrumentMasterError(f"Failed to download instrument master from {url}: {e}") from e

    def _parse_csv(self, csv_content: str) -> dict[tuple[str, str], str]:
        """Parse CSV content and build lookup dictionary.

        Resolves the required columns via ``_COLUMN_ALIASES`` so the parser
        keeps working if Zerodha renames headers upstream. Raises
        ``ZerodhaInstrumentMasterError`` if any required column is missing.

        Args:
            csv_content: Raw CSV content.

        Returns:
            Dictionary mapping (exchange, tradingsymbol) to instrument_token.
        """
        if not csv_content.strip():
            raise ZerodhaInstrumentMasterError("Empty instrument master CSV")

        reader = csv.DictReader(csv_content.splitlines())
        if not reader.fieldnames:
            raise ZerodhaInstrumentMasterError("CSV has no header row")

        # Resolve column indices using aliases
        column_indices: dict[str, int] = {}
        for canonical, aliases in self._COLUMN_ALIASES.items():
            found = False
            for alias in aliases:
                if alias in reader.fieldnames:
                    column_indices[canonical] = reader.fieldnames.index(alias)
                    found = True
                    break
            if not found:
                raise ZerodhaInstrumentMasterError(
                    f"Required column '{canonical}' not found in CSV. "
                    f"Available columns: {reader.fieldnames}. "
                    f"Aliases tried: {aliases}"
                )

        lookup: dict[tuple[str, str], str] = {}
        for row_num, row in enumerate(reader, start=2):  # 1-indexed, +1 for header
            try:
                instrument_token = row[reader.fieldnames[column_indices["instrument_token"]]]
                exchange = row[reader.fieldnames[column_indices["exchange"]]]
                tradingsymbol = row[reader.fieldnames[column_indices["tradingsymbol"]]]

                if instrument_token and exchange and tradingsymbol:
                    lookup[(exchange, tradingsymbol)] = instrument_token
            except (IndexError, KeyError) as e:
                logger.warning("Skipping malformed row %d in instrument master: %s", row_num, e)
                continue

        logger.debug("Parsed instrument master: %d entries", len(lookup))
        return lookup

    def load(self, exchange: str | None = None) -> None:
        """Load instrument master from cache or download.

        Args:
            exchange: Optional exchange to filter. If None, loads all exchanges.
        """
        if self._loaded and self._is_cache_valid():
            logger.debug("Using cached instrument master (age < %d hours)", self._config.cache_ttl_hours)
            return

        # Try to load from cache first
        if self._cache_file.exists() and self._is_cache_valid():
            try:
                csv_content = self._cache_file.read_text(encoding="utf-8")
                self._lookup = self._parse_csv(csv_content)
                self._loaded = True
                self._load_time = time.time()
                logger.debug("Loaded instrument master from cache: %d entries", len(self._lookup))
                return
            except Exception as e:
                logger.warning("Failed to load cached instrument master: %s", e)

        # Download fresh
        logger.info("Downloading instrument master from Zerodha (exchange=%s)...", exchange or "all")
        csv_content = self._download_csv(exchange)

        # Save to cache
        try:
            self._cache_file.write_text(csv_content, encoding="utf-8")
            logger.debug("Saved instrument master to cache: %s", self._cache_file)
        except Exception as e:
            logger.warning("Failed to save instrument master cache: %s", e)

        # Parse and build lookup
        self._lookup = self._parse_csv(csv_content)
        self._loaded = True
        self._load_time = time.time()
        logger.info("Instrument master loaded: %d entries", len(self._lookup))

    def resolve_symbol(self, symbol: str, exchange: str | None = None) -> str:
        """Resolve trading symbol to instrument_token.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE").
            exchange: Exchange segment (e.g., "NSE"). If None, uses config's exchange.

        Returns:
            Instrument token as string.

        Raises:
            ZerodhaSymbolNotFoundError: If symbol not found.
        """
        if not self._loaded:
            self.load(exchange)

        target_exchange = exchange or self._config.exchange
        key = (target_exchange, symbol)

        if key not in self._lookup:
            # Try case-insensitive lookup
            for (exch, sym), token in self._lookup.items():
                if exch.upper() == target_exchange.upper() and sym.upper() == symbol.upper():
                    logger.debug("Resolved '%s' -> instrument_token='%s' (case-insensitive)", symbol, token)
                    return token

            raise ZerodhaSymbolNotFoundError(
                f"Symbol '{symbol}' not found in exchange '{target_exchange}'",
                symbol=symbol,
                exchange=target_exchange,
            )

        token = self._lookup[key]
        logger.debug("Resolved '%s' -> instrument_token='%s'", symbol, token)
        return token

    def get_instrument_token(self, symbol: str, exchange: str | None = None) -> str:
        """Alias for resolve_symbol for clarity."""
        return self.resolve_symbol(symbol, exchange)

    @property
    def is_loaded(self) -> bool:
        """Check if instrument master is loaded."""
        return self._loaded

    @property
    def entry_count(self) -> int:
        """Get number of entries in lookup."""
        return len(self._lookup)