"""Cache key construction.

A cache key identifies one canonical OHLCV query: the symbol, the timeframe,
the exact instants it covers, and the vendor options that change the response.
The key also determines where the data lives on disk, so two queries that
would produce different data can never share a file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, unquote

from quantrex.core.models.timeframe import Timeframe


@dataclass(slots=True, frozen=True)
class CacheKey:
    """Identity of a cached OHLCV query.

    Attributes:
        symbol: Trading symbol, e.g. ``"NSE:INFY"``.
        timeframe: Candle timeframe.
        from_date: Start of the covered range (inclusive).
        to_date: End of the covered range (exclusive).
        continuous: Whether the data comes from the continuous futures series.
        oi: Whether the data includes open interest.
        version: Cache format version, used to invalidate old files.
    """

    symbol: str
    timeframe: Timeframe
    from_date: datetime
    to_date: datetime
    continuous: bool = False
    oi: bool = False
    version: int = 1

    def __post_init__(self) -> None:
        """Validate the key components."""
        if not self.symbol:
            raise ValueError("symbol cannot be empty")
        if self.symbol in {".", ".."}:
            raise ValueError(f"symbol cannot be a path segment: {self.symbol!r}")
        if self.from_date >= self.to_date:
            raise ValueError("from_date must be before to_date")

    @staticmethod
    def encode_symbol(symbol: str) -> str:
        """Encode a symbol for use as a single path segment.

        Percent-encoding keeps the mapping reversible and keeps ``:`` and
        ``/`` out of the path, so ``"NSE:INFY"`` and ``"NSE_INFY"`` cannot
        collide.
        """
        return quote(symbol, safe="")

    @staticmethod
    def decode_symbol(encoded: str) -> str:
        """Decode a symbol previously encoded by :meth:`encode_symbol`."""
        return unquote(encoded)

    def series_name(self) -> str:
        """Render the name of the directory holding this series' data.

        The name carries the timeframe, the vendor options and the format
        version, so data fetched under different options, or written by an
        older version, is kept in a separate place.
        """
        flags = f"c{int(self.continuous)}o{int(self.oi)}"
        return f"{self.timeframe}_{flags}_v{self.version}"

    @classmethod
    def create(
        cls,
        symbol: str,
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime,
        continuous: bool = False,
        oi: bool = False,
        version: int = 1,
    ) -> CacheKey:
        """Create a cache key from components.

        Instants are normalized to UTC, so the same moment expressed in two
        timezones yields the same key.
        """
        if from_date.tzinfo is None or to_date.tzinfo is None:
            raise ValueError("from_date and to_date must be timezone-aware")

        return cls(
            symbol=symbol,
            timeframe=timeframe,
            from_date=from_date.astimezone(UTC),
            to_date=to_date.astimezone(UTC),
            continuous=continuous,
            oi=oi,
            version=version,
        )
