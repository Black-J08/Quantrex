"""Zerodha historical data provider implementation."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from quantrex.core.broker.exceptions.exceptions import (
    AmbiguousSymbolError,
    SymbolNotFoundError,
)
from quantrex.core.broker.zerodha.historical.client import ZerodhaHistoricalDataClient
from quantrex.core.broker.zerodha.instrument_master.master import InstrumentMaster
from quantrex.core.broker.zerodha.session.session import ZerodhaSession
from quantrex.core.data.cache.cache_key import CacheKey
from quantrex.core.data.cache.ohlcv_cache import OHLCVCache, missing_intervals
from quantrex.core.data.exceptions.exceptions import (
    NormalizationError,
    ProviderError,
    SymbolResolutionError,
    TimeframeNotSupportedError,
)
from quantrex.core.data.historical.provider import HistoricalDataProvider
from quantrex.core.data.normalization.zerodha import ZerodhaNormalizer
from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit

logger = logging.getLogger(__name__)

#: Cache format version. Bumped when the on-disk layout or the stored bar
#: times change, so that files written by an older version are ignored.
CACHE_VERSION = 2


class ZerodhaHistoricalDataProvider(HistoricalDataProvider):
    """Historical data provider for Zerodha.

    Owns the full historical-data path: working out which intervals are
    already cached, fetching only the missing ones through the broker client,
    normalizing into canonical models, and storing the result.

    Resource ownership:
        - The researcher creates and owns the ``ZerodhaSession`` and is
          responsible for closing it (``await session.close()``) when done.
          This provider does *not* close the session.
        - ``InstrumentMaster`` is created internally by default when not
          supplied, and is owned by this provider.
        - ``ZerodhaNormalizer`` and the on-disk ``OHLCVCache`` are owned by
          this provider.

    Example::

        session = ZerodhaSession()
        provider = ZerodhaHistoricalDataProvider(session)
        try:
            candles = await provider.get_candles(...)
        finally:
            await session.close()
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
            session: ZerodhaSession for making authenticated requests. The
                researcher owns this session and is responsible for closing it.
            instrument_master: Optional InstrumentMaster (a default is created
                internally and owned by this provider).
            normalizer: Optional ZerodhaNormalizer (a default is created).
            cache_dir: Directory for the on-disk cache. A default is used
                when not supplied.
            cache_version: Cache format version.
        """
        self._session = session
        self._client = ZerodhaHistoricalDataClient(session, instrument_master)
        self._normalizer = normalizer or ZerodhaNormalizer()
        self._cache = OHLCVCache(cache_dir) if cache_dir is not None else OHLCVCache()
        self._cache_version = cache_version

    @property
    def session(self) -> ZerodhaSession:
        """Get the underlying broker session.

        The researcher owns the session lifecycle and is responsible for
        closing it when done. This provider does not close the session.
        """
        return self._session

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
            return self._cache.get_cached_candles(key)

        for gap_start, gap_end in missing:
            # The client splits each missing interval into month-aligned
            # segments internally and acquires rate-limit capacity before
            # each request.
            logger.info(
                "Fetching %s %s from %s to %s",
                symbol,
                timeframe,
                gap_start.isoformat(),
                gap_end.isoformat(),
            )
            segment_key = CacheKey.create(
                symbol=symbol,
                timeframe=timeframe,
                from_date=gap_start,
                to_date=gap_end,
                continuous=continuous,
                oi=oi,
                version=self._cache_version,
            )
            await self._fetch_and_store(segment_key, symbol, timeframe, **kwargs)

        return self._cache.get_cached_candles(key)

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
            raise ProviderError(
                f"Cache write failed for {symbol}",
                provider="zerodha",
                details={"symbol": symbol, "timeframe": str(timeframe)},
            ) from e

        logger.info("Received %d candles for %s", len(candles), symbol)

    async def close(self) -> None:
        """Close provider and release resources.

        This provider does *not* close the underlying ``ZerodhaSession`` —
        session lifecycle is owned by the researcher. Call
        ``await session.close()`` separately when finished.
        """
        logger.debug("ZerodhaHistoricalDataProvider closed (session managed externally)")