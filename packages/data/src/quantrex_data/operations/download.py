"""Data download operations for Quantrex."""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from quantrex_core.logging import get_logger
from quantrex_core.protocols import DataProvider

logger = get_logger(__name__)


class DataDownloader:
    """Downloads missing data via providers."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def download_missing(
        self,
        provider: DataProvider,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1M",
    ) -> List[Dict[str, Any]]:
        """Download missing data for a symbol/timeframe.

        Args:
            provider: DataProvider instance (Dhan, Zerodha, etc.)
            symbol: Trading symbol
            start: Start datetime
            end: End datetime
            timeframe: Timeframe interval

        Returns:
            List of normalized data rows.
        """
        logger.info("Downloading data for %s %s from %s to %s", symbol, timeframe, start, end)

        try:
            # Provider-specific download logic
            if hasattr(provider, 'fetch_range'):
                raw_data = provider.fetch_range(symbol, timeframe, start, end)
            else:
                # Fallback to basic fetch
                raw_data = provider.fetch(timeframe=timeframe)

            if not raw_data:
                logger.warning("No data returned from provider for %s", symbol)
                return []

            # Normalize data (provider-specific)
            normalized = self._normalize_data(raw_data, symbol, timeframe)
            logger.info("Downloaded %d rows for %s", len(normalized), symbol)
            return normalized

        except Exception as e:
            logger.exception("Failed to download data for %s: %s", symbol, e)
            raise

    def _normalize_data(
        self,
        raw_data: Any,
        symbol: str,
        timeframe: str,
    ) -> List[Dict[str, Any]]:
        """Normalize raw provider data to standard format.

        This is a placeholder - actual normalization happens in adapters.
        """
        # This would be implemented per provider
        # For now, return as-is if already in correct format
        if isinstance(raw_data, list) and raw_data and isinstance(raw_data[0], dict):
            return raw_data
        return []


def download_dhan_data(
    symbol: str,
    start: datetime,
    end: datetime,
    timeframe: str = "1M",
    api_key: Optional[str] = None,
    access_token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Download data from Dhan provider.

    Args:
        symbol: Trading symbol
        start: Start datetime
        end: End datetime
        timeframe: Timeframe interval
        api_key: Dhan API key (or from env DHAN_API_KEY)
        access_token: Dhan access token (or from env DHAN_ACCESS_TOKEN)

    Returns:
        List of normalized data rows.
    """
    # Import here to avoid circular dependency
    from quantrex_data.providers.dhan_provider import DhanDataProvider

    api_key = api_key or os.getenv("DHAN_API_KEY")
    access_token = access_token or os.getenv("DHAN_ACCESS_TOKEN")

    if not api_key or not access_token:
        raise ValueError("Dhan credentials required (api_key, access_token)")

    provider = DhanDataProvider(
        api_key=api_key,
        access_token=access_token,
    )

    try:
        # Dhan provider specific fetch
        raw_data = provider.fetch_range(symbol, timeframe, start, end)
        return raw_data
    finally:
        provider.close()


def download_zerodha_data(
    symbol: str,
    start: datetime,
    end: datetime,
    timeframe: str = "1M",
    api_key: Optional[str] = None,
    access_token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Download data from Zerodha provider.

    Args:
        symbol: Trading symbol
        start: Start datetime
        end: End datetime
        timeframe: Timeframe interval
        api_key: Zerodha API key (or from env ZERODHA_API_KEY)
        access_token: Zerodha access token (or from env ZERODHA_ACCESS_TOKEN)

    Returns:
        List of normalized data rows.
    """
    from quantrex_data.providers.zerodha_provider import ZerodhaDataProvider

    api_key = api_key or os.getenv("ZERODHA_API_KEY")
    access_token = access_token or os.getenv("ZERODHA_ACCESS_TOKEN")

    if not api_key or not access_token:
        raise ValueError("Zerodha credentials required (api_key, access_token)")

    provider = ZerodhaDataProvider(
        api_key=api_key,
        access_token=access_token,
    )

    try:
        raw_data = provider.fetch_range(symbol, timeframe, start, end)
        return raw_data
    finally:
        provider.close()