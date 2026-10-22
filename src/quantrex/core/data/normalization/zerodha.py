"""Zerodha-specific normalizer for vendor responses."""

from __future__ import annotations

import logging
from typing import Any

from quantrex.core.data.exceptions import NormalizationError
from quantrex.core.data.normalization.base import Normalizer
from quantrex.core.models import OHLCVCandle, RawCandle, Timeframe

logger = logging.getLogger(__name__)


class ZerodhaNormalizer(Normalizer):
    """Normalizes Zerodha API responses to Quantrex canonical models."""

    def normalize_candles(
        self,
        raw_response: Any,
        symbol: str,
        timeframe: Timeframe,
    ) -> list[OHLCVCandle]:
        """Normalize Zerodha historical data response to OHLCVCandle list.
        
        Args:
            raw_response: Raw JSON response from Zerodha historical API
            symbol: Trading symbol (e.g., "NSE:INFY")
            timeframe: Candle timeframe
            
        Returns:
            List of normalized OHLCVCandle objects
            
        Raises:
            NormalizationError: If normalization fails
        """
        if not isinstance(raw_response, dict):
            raise NormalizationError(
                f"Expected dict response, got {type(raw_response).__name__}",
                vendor="zerodha",
                raw_data=raw_response,
            )

        if raw_response.get("status") != "success":
            raise NormalizationError(
                f"API error: {raw_response.get('message', 'Unknown error')}",
                vendor="zerodha",
                raw_data=raw_response,
            )

        candles_data = raw_response.get("data", {}).get("candles", [])
        if not isinstance(candles_data, list):
            raise NormalizationError(
                f"Expected candles list, got {type(candles_data).__name__}",
                vendor="zerodha",
                raw_data=raw_response,
            )

        candles = []
        for i, candle_data in enumerate(candles_data):
            try:
                raw_candle = RawCandle.from_api_response(candle_data)
                ohlcv = self._raw_to_ohlcv(raw_candle, symbol, timeframe)
                candles.append(ohlcv)
            except (ValueError, IndexError, TypeError) as e:
                logger.warning("Failed to parse candle %d: %s, data: %s", i, e, candle_data)
                continue

        logger.debug("Normalized %d candles for %s (%s)", len(candles), symbol, timeframe)
        return candles

    def normalize_tick(
        self,
        raw_response: Any,
        symbol: str,
    ) -> Any:
        """Normalize Zerodha tick response to Tick.
        
        Not yet implemented - placeholder for future tick data support.
        
        Args:
            raw_response: Raw response from Zerodha tick API
            symbol: Trading symbol
            
        Returns:
            Normalized Tick object
            
        Raises:
            NormalizationError: If normalization fails
        """
        raise NotImplementedError("Tick normalization not yet implemented for Zerodha")

    def _raw_to_ohlcv(self, raw: RawCandle, symbol: str, timeframe: Timeframe) -> OHLCVCandle:
        """Convert RawCandle to OHLCVCandle."""
        return OHLCVCandle(
            symbol=symbol,
            timeframe=timeframe,
            open=raw.open,
            high=raw.high,
            low=raw.low,
            close=raw.close,
            volume=raw.volume,
        )