"""Abstract base class for vendor response normalizers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe


class Normalizer(ABC):
    """Abstract base class for normalizing vendor responses to canonical models.

    Each vendor implementation provides a concrete normalizer that converts
    raw vendor API responses into Quantrex canonical models.
    """

    @abstractmethod
    def normalize_candles(
        self,
        raw_response: Any,
        symbol: str,
        timeframe: Timeframe,
    ) -> list[OHLCVCandle]:
        """Normalize a raw vendor candle response to a list of canonical candles.

        Args:
            raw_response: Raw response from the vendor API.
            symbol: Trading symbol (e.g., "NSE:INFY").
            timeframe: Candle timeframe.

        Returns:
            List of normalized OHLCVCandle objects.

        Raises:
            NormalizationError: If the response cannot be normalized.
        """
        ...
