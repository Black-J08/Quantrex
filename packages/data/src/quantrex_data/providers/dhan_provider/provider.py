"""Dhan Data Provider for Quantrex framework.

Fetches raw OHLCV data from DhanHQ REST API with symbol resolution,
date normalization, automatic chunking, and transparent caching.
"""

from datetime import date, datetime, time
from typing import Any

from quantrex_core.logging import get_logger
from quantrex_core.protocols import DataProvider
from quantrex_data.operations import ArrowCache

from .client import DhanAPIClient
from .config import DhanProviderConfig
from .exceptions import DhanSymbolNotFoundError
from .instrument_master import InstrumentMaster
from .models import HistoricalDataRequest, HistoricalDataResponse, IntradayDataRequest, IntradayDataResponse

logger = get_logger(__name__)


class DhanDataProvider:
    """Data provider for fetching OHLCV data from DhanHQ API.

    Implements the DataProvider protocol. Handles:
    - Symbol resolution via instrument master CSV
    - Date normalization (date/datetime/str -> Dhan format)
    - Automatic chunking for large date ranges
    - Credential loading from .env file
    - Rate limiting and retry logic

    Example:
        >>> provider = DhanDataProvider(
        ...     symbol="RELIANCE",
        ...     exchange_segment="NSE_EQ",
        ...     instrument="EQUITY",
        ...     from_date="2024-01-01",
        ...     to_date="2024-01-31"
        ... )
        >>> data = provider.fetch()
        >>> provider.close()
    """

    def __init__(
        self,
        *,
        access_token: str | None = None,
        client_id: str | None = None,
        symbol: str | None = None,
        security_id: str | None = None,
        exchange_segment: str,
        instrument: str,
        expiry_code: int = 0,
        from_date: date | datetime | str | None = None,
        to_date: date | datetime | str | None = None,
        timeframe: str = "day",
        include_oi: bool = False,
        base_url: str = "https://api.dhan.co/v2",
        timeout: float = 30.0,
        max_retries: int = 3,
        chunk_size_days: dict[str, int] | None = None,
    ) -> None:
        """Initialize Dhan data provider.

        Args:
            access_token: JWT access token. If None, loads from DHAN_ACCESS_TOKEN env var.
            client_id: Dhan client ID. If None, resolved from DHAN_CLIENT_ID env var or
                extracted from the access-token JWT. Required by the Dhan v2 gateway on
                every request (sent as the ``client-id`` header and ``dhanClientId`` body
                field). Without it, the gateway returns 301/400.
            symbol: User-friendly trading symbol (e.g., "RELIANCE"). Mutually exclusive with security_id.
            security_id: Dhan's numeric security ID (e.g., "1333"). Mutually exclusive with symbol.
            exchange_segment: Exchange segment (NSE_EQ, NSE_FNO, NSE_CURRENCY, BSE_EQ, BSE_FNO, BSE_CURRENCY, MCX_COMM).
            instrument: Instrument type (EQUITY, FUTSTK, OPTSTK, FUTIDX, OPTIDX, FUTCOM, OPTFUT, FUTCUR, OPTCUR, INDEX).
            expiry_code: Expiry code for derivatives (0 for equity/index).
            from_date: Optional start date (date, datetime, or str in YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
                      If not provided, must be passed to fetch() at runtime.
            to_date: Optional end date (date, datetime, or str in YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
                    If not provided, must be passed to fetch() at runtime.
            timeframe: Data timeframe (day, 1minute, 5minute, 15minute, 30minute, 60minute).
            include_oi: Include open interest data (F&O only).
            base_url: API base URL. The Dhan v2 endpoints are served under the
            ``/v2/`` prefix. Requests to ``https://api.dhan.co/charts/...``
            are permanently redirected (HTTP 301) to ``https://api.dhan.co/v2/``,
            so the default includes the ``/v2`` suffix. For the sandbox
            environment use ``https://sandbox.dhan.co/v2``.
            timeout: Request timeout in seconds.
            max_retries: Maximum retry attempts.
            chunk_size_days: Custom chunk sizes per timeframe (days per request).

        Raises:
            ValueError: If configuration is invalid.
        """
        # Create config object (validates all inputs)
        # Merge default chunk sizes with user-provided ones.
        # Dhan's historical data API enforces a hard limit of 90 days
        # per request; requests exceeding it fail with ``errorCode``
        # 812/813/814 ("Invalid request parameters"). The chunking layer
        # splits the user's date range into <=90-day sub-requests and
        # merges the responses transparently. We use ``89`` as the
        # stride so the inclusive end-of-chunk stays within the limit
        # even when ``from == to`` (a single inclusive day counts as
        # 1 day, so a 90-day inclusive range needs a 89-day stride).
        default_chunk_sizes = {
            "day": 89,
            "1minute": 30,
            "5minute": 60,
            "15minute": 180,
            "30minute": 360,
            "60minute": 720,
        }
        merged_chunk_sizes = {**default_chunk_sizes, **(chunk_size_days or {})}

        self._config = DhanProviderConfig(
            access_token=access_token,
            client_id=client_id,
            symbol=symbol,
            security_id=security_id,
            exchange_segment=exchange_segment,
            instrument=instrument,
            expiry_code=expiry_code,
            from_date=from_date,
            to_date=to_date,
            timeframe=timeframe,  # type: ignore[arg-type]
            include_oi=include_oi,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            chunk_size_days=merged_chunk_sizes,
        )

        # Initialize components
        self._client = DhanAPIClient(self._config)
        self._instrument_master = InstrumentMaster(self._config)

        # Initialize automatic cache (zero-config, internal)
        self._cache = ArrowCache()

        # Resolve symbol to security_id if needed
        self._security_id = self._config.security_id
        if self._config.symbol is not None:
            self._security_id = self._resolve_symbol(self._config.symbol)

        logger.debug(
            "DhanDataProvider initialized: symbol=%s, security_id=%s, exchange_segment=%s, instrument=%s, timeframe=%s",
            self._config.symbol,
            self._security_id,
            self._config.exchange_segment,
            self._config.instrument,
            self._config.timeframe,
        )

    @property
    def security_id(self) -> str:
        """Get the resolved security ID."""
        return self._security_id

    @property
    def config(self) -> DhanProviderConfig:
        """Get the provider configuration."""
        return self._config

    def _normalize_date_input(self, value: date | datetime | str) -> str:
        """Normalize date/datetime/str input to string for config storage.

        Args:
            value: Date input in various formats.

        Returns:
            String representation (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
        """
        if isinstance(value, str):
            return value
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(value, date):
            return value.strftime("%Y-%m-%d")
        raise ValueError(f"Unsupported date type: {type(value)}. Use date, datetime, or str.")

    def _normalize_date_for_api(self, value: str, is_intraday: bool) -> str:
        """Normalize stored date string to Dhan API format.

        Args:
            value: Date string from config.
            is_intraday: Whether this is for intraday API.

        Returns:
            Date string in Dhan API format.
        """
        # If already has time component, use as-is for intraday
        if is_intraday and " " in value:
            return value

        # For daily, ensure YYYY-MM-DD format
        if not is_intraday:
            # Strip time component if present
            return value.split(" ")[0]

        # For intraday without time, assume market open
        return value + " 09:15:00"

    def _resolve_symbol(self, symbol: str) -> str:
        """Resolve trading symbol to security_id using instrument master.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE").

        Returns:
            Security ID as string.

        Raises:
            DhanSymbolNotFoundError: If symbol not found.
        """
        logger.debug("Resolving symbol '%s' for exchange_segment '%s'", symbol, self._config.exchange_segment)
        security_id = self._instrument_master.resolve_symbol(symbol, self._config.exchange_segment)
        logger.debug("Resolved '%s' -> security_id='%s'", symbol, security_id)
        return security_id

    def _chunk_date_range(self, from_date: str, to_date: str, is_intraday: bool) -> list[tuple[str, str]]:
        """Split date range into API-compliant chunks.

        Args:
            from_date: Start date string.
            to_date: End date string.
            is_intraday: Whether this is for intraday API.

        Returns:
            List of (chunk_from, chunk_to) date tuples. Every chunk has
            a strictly positive span (``chunk_to > chunk_from``) because
            Dhan's daily and intraday APIs reject same-day windows with
            HTTP 400 / ``errorCode: DH-907``. Verified against Dhan v2:
            a same-day ``fromDate == toDate`` request returns ``DH-907``
            while ``toDate = fromDate + 1 day`` succeeds and returns the
            inclusive candle for ``fromDate``. When the user's range
            would otherwise leave a single-day residue at the tail, this
            chunker absorbs that residue into the previous chunk so no
            candle in the requested window is dropped and no chunk is
            rejected.
        """
        # Parse dates
        if is_intraday and " " in from_date:
            start = datetime.strptime(from_date, "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(to_date, "%Y-%m-%d %H:%M:%S")
        else:
            start = datetime.strptime(from_date.split(" ")[0], "%Y-%m-%d")
            end = datetime.strptime(to_date.split(" ")[0], "%Y-%m-%d")

        chunk_days = self._config.chunk_size_days.get(self._config.timeframe, 30)
        fmt = "%Y-%m-%d %H:%M:%S" if is_intraday and " " in from_date else "%Y-%m-%d"

        if start == end:
            # Same-day range: a single 1-day chunk. The caller is
            # responsible for treating such requests as meaningful
            # (Dhan rejects them with ``DH-907``).
            return [(start.strftime(fmt), end.strftime(fmt))]

        # Build the sequence of chunk starts and ends by walking the
        # range in ``chunk_days`` strides. Each chunk's ``to_date`` is
        # inclusive; the next chunk's ``from_date`` is
        # ``previous.to_date + 1 day``. When the remainder of the range
        # after a stride would be a single day (i.e. the next stride
        # would start exactly on ``end``), we extend the current
        # chunk's ``to_date`` to ``end`` instead of emitting a same-day
        # request that Dhan would reject. Verified against Dhan v2:
        # ``fromDate == toDate`` returns HTTP 400 / ``errorCode DH-907``.
        chunks: list[tuple[str, str]] = []
        current_start = start
        while current_start <= end:
            stride_end = current_start + __import__("datetime").timedelta(days=chunk_days)
            next_start = stride_end + __import__("datetime").timedelta(days=1)

            if stride_end >= end:
                # This stride covers or overshoots the end; a single
                # chunk finishes the range.
                current_end = end
            elif next_start >= end:
                # After this stride, only a same-day residue would
                # remain (or no range at all). Absorb it into this
                # chunk so we never emit a ``from == to`` request.
                current_end = end
            else:
                current_end = stride_end

            chunks.append((current_start.strftime(fmt), current_end.strftime(fmt)))

            if current_end >= end:
                break
            current_start = current_end + __import__("datetime").timedelta(days=1)

        logger.debug("Split date range into %d chunks for timeframe '%s'", len(chunks), self._config.timeframe)
        return chunks

    def _merge_responses(self, responses: list[HistoricalDataResponse | IntradayDataResponse]) -> dict:
        """Merge multiple chunked responses into single response dict.

        Args:
            responses: List of response objects.

        Returns:
            Merged response as dictionary with combined arrays.
        """
        if not responses:
            return {}

        if len(responses) == 1:
            return responses[0].model_dump(by_alias=True)

        # Merge arrays
        merged = {
            "open": [],
            "high": [],
            "low": [],
            "close": [],
            "volume": [],
            "timestamp": [],
        }
        has_oi = responses[0].open_interest is not None
        if has_oi:
            merged["open_interest"] = []

        for resp in responses:
            merged["open"].extend(resp.open)
            merged["high"].extend(resp.high)
            merged["low"].extend(resp.low)
            merged["close"].extend(resp.close)
            merged["volume"].extend(resp.volume)
            merged["timestamp"].extend(resp.timestamp)
            if has_oi and resp.open_interest is not None:
                merged["open_interest"].extend(resp.open_interest)

        logger.debug("Merged %d chunks into %d candles", len(responses), len(merged["timestamp"]))
        return merged

    def _fetch_from_api(self, timeframe: str, from_date: str | None = None, to_date: str | None = None) -> dict:
        """Internal method to fetch raw data from Dhan API.

        Args:
            timeframe: Timeframe in Quantrex format (e.g., "1M", "1D")
            from_date: Optional override for start date (API format)
            to_date: Optional override for end date (API format)

        Returns:
            Raw API response as dictionary.
        """
        dhan_timeframe = self._map_timeframe_to_dhan(timeframe)
        is_intraday = dhan_timeframe != "day"

        # Use provided dates or fall back to config
        api_from_date = from_date or self._normalize_date_for_api(self._config.from_date, is_intraday)
        api_to_date = to_date or self._normalize_date_for_api(self._config.to_date, is_intraday)

        logger.info(
            "Fetching %s data from API for security_id='%s' from %s to %s",
            timeframe,
            self._security_id,
            api_from_date,
            api_to_date,
        )

        # Chunk date range
        chunks = self._chunk_date_range(api_from_date, api_to_date, is_intraday)

        responses = []
        for i, (chunk_from, chunk_to) in enumerate(chunks):
            logger.debug("Fetching chunk %d/%d: %s to %s", i + 1, len(chunks), chunk_from, chunk_to)

            if is_intraday:
                request = IntradayDataRequest(
                    securityId=self._security_id,
                    exchangeSegment=self._config.exchange_segment,
                    instrument=self._config.instrument,
                    interval=dhan_timeframe.replace("minute", ""),
                    oi=self._config.include_oi,
                    fromDate=chunk_from,
                    toDate=chunk_to,
                )
                response = self._client.get_intraday_historical(request)
            else:
                request = HistoricalDataRequest(
                    securityId=self._security_id,
                    exchangeSegment=self._config.exchange_segment,
                    instrument=self._config.instrument,
                    expiryCode=self._config.expiry_code,
                    oi=self._config.include_oi,
                    fromDate=chunk_from,
                    toDate=chunk_to,
                )
                response = self._client.get_daily_historical(request)

            responses.append(response)

        # Merge all chunked responses
        merged = self._merge_responses(responses)

        logger.info("Fetched %d candles from API for security_id='%s'", len(merged.get("timestamp", [])), self._security_id)
        return merged

    def _format_cached_response(self, rows: list[dict]) -> dict:
        """Convert cached rows back to provider response format."""
        if not rows:
            return {"timestamp": [], "open": [], "high": [], "low": [], "close": [], "volume": []}

        # Extract arrays from rows
        timestamps = []
        opens = []
        highs = []
        lows = []
        closes = []
        volumes = []
        ois = []

        for row in rows:
            # Parse datetime string to epoch seconds (IST)
            dt_str = row.get("datetime", "")
            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                # Convert to epoch seconds assuming IST
                epoch = int(dt.timestamp())
            except Exception:
                epoch = 0
            timestamps.append(epoch)
            opens.append(row.get("open", 0))
            highs.append(row.get("high", 0))
            lows.append(row.get("low", 0))
            closes.append(row.get("close", 0))
            volumes.append(row.get("volume", 0))
            if "oi" in row and row["oi"] is not None:
                ois.append(row["oi"])

        result = {
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
        if ois:
            result["open_interest"] = ois
        return result

    def fetch(
        self,
        timeframe: str | None = None,
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
            timeframe: Timeframe interval (e.g., "1M", "5M", "15M", "30M", "1H", "1D").
                      None uses the provider's configured timeframe.
            from_date: Optional start date override (ISO format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS").
                      If provided, overrides the provider's configured from_date.
            to_date: Optional end date override (ISO format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS").
                    If provided, overrides the provider's configured to_date.

        Returns:
            Raw API response as dictionary with keys:
            open, high, low, close, volume, timestamp (arrays), and optionally open_interest.

        Raises:
            DhanSymbolNotFoundError: If symbol resolution fails.
            DhanAuthenticationError: If authentication fails.
            DhanRateLimitError: If rate limit exceeded.
            DhanDataNotFoundError: If no data returned.
            DhanInvalidParameterError: If request parameters invalid.
            DhanAPIError: Other API errors.
        """
        effective_timeframe = timeframe or self._config.timeframe
        provider_name = "dhan"
        symbol = self._config.symbol or self._security_id

        # Determine effective dates: use overrides if provided, else config
        effective_from_date = from_date or self._config.from_date
        effective_to_date = to_date or self._config.to_date

        # If dates are not configured and not overridden, we can't use cache
        if effective_from_date is None or effective_to_date is None:
            logger.warning("Date range not configured; skipping cache and fetching from API")
            return self._fetch_from_api(effective_timeframe, from_date, to_date)

        # Parse config dates for cache operations
        try:
            start_dt = datetime.strptime(effective_from_date.split(" ")[0], "%Y-%m-%d")
            end_dt = datetime.strptime(effective_to_date.split(" ")[0], "%Y-%m-%d")
        except Exception:
            # If date parsing fails, skip cache and go straight to API
            logger.warning("Failed to parse dates for caching, falling back to API")
            return self._fetch_from_api(effective_timeframe, from_date, to_date)

        # 1. Try cache for exact date range (closed partition)
        try:
            cached = self._cache.load_partition(
                provider=provider_name,
                symbol=symbol,
                timeframe=effective_timeframe,
                start=start_dt,
                end=end_dt,
            )
            if cached is not None:
                logger.info("Cache hit for %s/%s/%s %s-%s", provider_name, symbol, effective_timeframe, start_dt, end_dt)
                return self._format_cached_response(cached)
        except Exception as e:
            logger.warning("Cache read failed, falling back to API: %s", e)

        # 2. Check current partition for delta fetch
        try:
            last_ts = self._cache.get_last_timestamp(provider_name, symbol, effective_timeframe)
            if last_ts and last_ts < end_dt:
                # Fetch only missing tail
                delta_from = last_ts.strftime("%Y-%m-%d %H:%M:%S")
                logger.info("Delta fetch for %s/%s/%s from %s", provider_name, symbol, effective_timeframe, delta_from)
                delta_data = self._fetch_from_api(effective_timeframe, from_date=delta_from, to_date=to_date)
                if delta_data and delta_data.get("timestamp"):
                    # Convert delta response to rows and append
                    delta_rows = self._response_to_rows(delta_data, symbol, effective_timeframe, provider_name)
                    if delta_rows:
                        self._cache.append_to_current_partition(provider_name, symbol, effective_timeframe, delta_rows)
                        # Return merged cached + delta
                        full_cached = self._cache.load_current_partition(provider_name, symbol, effective_timeframe)
                        if full_cached:
                            return self._format_cached_response(full_cached)
        except Exception as e:
            logger.warning("Delta fetch failed, falling back to full API fetch: %s", e)

        # 3. Full fetch (no cache or cache miss)
        try:
            api_data = self._fetch_from_api(effective_timeframe, from_date, to_date)
            if api_data and api_data.get("timestamp"):
                # Convert to rows and save to cache
                rows = self._response_to_rows(api_data, symbol, effective_timeframe, provider_name)
                if rows:
                    self._cache.save_partition(provider_name, symbol, effective_timeframe, start_dt, end_dt, rows)
            return api_data
        except Exception as e:
            logger.exception("API fetch failed for %s/%s/%s: %s", provider_name, symbol, effective_timeframe, e)
            raise

    def _response_to_rows(self, response: dict, symbol: str, timeframe: str, provider: str) -> list[dict]:
        """Convert provider response dict to list of row dicts for caching."""
        if not response or not response.get("timestamp"):
            return []

        timestamps = response.get("timestamp", [])
        opens = response.get("open", [])
        highs = response.get("high", [])
        lows = response.get("low", [])
        closes = response.get("close", [])
        volumes = response.get("volume", [])
        ois = response.get("open_interest")

        n = len(timestamps)
        if n == 0:
            return []

        rows = []
        for i in range(n):
            # Convert epoch to datetime string (IST)
            epoch = timestamps[i]
            try:
                dt = datetime.fromtimestamp(epoch)
                dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                dt_str = ""

            row = {
                "datetime": dt_str,
                "open": float(opens[i]) if i < len(opens) else 0.0,
                "high": float(highs[i]) if i < len(highs) else 0.0,
                "low": float(lows[i]) if i < len(lows) else 0.0,
                "close": float(closes[i]) if i < len(closes) else 0.0,
                "volume": float(volumes[i]) if i < len(volumes) else 0.0,
            }
            if ois is not None and i < len(ois):
                row["oi"] = float(ois[i])
            rows.append(row)

        return rows

    def supported_timeframes(self) -> list[str]:
        """Return list of supported timeframe intervals.
        
        Returns:
            List of timeframe strings supported by Dhan API.
        """
        return ["1M", "5M", "15M", "30M", "1H", "1D"]
    
    def get_origin_time(self) -> time:
        """Return the origin time for this provider's market.
        
        Dhan provider uses NSE (National Stock Exchange of India) origin time
        as the standard for Indian market data.
        
        Returns:
            Origin time as datetime.time (09:15 for NSE).
        """
        return time(9, 15)
    
    @property
    def supported_timeframes_property(self) -> list[str]:
        """Property accessor for supported_timeframes."""
        return self.supported_timeframes()
    
    def _map_timeframe_to_dhan(self, timeframe: str) -> str:
        """Map our timeframe format to Dhan API format.
        
        Args:
            timeframe: Timeframe in our format (e.g., "1M", "1H", "1D")
            
        Returns:
            Timeframe in Dhan API format (e.g., "1minute", "60minute", "day")
        """
        mapping = {
            "1M": "1minute",
            "5M": "5minute",
            "15M": "15minute",
            "30M": "30minute",
            "1H": "60minute",
            "1D": "day",
            "day": "day",  # Backward compatibility
            "1minute": "1minute",  # Backward compatibility
            "5minute": "5minute",
            "15minute": "15minute",
            "30minute": "30minute",
            "60minute": "60minute",
        }
        if timeframe not in mapping:
            raise ValueError(f"Unsupported timeframe: {timeframe}. Supported: {list(mapping.keys())}")
        return mapping[timeframe]

    def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        logger.debug("Closing DhanDataProvider")
        self._client.close()

    def __enter__(self) -> "DhanDataProvider":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()