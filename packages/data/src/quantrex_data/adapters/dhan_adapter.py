"""Dhan Data Adapter for Quantrex framework.

Normalizes raw Dhan API responses to standardized OHLCV format
for the Backtest Engine.
"""

from datetime import datetime, timezone
from typing import Any

from loguru import logger

from quantrex_core.protocols import DataAdapter, DataProvider

from quantrex_data.providers.dhan_provider import DhanDataProvider


class DhanDataAdapter:
    """Data adapter for normalizing Dhan API data to engine format.

    Consumes a DhanDataProvider and converts its array-based response
    into standardized OHLCV dictionaries with proper datetime formatting.

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
        timezone: str = "UTC",
    ) -> None:
        """Initialize Dhan data adapter.

        Args:
            provider: DhanDataProvider instance to consume data from.
            datetime_format: Format string for output datetime (default: "%Y-%m-%d %H:%M:%S").
            timezone: Output timezone (default: "UTC"). Dhan returns IST timestamps.

        Raises:
            TypeError: If provider is not a DhanDataProvider instance.
        """
        if not isinstance(provider, DhanDataProvider):
            raise TypeError(f"DhanDataAdapter requires DhanDataProvider, got {type(provider).__name__}")

        self._provider = provider
        self._datetime_format = datetime_format
        self._timezone = timezone

        logger.debug("DhanDataAdapter initialized with datetime_format='{}', timezone='{}'", datetime_format, timezone)

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
            # Convert epoch timestamp to datetime
            # Dhan returns epoch seconds in IST
            epoch = timestamps[i]
            dt = datetime.fromtimestamp(epoch, tz=timezone.utc)

            # Convert to target timezone if needed
            if self._timezone != "UTC":
                try:
                    import zoneinfo
                    target_tz = zoneinfo.ZoneInfo(self._timezone)
                    dt = dt.astimezone(target_tz)
                except Exception:
                    logger.warning("Invalid timezone '{}', using UTC", self._timezone)

            # Format datetime
            datetime_str = dt.strftime(self._datetime_format)

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

        logger.debug("DhanDataAdapter: normalized {} rows", len(results))
        return results

    def close(self) -> None:
        """Close the underlying provider."""
        logger.debug("Closing DhanDataAdapter")
        self._provider.close()

    def __enter__(self) -> "DhanDataAdapter":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()