"""Abstract base class for vendor response normalizers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from quantrex.core.models import OHLCVCandle, Timeframe


class Normalizer(ABC):
    """Abstract base class for normalizing vendor responses to canonical models.
    
    Each vendor implementation should provide a concrete normalizer that converts
    raw vendor API responses into Quantrex canonical models (OHLCVCandle, Tick, etc.).
    """

    @abstractmethod
    def normalize_candles(
        self,
        raw_response: Any,
        symbol: str,
        timeframe: Timeframe,
    ) -> list[OHLCVCandle]:
        """Normalize raw vendor candle response to OHLCVCandle list.
        
        Args:
            raw_response: Raw response from vendor API (JSON dict, list, etc.)
            symbol: Trading symbol (e.g., "NSE:INFY")
            timeframe: Candle timeframe
            
        Returns:
            List of normalized OHLCVCandle objects
            
        Raises:
            NormalizationError: If normalization fails
        """
        ...

    @abstractmethod
    def normalize_tick(
        self,
        raw_response: Any,
        symbol: str,
    ) -> Any:
        """Normalize raw vendor tick response to Tick.
        
        Args:
            raw_response: Raw response from vendor API
            symbol: Trading symbol
            
        Returns:
            Normalized Tick object
            
        Raises:
            NormalizationError: If normalization fails
        """
        ...

    def validate_candle(self, candle: OHLCVCandle) -> None:
        """Validate a normalized candle.
        
        Can be overridden by subclasses for vendor-specific validation.
        
        Args:
            candle: Normalized candle to validate
            
        Raises:
            DataValidationError: If validation fails
        """
        # Base validation is done by OHLCVCandle.__post_init__
