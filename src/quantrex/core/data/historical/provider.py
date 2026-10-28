"""Abstract base class for historical data providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Self

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe


class HistoricalDataProvider(ABC):
    """Abstract base class for historical market data providers.
    
    Provides a vendor-agnostic interface for fetching historical OHLCV candles.
    Concrete implementations handle vendor-specific API communication and normalization.
    """

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime,
        **kwargs: Any,
    ) -> list[OHLCVCandle]:
        """Fetch historical OHLCV candles for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., "NSE:INFY")
            timeframe: Candle timeframe
            from_date: Start date (inclusive)
            to_date: End date (inclusive)
            **kwargs: Provider-specific options (e.g., continuous, oi)
            
        Returns:
            List of OHLCVCandle objects
            
        Raises:
            SymbolResolutionError: If symbol cannot be resolved
            TimeframeNotSupportedError: If timeframe is not supported
            ProviderError: If provider encounters an error
        """
        ...

    @abstractmethod
    def supported_timeframes(self) -> list[Timeframe]:
        """Get list of supported timeframes for this provider.
        
        Returns:
            List of supported Timeframe objects
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close provider and release resources."""
        ...

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()