"""Zerodha historical data provider implementation."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from quantrex.core.broker.zerodha.exceptions.exceptions import (
    AmbiguousSymbolError,
    SymbolNotFoundError,
)
from quantrex.core.broker.zerodha.historical import ZerodhaHistoricalDataClient
from quantrex.core.broker.zerodha.instrument_master import InstrumentMaster
from quantrex.core.broker.zerodha.session.session import ZerodhaSession
from quantrex.core.data.cache import OHLCVCache
from quantrex.core.data.cache.cache_key import CacheKey
from quantrex.core.data.exceptions import (
    NormalizationError,
    ProviderError,
    SymbolResolutionError,
    TimeframeNotSupportedError,
)
from quantrex.core.data.historical.provider import HistoricalDataProvider
from quantrex.core.data.normalization import ZerodhaNormalizer
from quantrex.core.models import OHLCVCandle, Timeframe, TimeframeUnit

logger = logging.getLogger(__name__)


class ZerodhaHistoricalDataProvider(HistoricalDataProvider):
    """Historical data provider for Zerodha.

    Owns the full historical-data path: cache lookup, raw fetch through the
    broker client, normalization into canonical models, and validation.
    """

    def __init__(
        self,
        session: ZerodhaSession,
        instrument_master: InstrumentMaster | None = None,
        normalizer: ZerodhaNormalizer | None = None,
        cache: OHLCVCache | None = None,
        *,
        cache_version: int = 1,
    ) -> None:
        """Initialize Zerodha historical data provider.

        Args:
            session: ZerodhaSession for making authenticated requests
            instrument_master: Optional InstrumentMaster instance (creates default if not provided)
            normalizer: Optional ZerodhaNormalizer instance (creates default if not provided)
            cache: Optional OHLCVCache instance (creates default if not provided)
            cache_version: Cache version used for cache keys
        """
        self._client = ZerodhaHistoricalDataClient(session, instrument_master)
        self._normalizer = normalizer or ZerodhaNormalizer()
        self._cache = cache or OHLCVCache()
        self._cache_version = cache_version

    @property
    def client(self) -> ZerodhaHistoricalDataClient:
        """Get the underlying broker client."""
        return self._client

    @property
    def cache(self) -> OHLCVCache:
        """Get the cache instance."""
        return self._cache

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

        Uses the cache-aside pattern: the cache is consulted first, and the
        vendor API is only called on a cache miss.

        Args:
            symbol: Trading symbol (e.g., "NSE:INFY" or "INFY")
            timeframe: Candle timeframe
            from_date: Start date (inclusive)
            to_date: End date (inclusive)
            **kwargs: Provider-specific options:
                - continuous: Whether to fetch continuous data for futures (default: False)
                - oi: Whether to include open interest data (default: False)

        Returns:
            List of OHLCVCandle objects

        Raises:
            TimeframeNotSupportedError: If timeframe is not supported
            ProviderError: If the API request or normalization fails
        """
        # Validate timeframe
        if timeframe not in self.supported_timeframes():
            raise TimeframeNotSupportedError(
                timeframe=str(timeframe),
                provider="zerodha",
                supported=[str(tf) for tf in self.supported_timeframes()],
            )

        # Check cache first - avoids authenticating when data is already cached
        key = CacheKey.create(
            symbol=symbol,
            timeframe=timeframe,
            from_date=from_date,
            to_date=to_date,
            version=self._cache_version,
        )
        cached = self._cache.get(key)
        if cached is not None:
            logger.debug("Cache hit for %s", key.to_filename())
            return cached

        # Cache miss - fetch raw data from the broker client
        logger.debug("Cache miss for %s, fetching from Zerodha", key.to_filename())
        try:
            raw_response = await self._client.get_raw_candles(
                symbol=symbol,
                timeframe=timeframe,
                from_date=from_date,
                to_date=to_date,
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

        # Normalize into canonical models
        try:
            candles = self._normalizer.normalize_candles(raw_response, symbol, timeframe)
        except NormalizationError as e:
            raise ProviderError(
                f"Normalization failed: {e}",
                provider="zerodha",
                details={"symbol": symbol, "timeframe": str(timeframe)},
            ) from e

        # Store in cache
        if candles:
            try:
                self._cache.set(key, candles)
                logger.debug("Cached %d candles for %s", len(candles), key.to_filename())
            except (OSError, ValueError) as e:
                logger.warning("Failed to cache candles for %s: %s", key.to_filename(), e)

        logger.info("Received %d candles for %s", len(candles), symbol)
        return candles

    async def close(self) -> None:
        """Close provider and release resources."""
        # Session is managed externally, just log
        logger.debug("ZerodhaHistoricalDataProvider closed")