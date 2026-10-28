"""Zerodha historical data provider implementation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quantrex.core.broker.zerodha.historical import ZerodhaHistoricalDataClient
from quantrex.core.broker.zerodha.instrument_master import InstrumentMaster
from quantrex.core.broker.zerodha.session.session import ZerodhaSession
from quantrex.core.data.cache.cache_key import CacheKey
from quantrex.core.data.cache.ohlcv_cache import OHLCVCache, missing_intervals
from quantrex.core.data.exceptions import (
    NormalizationError,
    ProviderError,
    SymbolResolutionError,
    TimeframeNotSupportedError,
)
from quantrex.core.data.historical.provider import HistoricalDataProvider
from quantrex.core.data.normalization import ZerodhaNormalizer
from quantrex.core.exceptions import AmbiguousSymbolError, SymbolNotFoundError
from quantrex.core.models import OHLCVCandle, Timeframe, TimeframeUnit

logger = logging.getLogger(__name__)

#: Cache format version. Bumped when the on-disk layout or the stored bar
#: times change, so that files written by an older version are ignored.
CACHE_VERSION = 2


def _month_segments(from_date: datetime, to_date: datetime) -> list[tuple[datetime, datetime]]:
    """Split a range into calendar-month aligned segments.

    A month is the longest span that stays under every Zerodha per-request
    limit (the tightest is 60 days for 1-minute candles), so each segment
    can be fetched in a single request without being truncated.
    """
    segments: list[tuple[datetime, datetime]] = []
    cursor = from_date.astimezone(UTC)
    end = to_date.astimezone(UTC)

    while cursor < end:
        next_month = datetime(
            cursor.year + (cursor.month == 12),
            (cursor.month % 12) + 1,
            1,
            tzinfo=UTC,
        )
        segment_end = min(end, next_month)
        segments.append((cursor, segment_end))
        cursor = segment_end

    return segments


class ZerodhaHistoricalDataProvider(HistoricalDataProvider):
    """Historical data provider for Zerodha.

    Owns the full historical-data path: working out which intervals are
    already cached, fetching only the missing ones through the broker client,
    normalizing into canonical models, and storing the result.
    """

    def __init__(
        self,
        session: ZerodhaSession,
        instrument_master: InstrumentMaster | None = None,
        normalizer: ZerodhaNormalizer | None = None,
        cache_dir: Path | str | None = None,
        *,
        cache_version: int = CACHE_VERSION,
    ) -> None:
        """Initialize Zerodha historical data provider.

        Args:
            session: ZerodhaSession for making authenticated requests.
            instrument_master: Optional InstrumentMaster (a default is created).
            normalizer: Optional ZerodhaNormalizer (a default is created).
            cache_dir: Directory for the on-disk cache. A default is used
                when not supplied.
            cache_version: Cache format version.
        """
        self._client = ZerodhaHistoricalDataClient(session, instrument_master)
        self._normalizer = normalizer or ZerodhaNormalizer()
        self._cache = OHLCVCache(cache_dir) if cache_dir is not None else OHLCVCache()
        self._cache_version = cache_version

    @property
    def client(self) -> ZerodhaHistoricalDataClient:
        """Get the underlying broker client."""
        return self._client

    def supported_timeframes(self) -> list[Timeframe]:
        """Get list of supported timeframes for Zerodha."""
        return [
            Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            Timeframe(value=3, unit=TimeframeUnit.MINUTE),
            Timeframe(value=5, unit=TimeframeUnit.MINUTE),
            Timeframe(value=10, unit=TimeframeUnit.MINUTE),
            Timeframe(value=15, unit=TimeframeUnit.MINUTE),
            Timeframe(value=30, unit=TimeframeUnit.MINUTE),
            Timeframe(value=60, unit=TimeframeUnit.MINUTE),
            Timeframe(value=1, unit=TimeframeUnit.HOUR),
            Timeframe(value=1, unit=TimeframeUnit.DAY),
        ]

    async def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime,
        **kwargs: Any,
    ) -> list[OHLCVCandle]:
        """Fetch historical OHLCV candles for a symbol.

        The cache is consulted first and only the intervals that are missing
        are requested from the vendor, so a repeated or overlapping request
        does not re-authenticate or re-download what is already on disk.

        Args:
            symbol: Trading symbol (e.g., "NSE:INFY" or "INFY").
            timeframe: Candle timeframe.
            from_date: Start of the range (inclusive).
            to_date: End of the range (exclusive).
            **kwargs: Provider-specific options:
                - continuous: Whether to fetch continuous data for futures.
                - oi: Whether to include open interest data.

        Returns:
            List of OHLCVCandle objects, sorted by bar time.

        Raises:
            TimeframeNotSupportedError: If the timeframe is not supported.
            ProviderError: If the API request or normalization fails.
        """
        if timeframe not in self.supported_timeframes():
            raise TimeframeNotSupportedError(
                timeframe=str(timeframe),
                provider="zerodha",
                supported=[str(tf) for tf in self.supported_timeframes()],
            )

        if from_date >= to_date:
            raise ProviderError(
                f"from_date must be before to_date: {from_date} >= {to_date}",
                provider="zerodha",
                details={"symbol": symbol, "timeframe": str(timeframe)},
            )

        continuous = bool(kwargs.pop("continuous", False))
        oi = bool(kwargs.pop("oi", False))

        key = CacheKey.create(
            symbol=symbol,
            timeframe=timeframe,
            from_date=from_date,
            to_date=to_date,
            continuous=continuous,
            oi=oi,
            version=self._cache_version,
        )

        covered = self._cache.get_coverage(key)
        missing = missing_intervals(key.from_date, key.to_date, covered)

        if not missing:
            logger.info("Cache hit for %s %s, no vendor request needed", symbol, timeframe)
            return self._cache.get_candles(key)

        for gap_start, gap_end in missing:
            # Each gap is fetched one month at a time, so no single request
            # exceeds the vendor's per-request range limit.
            for segment_start, segment_end in _month_segments(gap_start, gap_end):
                logger.info(
                    "Fetching %s %s from %s to %s",
                    symbol,
                    timeframe,
                    segment_start.isoformat(),
                    segment_end.isoformat(),
                )
                segment_key = CacheKey.create(
                    symbol=symbol,
                    timeframe=timeframe,
                    from_date=segment_start,
                    to_date=segment_end,
                    continuous=continuous,
                    oi=oi,
                    version=self._cache_version,
                )
                await self._fetch_and_store(segment_key, symbol, timeframe, **kwargs)

        return self._cache.get_candles(key)

    async def _fetch_and_store(
        self,
        key: CacheKey,
        symbol: str,
        timeframe: Timeframe,
        **kwargs: Any,
    ) -> None:
        """Fetch one interval from the vendor and store it in the cache."""
        try:
            raw_response = await self._client.get_raw_candles(
                symbol=symbol,
                timeframe=timeframe,
                from_date=key.from_date,
                to_date=key.to_date,
                continuous=key.continuous,
                oi=key.oi,
                **kwargs,
            )
        except (SymbolNotFoundError, AmbiguousSymbolError) as e:
            raise SymbolResolutionError(symbol, str(e)) from e
        except Exception as e:
            raise ProviderError(
                f"API request failed: {e}",
                provider="zerodha",
                details={"symbol": symbol, "timeframe": str(timeframe)},
            ) from e

        try:
            candles = self._normalizer.normalize_candles(raw_response, symbol, timeframe)
        except NormalizationError as e:
            raise ProviderError(
                f"Normalization failed: {e}",
                provider="zerodha",
                details={"symbol": symbol, "timeframe": str(timeframe)},
            ) from e

        try:
            self._cache.store_candles(key, candles)
        except (OSError, ValueError) as e:
            logger.warning("Failed to cache candles for %s: %s", symbol, e)

        logger.info("Received %d candles for %s", len(candles), symbol)

    async def close(self) -> None:
        """Close provider and release resources."""
        # Session is managed externally, just log
        logger.debug("ZerodhaHistoricalDataProvider closed")