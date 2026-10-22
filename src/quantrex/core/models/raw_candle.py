"""Raw vendor candle model for the trading framework.

This is a vendor-neutral wire model: it represents a candle exactly as a vendor
returned it, before normalization into the canonical :class:`OHLCVCandle`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(slots=True, frozen=True)
class RawCandle:
    """Raw candle data as received from a vendor API.

    Attributes:
        timestamp: Candle start time.
        open: Opening price.
        high: Highest price.
        low: Lowest price.
        close: Closing price.
        volume: Trading volume.
        oi: Open interest, when the vendor supplies it.
    """

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    oi: Decimal | None = None

    @classmethod
    def from_api_response(cls, data: list) -> RawCandle:
        """Create a RawCandle from a vendor API response array.

        Expected format: [timestamp, open, high, low, close, volume]
        Optional: [timestamp, open, high, low, close, volume, oi]
        """
        if len(data) < 6:
            raise ValueError(f"Invalid candle data: expected at least 6 elements, got {len(data)}")

        # Parse timestamp - vendors may return an ISO string or a POSIX timestamp
        ts_value = data[0]
        if isinstance(ts_value, str):
            timestamp = datetime.fromisoformat(ts_value)
        else:
            timestamp = datetime.fromtimestamp(ts_value, tz=UTC)

        return cls(
            timestamp=timestamp,
            open=Decimal(str(data[1])),
            high=Decimal(str(data[2])),
            low=Decimal(str(data[3])),
            close=Decimal(str(data[4])),
            volume=Decimal(str(data[5])),
            oi=Decimal(str(data[6])) if len(data) > 6 and data[6] is not None else None,
        )
