"""Zerodha Data Provider for Quantrex framework.

Fetches raw OHLCV data from Zerodha Kite Connect REST API with symbol resolution,
date normalization, automatic chunking, and transparent caching.
"""

import time
from datetime import date, datetime, time as dt_time
from pathlib import Path
from typing import Any

from quantrex_core.logging import get_logger
from quantrex_core.protocols import DataProvider
from quantrex_core.timeframe.provider_mapping import ZERODHA_MAPPER
from quantrex_data.operations import ArrowCache

from .auth import ZerodhaAuth
from .client import ZerodhaAPIClient
from .config import ZerodhaProviderConfig
from .exceptions import (
    ZerodhaAuthenticationError,
    ZerodhaDataNotFoundError,
    ZerodhaInstrumentMasterError,
    ZerodhaRateLimitError,
    ZerodhaSymbolNotFoundError,
)
from .instrument_master import InstrumentMaster
from .models import HistoricalDataResponse

logger = get_logger(__name__)


class ZerodhaDataProvider:
    """Data provider for fetching OHLCV data from Zerodha Kite Connect API.

    Implements the DataProvider protocol. Handles:
    - Symbol resolution via instrument master CSV
    - Date normalization (date/datetime/str -> Zerodha format)
    - Automatic chunking for large date ranges
    - Credential loading from .env file
    - Automatic login/authentication flow
    - Rate limiting and retry logic

    Example:
        >>> provider = ZerodhaDataProvider(
        ...     symbol="RELIANCE",
        ...     exchange="NSE",
        ...     from_date="2024-01-01",
        ...     to_date="2024-01-31"
        ... )
        >>> data = provider.fetch()
        >>> provider.close()
    """

    # Default chunk sizes per interval (days per request)
    # Conservative limits based on Zerodha's typical restrictions
    DEFAULT_CHUNK_SIZES = {
        "minute": 30,
        "3minute": 30,
        "5minute": 30,
        "10minute": 30,
        "15minute": 30,
        "30minute": 30,
        "60minute": 60,
        "day": 500,
    }

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        access_token: str | None = None,
        token_file: str | Path | None = None,
        symbol: str | None = None,
        instrument_token: str | None = None,
        exchange_segment: str = "",
        from_date: date | datetime | str | None = None,
        to_date: date | datetime | str | None = None,
        interval: str = "day",
        continuous: bool = False,
        oi: bool = False,
        base_url: str = "https://api.kite.trade",
        timeout: float = 30.0,
        max_retries: int = 3,
        chunk_size_days: dict[str, int] | None = None,
        cache_dir: str | Path | None = None,
        cache_ttl_hours: int = 24,
    ) -> None:
        """Initialize Zerodha data provider.

        Args:
            api_key: Zerodha API key. If None, loads from ZERODHA_API_KEY env var.
            api_secret: Zerodha API secret. If None, loads from ZERODHA_API_SECRET env var.
            access_token: Access token. If None, loads from token_file or triggers login flow.
            token_file: Path to access token file. Default: ~/.quantrex/zerodha/access_token
            symbol: User-friendly trading symbol (e.g., "RELIANCE"). Mutually exclusive with instrument_token.
            instrument_token: Zerodha's numeric instrument token (e.g., "408065"). Mutually exclusive with symbol.
            exchange: Exchange segment (NSE, NFO, BSE, BFO, CDS, MCX, BCD, MF).
            from_date: Optional start date (date, datetime, or str in YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
                      If not provided, must be passed to fetch() at runtime.
            to_date: Optional end date (date, datetime, or str in YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
                    If not provided, must be passed to fetch() at runtime.
            interval: Data interval (minute, 3minute, 5minute, 10minute, 15minute, 30minute, 60minute, day).
            continuous: Whether to get continuous data for futures (default: False).
            oi: Include open interest data (default: False).
            base_url: API base URL (default: https://api.kite.trade).
            timeout: Request timeout in seconds (default: 30.0).
            max_retries: Maximum retry attempts (default: 3).
            chunk_size_days: Custom chunk sizes per interval (days per request).
            cache_dir: Directory for caching instrument master CSV.
            cache_ttl_hours: Cache TTL for instrument master in hours (default: 24).

        Raises:
            ValueError: If configuration is invalid.
        """
        # Merge default chunk sizes with user-provided ones
        merged_chunk_sizes = {**self.DEFAULT_CHUNK_SIZES, **(chunk_size_days or {})}

        # Create config object (validates all inputs)
        self._config = ZerodhaProviderConfig(
            api_key=api_key,
            api_secret=api_secret,
            access_token=access_token,
            token_file=token_file,
            symbol=symbol,
            instrument_token=instrument_token,
            exchange=exchange_segment,
            from_date=from_date,
            to_date=to_date,
            interval=interval,
            continuous=continuous,
            oi=oi,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            chunk_size_days=merged_chunk_sizes,
            cache_dir=cache_dir,
            cache_ttl_hours=cache_ttl_hours,
        )

        # Initialize components
        self._client = ZerodhaAPIClient(self._config)
        self._instrument_master = InstrumentMaster(self._config, self._client)

        # Initialize automatic cache (zero-config, internal)
        self._cache = ArrowCache()

        # Ensure we have a valid token before resolving symbols or downloading instrument master
        self._ensure_valid_token()

        # Update config with the valid access token so InstrumentMaster can use it
        object.__setattr__(self._config, "access_token", self._client._access_token)

        # Resolve symbol to instrument_token if needed
        self._instrument_token = self._config.instrument_token
        if self._config.symbol is not None:
            self._instrument_token = self._resolve_symbol(self._config.symbol)

        logger.debug(
            "ZerodhaDataProvider initialized: symbol=%s, instrument_token=%s, exchange=%s, interval=%s",
            self._config.symbol,
            self._instrument_token,
            self._config.exchange,
            self._config.interval,
        )

    @property
    def instrument_token(self) -> str:
        """Get the resolved instrument token."""
        return self._instrument_token

    @property
    def config(self) -> ZerodhaProviderConfig:
        """Get the provider configuration."""
        return self._config

    def _resolve_symbol(self, symbol: str) -> str:
        """Resolve trading symbol to instrument_token using instrument master.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE").

        Returns:
            Instrument token as string.

        Raises:
            ZerodhaSymbolNotFoundError: If symbol not found.
        """
        logger.debug("Resolving symbol '%s' for exchange '%s'", symbol, self._config.exchange)
        instrument_token = self._instrument_master.resolve_symbol(symbol, self._config.exchange)
        logger.debug("Resolved '%s' -> instrument_token='%s'", symbol, instrument_token)
        return instrument_token

    def _ensure_valid_token(self) -> None:
        """Ensure we have a valid access token, triggering login flow if needed.

        This method uses ZerodhaAuth to validate the token and run the login flow if needed.
        """
        auth = ZerodhaAuth(self._config)
        try:
            access_token = auth.ensure_valid_token(self._client)
            # Update client with the valid token
            self._client.update_access_token(access_token)
        except ZerodhaAuthenticationError:
            # Re-raise with context
            raise
        except Exception as e:
            raise ZerodhaAuthenticationError(f"Authentication failed: {e}") from e

    def _trigger_login_flow(self) -> None:
        """Trigger the Zerodha login flow to obtain a new access token.

        This method is kept for backward compatibility but delegates to ZerodhaAuth.
        """
        auth = ZerodhaAuth(self._config)
        access_token = auth.run_login_flow(self._client)
        # Update client with the new token
        self._client.update_access_token(access_token)

    def _normalize_date_for_api(self, value: str) -> str:
        """Normalize stored date string to Zerodha API format (YYYY-MM-DD HH:MM:SS).

        Args:
            value: Date string from config.

        Returns:
            Date string in Zerodha API format.
        """
        # If already has time component, use as-is
        if " " in value:
            return value

        # For date-only, assume market open for intraday, or just date for daily
        if self._config.interval == "day":
            return value  # Zerodha daily API accepts YYYY-MM-DD
        return value + " 09:15:00"

    def _chunk_date_range(self, from_date: str, to_date: str, interval: str | None = None) -> list[tuple[str, str]]:
        """Split date range into API-compliant chunks.

        Args:
            from_date: Start date string (YYYY-MM-DD HH:MM:SS).
            to_date: End date string (YYYY-MM-DD HH:MM:SS).
            interval: The interval being fetched (uses config default if None).

        Returns:
            List of (chunk_from, chunk_to) date tuples.
        """
        # Parse dates
        if " " in from_date:
            start = datetime.strptime(from_date, "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(to_date, "%Y-%m-%d %H:%M:%S")
            fmt = "%Y-%m-%d %H:%M:%S"
        else:
            start = datetime.strptime(from_date, "%Y-%m-%d")
            end = datetime.strptime(to_date, "%Y-%m-%d")
            fmt = "%Y-%m-%d"

        # Use provided interval or fall back to config default
        effective_interval = interval or self._config.interval
        chunk_days = self._config.chunk_size_days.get(effective_interval, 30)

        if start >= end:
            # Same-day or invalid range
            return [(start.strftime(fmt), end.strftime(fmt))]

        chunks: list[tuple[str, str]] = []
        current_start = start

        while current_start < end:
            stride_end = current_start + __import__("datetime").timedelta(days=chunk_days)
            next_start = stride_end + __import__("datetime").timedelta(days=1)

            if stride_end >= end:
                current_end = end
            elif next_start >= end:
                current_end = end
            else:
                current_end = stride_end

            chunks.append((current_start.strftime(fmt), current_end.strftime(fmt)))

            if current_end >= end:
                break
            current_start = current_end + __import__("datetime").timedelta(days=1)

        logger.debug("Split date range into %d chunks for interval '%s'", len(chunks), self._config.interval)
        return chunks

    def _merge_responses(self, responses: list[HistoricalDataResponse]) -> dict:
        """Merge multiple chunked responses into single response dict.

        Args:
            responses: List of response objects.

        Returns:
            Merged response as dictionary with combined candles array.
        """
        if not responses:
            return {"candles": []}

        if len(responses) == 1:
            return {"candles": responses[0].get_candles()}

        merged_candles = []
        for resp in responses:
            merged_candles.extend(resp.get_candles())

        logger.debug("Merged %d chunks into %d candles", len(responses), len(merged_candles))
        return {"candles": merged_candles}

    def _fetch_from_api(self, interval: str, from_date: str | None = None, to_date: str | None = None) -> dict:
        """Internal method to fetch raw data from Zerodha API.

        Args:
            interval: Interval in Zerodha format (e.g., "minute", "day")
            from_date: Optional override for start date (API format)
            to_date: Optional override for end date (API format)

        Returns:
            Raw API response as dictionary.
        """
        # Ensure we have a valid token before making requests
        self._ensure_valid_token()

        # Use provided dates or fall back to config
        api_from_date = from_date or self._normalize_date_for_api(self._config.from_date)
        api_to_date = to_date or self._normalize_date_for_api(self._config.to_date)

        logger.info(
            "Fetching %s data from API for instrument_token='%s' from %s to %s",
            interval,
            self._instrument_token,
            api_from_date,
            api_to_date,
        )

        # Chunk date range using the effective interval
        chunks = self._chunk_date_range(api_from_date, api_to_date, interval)

        responses = []
        for i, (chunk_from, chunk_to) in enumerate(chunks):
            logger.debug("Fetching chunk %d/%d: %s to %s", i + 1, len(chunks), chunk_from, chunk_to)

            try:
                response = self._client.get_historical_data(
                    instrument_token=self._instrument_token,
                    interval=interval,
                    from_date=chunk_from,
                    to_date=chunk_to,
                    continuous=self._config.continuous,
                    oi=self._config.oi,
                )
                responses.append(response)
            except ZerodhaAuthenticationError:
                # Token expired during chunked requests - trigger login flow and retry
                logger.warning("Authentication error during chunked fetch, re-authenticating...")
                self._trigger_login_flow()
                # Retry the same chunk
                response = self._client.get_historical_data(
                    instrument_token=self._instrument_token,
                    interval=interval,
                    from_date=chunk_from,
                    to_date=chunk_to,
                    continuous=self._config.continuous,
                    oi=self._config.oi,
                )
                responses.append(response)

        # Merge all chunked responses
        merged = self._merge_responses(responses)

        logger.info("Fetched %d candles from API for instrument_token='%s'", len(merged.get("candles", [])), self._instrument_token)
        return merged

    def _format_cached_response(self, rows: list[dict]) -> dict:
        """Convert cached rows back to provider response format."""
        if not rows:
            return {"candles": []}

        candles = []
        for row in rows:
            dt_str = row.get("datetime", "")
            # Zerodha expects ISO format with timezone
            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                iso_str = dt.strftime("%Y-%m-%dT%H:%M:%S+0530")
            except Exception:
                iso_str = dt_str

            candle = [
                iso_str,
                row.get("open", 0.0),
                row.get("high", 0.0),
                row.get("low", 0.0),
                row.get("close", 0.0),
                row.get("volume", 0.0),
            ]
            if "oi" in row and row["oi"] is not None:
                candle.append(row["oi"])
            candles.append(candle)

        return {"candles": candles}

    def _response_to_rows(self, response: dict, symbol: str, interval: str, provider: str) -> list[dict]:
        """Convert provider response dict to list of row dicts for caching."""
        candles = response.get("candles", [])
        if not candles:
            return []

        rows = []
        for candle in candles:
            if len(candle) < 6:
                continue

            # Parse timestamp - Zerodha returns ISO 8601 with offset
            timestamp_str = candle[0]
            try:
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                dt_str = ""

            row = {
                "datetime": dt_str,
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]),
            }
            if len(candle) > 6 and candle[6] is not None:
                row["oi"] = float(candle[6])
            rows.append(row)

        return rows

    def fetch(
        self,
        interval: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        """Fetch raw OHLCV data with transparent caching.

        Implements read-through caching:
        1. Try cache for exact date range
        2. Try delta fetch for current partition
        3. Fall back to full API fetch
        4. Cache errors never break data flow — always fall back to API

        Args:
            interval: Interval (e.g., "minute", "5minute", "15minute", "day").
                      None uses the provider's configured interval.
            from_date: Optional start date override (ISO format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS").
                      If provided, overrides the provider's configured from_date.
            to_date: Optional end date override (ISO format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS").
                    If provided, overrides the provider's configured to_date.

        Returns:
            Raw API response as dictionary with key 'candles' containing
            list of [timestamp, open, high, low, close, volume, oi?] arrays.

        Raises:
            ZerodhaSymbolNotFoundError: If symbol resolution fails.
            ZerodhaAuthenticationError: If authentication fails.
            ZerodhaRateLimitError: If rate limit exceeded.
            ZerodhaDataNotFoundError: If no data returned.
            ZerodhaInvalidParameterError: If request parameters invalid.
            ZerodhaAPIError: Other API errors.
        """
        effective_interval = interval or self._config.interval
        provider_name = "zerodha"
        symbol = self._config.symbol or self._instrument_token

        # Determine effective dates: use overrides if provided, else config
        effective_from_date = from_date or self._config.from_date
        effective_to_date = to_date or self._config.to_date

        # If dates are not configured and not overridden, we can't use cache
        if effective_from_date is None or effective_to_date is None:
            logger.warning("Date range not configured; skipping cache and fetching from API")
            return self._fetch_from_api(effective_interval, from_date, to_date)

        # Parse config dates for cache operations
        try:
            start_dt = datetime.strptime(effective_from_date.split(" ")[0], "%Y-%m-%d")
            end_dt = datetime.strptime(effective_to_date.split(" ")[0], "%Y-%m-%d")
        except Exception:
            # If date parsing fails, skip cache and go straight to API
            logger.warning("Failed to parse dates for caching, falling back to API")
            return self._fetch_from_api(effective_interval, from_date, to_date)

        # 1. Try cache for exact date range (closed partition)
        try:
            cached = self._cache.load_partition(
                provider=provider_name,
                symbol=symbol,
                timeframe=effective_interval,
                start=start_dt,
                end=end_dt,
            )
            if cached is not None:
                logger.info("Cache hit for %s/%s/%s %s-%s", provider_name, symbol, effective_interval, start_dt, end_dt)
                return self._format_cached_response(cached)
        except Exception as e:
            logger.warning("Cache read failed, falling back to API: %s", e)

        # 2. Check current partition for delta fetch
        try:
            last_ts = self._cache.get_last_timestamp(provider_name, symbol, effective_interval)
            if last_ts and last_ts < end_dt:
                # Fetch only missing tail
                delta_from = last_ts.strftime("%Y-%m-%d %H:%M:%S")
                logger.info("Delta fetch for %s/%s/%s from %s", provider_name, symbol, effective_interval, delta_from)
                delta_data = self._fetch_from_api(effective_interval, from_date=delta_from, to_date=to_date)
                if delta_data and delta_data.get("candles"):
                    # Convert delta response to rows and append
                    delta_rows = self._response_to_rows(delta_data, symbol, effective_interval, provider_name)
                    if delta_rows:
                        self._cache.append_to_current_partition(provider_name, symbol, effective_interval, delta_rows)
                        # Return merged cached + delta
                        full_cached = self._cache.load_current_partition(provider_name, symbol, effective_interval)
                        if full_cached:
                            return self._format_cached_response(full_cached)
        except Exception as e:
            logger.warning("Delta fetch failed, falling back to full API fetch: %s", e)

        # 3. Full fetch (no cache or cache miss)
        try:
            api_data = self._fetch_from_api(effective_interval, from_date, to_date)
            if api_data and api_data.get("candles"):
                # Convert to rows and save to cache
                rows = self._response_to_rows(api_data, symbol, effective_interval, provider_name)
                if rows:
                    self._cache.save_partition(provider_name, symbol, effective_interval, start_dt, end_dt, rows)
            return api_data
        except Exception as e:
            logger.exception("API fetch failed for %s/%s/%s: %s", provider_name, symbol, effective_interval, e)
            raise

    def supported_timeframes(self) -> list[str]:
        """Return list of supported timeframe intervals.

        Returns:
            List of timeframe strings supported by Zerodha API (Quantrex format).
        """
        return ZERODHA_MAPPER.get_supported_quantrex_intervals()

    def get_origin_time(self) -> dt_time:
        """Return the origin time for this provider's market.

        Zerodha provider uses NSE (National Stock Exchange of India) origin time
        as the standard for Indian market data.

        Returns:
            Origin time as datetime.time (09:15 for NSE).
        """
        return dt_time(9, 15)

    @property
    def supported_timeframes_property(self) -> list[str]:
        """Property accessor for supported_timeframes."""
        return self.supported_timeframes()

    def _map_timeframe_to_zerodha(self, timeframe: str) -> str:
        """Map Quantrex timeframe format to Zerodha API interval format.

        Args:
            timeframe: Timeframe in Quantrex format (e.g., "1M", "1H", "1D")

        Returns:
            Interval in Zerodha API format (e.g., "minute", "60minute", "day")

        Raises:
            ValueError: If timeframe is not supported.
        """
        return ZERODHA_MAPPER.to_provider(timeframe)

    def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        logger.debug("Closing ZerodhaDataProvider")
        self._client.close()

    def __enter__(self) -> "ZerodhaDataProvider":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()