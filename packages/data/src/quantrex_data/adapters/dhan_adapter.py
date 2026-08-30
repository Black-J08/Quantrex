"""Dhan Data Adapter for Quantrex framework.

Normalizes raw Dhan API responses to standardized OHLCV format
for the Backtest Engine.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from quantrex_core.logging import get_logger
from quantrex_core.protocols import DataAdapter, DataProvider

from quantrex_data.providers.dhan_provider import DhanDataProvider

logger = get_logger(__name__)

# Dhan returns ``timestamp`` as epoch seconds in Indian Standard Time
# (UTC+05:30). The official ``dhanhq-py`` SDK confirms this in
# ``dhanhq.convert_to_date_time`` which constructs the result via
# ``datetime.fromtimestamp(epoch, IST)``. We pin the canonical source
# timezone here so every layer of Quantrex agrees on the wall clock.
DHAN_SOURCE_TIMEZONE = "Asia/Kolkata"
# IST is the canonical market timezone for Indian exchanges. Defaulting
# the adapter's output to IST means the naive ``datetime`` written into
# ``Candle.timestamp`` and into the exported ``closed_trades.csv``
# matches the timestamps the user saw on the exchange.
DEFAULT_OUTPUT_TIMEZONE = "Asia/Kolkata"


class DhanDataAdapter:
    """Data adapter for normalizing Dhan API data to engine format.

    Consumes a DhanDataProvider and converts its array-based response
    into standardized OHLCV dictionaries with proper datetime formatting.

    Timestamps:
        Dhan returns ``timestamp`` arrays as epoch seconds in IST
        (UTC+05:30). This adapter treats them as such, then renders the
        naive wall clock in the requested output timezone (IST by
        default). The resulting ``Candle.timestamp`` and CSV-exported
        timestamps therefore match the exchange's local clock for
        Indian market data.

    Example:
        >>> provider = DhanDataProvider(
        ...     symbol="RELIANCE",
        ...     exchange_segment="NSE_EQ",
        ...     instrument="EQUITY",
        ...     from_date="2024-01-01",
        ...     to_date="2024-01-31"
        ... )
        >>> adapter = DhanDataAdapter(provider)
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
        """Initialize Dhan data adapter.

        Args:
            provider: DhanDataProvider instance to consume data from.
            datetime_format: Format string for output datetime (default: "%Y-%m-%d %H:%M:%S").
            timezone: Output timezone for the naive ``datetime`` string emitted in each
                row (default: ``"Asia/Kolkata"``). Dhan's source timestamps are IST;
                the output timezone controls only the wall-clock projection the rest of
                Quantrex (Candle, backtest engine, exported CSVs) will see.

        Raises:
            TypeError: If provider is not a DhanDataProvider instance.
            ValueError: If ``timezone`` is not a valid IANA zone identifier.
        """
        if not isinstance(provider, DhanDataProvider):
            raise TypeError(f"DhanDataAdapter requires DhanDataProvider, got {type(provider).__name__}")

        # Fail loudly on bad timezones so we never silently fall back to a wrong
        # projection (the previous implementation only logged a warning and
        # produced UTC output, which was the original bug's proximate cause).
        try:
            self._source_tz = ZoneInfo(DHAN_SOURCE_TIMEZONE)
            self._output_tz = ZoneInfo(timezone)
        except Exception as e:
            raise ValueError(f"Invalid timezone '{timezone}': {e}") from e

        self._provider = provider
        self._datetime_format = datetime_format
        self._timezone_name = timezone
    
    @property
    def datetime_format(self) -> str:
        """Format string used for datetime parsing (single source of truth)."""
        return self._datetime_format

        logger.debug(
            "DhanDataAdapter initialized with datetime_format='%s', source='%s', output='%s'",
            datetime_format,
            DHAN_SOURCE_TIMEZONE,
            timezone,
        )

    def read(self) -> list[dict]:
        """Read normalized OHLCV data from the Dhan provider.

        Returns:
            List of dictionaries with standardized keys:
            'datetime', 'open', 'high', 'low', 'close', 'volume'
            (and 'oi' if open interest was requested).

        Raises:
            Exception: Propagates exceptions from provider.fetch().
        """
        logger.debug("Reading data from DhanDataProvider")

        # Fetch raw data from provider
        raw_data = self._provider.fetch()

        if not raw_data or not raw_data.get("timestamp"):
            logger.warning("No data returned from DhanDataProvider")
            return []

        # Extract arrays
        timestamps = raw_data["timestamp"]
        opens = raw_data["open"]
        highs = raw_data["high"]
        lows = raw_data["low"]
        closes = raw_data["close"]
        volumes = raw_data["volume"]
        ois = raw_data.get("open_interest")  # Optional

        # Validate array lengths
        n = len(timestamps)
        if not all(len(arr) == n for arr in [opens, highs, lows, closes, volumes]):
            raise ValueError("Response array lengths mismatch")

        if ois is not None and len(ois) != n:
            raise ValueError("Open interest array length mismatch")

        # Convert to list of dicts
        results = []
        for i in range(n):
            # Dhan returns epoch seconds in IST. Interpreting the epoch
            # as if it were UTC (the previous behaviour) shifted every
            # daily candle by 5h30m and pushed intraday candles outside
            # market hours. Build the moment in IST first, then project
            # to the requested output timezone.
            epoch = timestamps[i]
            ist_dt = datetime.fromtimestamp(epoch, tz=self._source_tz)
            out_dt = ist_dt.astimezone(self._output_tz)

            # Naive wall clock in the output timezone. Candle.from_row
            # uses ``datetime.strptime`` which produces naive datetimes;
            # downstream code treats ``timestamp`` as a wall-clock value,
            # so the projection is the contract this layer enforces.
            datetime_str = out_dt.strftime(self._datetime_format)

            row = {
                "datetime": datetime_str,
                "open": float(opens[i]),
                "high": float(highs[i]),
                "low": float(lows[i]),
                "close": float(closes[i]),
                "volume": float(volumes[i]),
            }

            # Add OI if present
            if ois is not None:
                row["oi"] = float(ois[i])

            results.append(row)

        logger.debug("DhanDataAdapter: normalized %d rows", len(results))
        return results

    def close(self) -> None:
        """Close the underlying provider."""
        logger.debug("Closing DhanDataAdapter")
        self._provider.close()

    def __enter__(self) -> "DhanDataAdapter":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()