"""Zerodha Data Adapter for Quantrex framework.

Normalizes raw Zerodha API responses to standardized OHLCV format
for the Backtest Engine.
"""

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from quantrex_core.logging import get_logger
from quantrex_core.protocols import DataAdapter, DataProvider

from quantrex_data.providers.zerodha_provider import ZerodhaDataProvider

logger = get_logger(__name__)

# Zerodha returns timestamps in ISO 8601 format with timezone offset
# e.g., "2019-12-04T09:15:00+0530" (IST = UTC+05:30)
# The source timezone is IST (Asia/Kolkata)
ZERODHA_SOURCE_TIMEZONE = "Asia/Kolkata"
# IST is the canonical market timezone for Indian exchanges. Defaulting
# the adapter's output to IST means the naive ``datetime`` written into
# ``Candle.timestamp`` and into the exported ``closed_trades.csv``
# matches the timestamps the user saw on the exchange.
DEFAULT_OUTPUT_TIMEZONE = "Asia/Kolkata"


class ZerodhaDataAdapter:
    """Data adapter for normalizing Zerodha API data to engine format.

    Consumes a ZerodhaDataProvider and converts its candle array response
    into standardized OHLCV dictionaries with proper datetime formatting.

    Timestamps:
        Zerodha returns timestamps as ISO 8601 strings with timezone offset
        (e.g., "2019-12-04T09:15:00+0530"). This adapter parses them as
        timezone-aware datetimes, then renders the naive wall clock in the
        requested output timezone (IST by default). The resulting
        ``Candle.timestamp`` and CSV-exported timestamps therefore match
        the exchange's local clock for Indian market data.

    Example:
        >>> provider = ZerodhaDataProvider(
        ...     symbol="RELIANCE",
        ...     exchange="NSE",
        ...     from_date="2024-01-01",
        ...     to_date="2024-01-31"
        ... )
        >>> adapter = ZerodhaDataAdapter(provider)
        >>> data = adapter.read()
        >>> adapter.close()
    """

    REQUIRED_KEYS = ("datetime", "open", "high", "low", "close", "volume")

    def __init__(
        self,
        provider: DataProvider,
        datetime_format: str = "%Y-%m-%d %H:%M:%S",
        timezone: str = DEFAULT_OUTPUT_TIMEZONE,
    ) -> None:
        """Initialize Zerodha data adapter.

        Args:
            provider: ZerodhaDataProvider instance to consume data from.
            datetime_format: Format string for output datetime (default: "%Y-%m-%d %H:%M:%S").
            timezone: Output timezone for the naive ``datetime`` string emitted in each
                row (default: ``"Asia/Kolkata"``). Zerodha's source timestamps are IST;
                the output timezone controls only the wall-clock projection the rest of
                Quantrex (Candle, backtest engine, exported CSVs) will see.

        Raises:
            TypeError: If provider is not a ZerodhaDataProvider instance.
            ValueError: If ``timezone`` is not a valid IANA zone identifier.
        """
        if not isinstance(provider, ZerodhaDataProvider):
            raise TypeError(f"ZerodhaDataAdapter requires ZerodhaDataProvider, got {type(provider).__name__}")

        # Fail loudly on bad timezones so we never silently fall back to a wrong
        # projection (the previous implementation only logged a warning and
        # produced UTC output, which was the original bug's proximate cause).
        try:
            self._source_tz = ZoneInfo(ZERODHA_SOURCE_TIMEZONE)
            self._output_tz = ZoneInfo(timezone)
        except Exception as e:
            raise ValueError(f"Invalid timezone '{timezone}': {e}") from e

        self._provider = provider
        self._datetime_format = datetime_format
        self._timezone_name = timezone

        logger.debug(
            "ZerodhaDataAdapter initialized with datetime_format='%s', source='%s', output='%s'",
            datetime_format,
            ZERODHA_SOURCE_TIMEZONE,
            timezone,
        )

    @property
    def datetime_format(self) -> str:
        """Format string used for datetime parsing (single source of truth)."""
        return self._datetime_format

    @property
    def supported_timeframes(self) -> list[str]:
        """Return list of supported timeframe intervals.

        Delegates to the underlying provider.
        """
        # Handle both real providers and mocks
        supported = getattr(self._provider, 'supported_timeframes_property', None)
        if supported is None:
            supported = getattr(self._provider, 'supported_timeframes', None)
        if callable(supported):
            try:
                return supported()
            except Exception:
                return ["1M", "3M", "5M", "10M", "15M", "30M", "1H", "1D"]
        elif isinstance(supported, list):
            return supported
        return ["1M", "3M", "5M", "10M", "15M", "30M", "1H", "1D"]

    def get_origin_time(self) -> time:
        """Return the origin time for this adapter's market.

        Zerodha adapter delegates to its underlying provider for origin time.

        Returns:
            Origin time as datetime.time (09:15 for NSE).
        """
        return self._provider.get_origin_time()

    def read(self) -> list[dict]:
        """Read normalized OHLCV data from the Zerodha provider (base timeframe).

        Returns:
            List of dictionaries with standardized keys:
            'datetime', 'open', 'high', 'low', 'close', 'volume'
            (and 'oi' if open interest was requested).
        """
        # Use the provider's default timeframe
        timeframes = self.supported_timeframes
        return self.read_timeframe(timeframes[0] if timeframes else "1M")

    def read_timeframe(self, timeframe: str) -> list[dict]:
        """Read normalized OHLCV data for a specific timeframe.

        Args:
            timeframe: Timeframe interval (e.g., "1M", "5M", "15M", "30M", "1H", "1D").

        Returns:
            List of dictionaries with standardized keys for the given timeframe.
        """
        # Validate timeframe is supported
        if timeframe not in self.supported_timeframes:
            raise ValueError(f"Timeframe '{timeframe}' not supported. Supported: {self.supported_timeframes}")

        logger.debug("Reading data from ZerodhaDataProvider for timeframe %s", timeframe)

        # Map timeframe to Zerodha interval and fetch raw data
        zerodha_interval = self._provider._map_timeframe_to_zerodha(timeframe)
        raw_data = self._provider.fetch(interval=zerodha_interval)

        if not raw_data or not raw_data.get("candles"):
            logger.warning("No data returned from ZerodhaDataProvider for timeframe %s", timeframe)
            return []

        candles = raw_data["candles"]

        # Validate candle structure
        if not candles:
            return []

        # Each candle: [timestamp, open, high, low, close, volume, oi?]
        expected_len = len(candles[0])
        if expected_len not in (6, 7):
            raise ValueError(f"Unexpected candle format: expected 6 or 7 elements, got {expected_len}")

        has_oi = expected_len == 7

        # Convert to list of dicts
        results = []
        for i, candle in enumerate(candles):
            try:
                # Parse timestamp - Zerodha returns ISO 8601 with offset
                # e.g., "2019-12-04T09:15:00+0530"
                timestamp_str = candle[0]
                # Parse as timezone-aware datetime
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

                # Convert to output timezone
                out_dt = dt.astimezone(self._output_tz)

                # Naive wall clock in the output timezone
                datetime_str = out_dt.strftime(self._datetime_format)

                row = {
                    "datetime": datetime_str,
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5]),
                }

                # Add OI if present
                if has_oi:
                    row["oi"] = float(candle[6])

                results.append(row)

            except (ValueError, IndexError) as e:
                logger.warning("Skipping malformed candle at index %d: %s", i, e)
                continue

        logger.debug("ZerodhaDataAdapter: normalized %d rows for timeframe %s", len(results), timeframe)
        return results

    def close(self) -> None:
        """Close the underlying provider."""
        logger.debug("Closing ZerodhaDataAdapter")
        self._provider.close()

    def __enter__(self) -> "ZerodhaDataAdapter":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()