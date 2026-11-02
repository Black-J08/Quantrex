#!/usr/bin/env python3
"""Example script demonstrating the Shoonya historical data API (data layer).

This script demonstrates:
1. Creating a ShoonyaSession (researcher-owned lifecycle)
2. Creating a ShoonyaHistoricalDataProvider with just the session
   (InstrumentMaster is created internally by default)
3. Fetching historical OHLCV candles (triggers on-demand instrument master refresh)
4. The lazy authentication flow (triggered on first API request)
5. Closing the session when finished

Requirements:
- Set SHOONYA_CLIENT_ID, SHOONYA_SECRET_KEY, and SHOONYA_REDIRECT_URL in .env file
- Run with: python examples/shoonya_example.py
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from quantrex.core.broker.shoonya.session.session import ShoonyaSession
from quantrex.core.data.historical.shoonya_provider import ShoonyaHistoricalDataProvider
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit

logger = logging.getLogger(__name__)


async def main() -> None:
    """Main example function."""
    logger.info("Starting Shoonya broker example with Instrument Master")

    # Create session (loads credentials from .env)
    # This does NOT trigger authentication yet - it's lazy!
    session = ShoonyaSession()
    logger.info("Created ShoonyaSession (authentication not yet triggered)")

    # Create historical data provider with just the session.
    # InstrumentMaster is created internally by default (on-demand refresh enabled).
    provider = ShoonyaHistoricalDataProvider(session)
    logger.info("Created ShoonyaHistoricalDataProvider (instrument master auto-created)")

    # Define time range (last 7 days)
    to_date = datetime.now(UTC)
    from_date = to_date - timedelta(days=7)

    # Fetch 1-minute candles for INFY
    # THIS is where lazy authentication happens - on first API request
    # Instrument master will also refresh on-demand if cache is missing/stale
    logger.info("Fetching 1-minute candles for NSE:INFY-EQ (this will trigger authentication and instrument master refresh if needed)...")

    try:
        candles = await provider.get_candles(
            symbol="NSE:INFY-EQ",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=from_date,
            to_date=to_date,
        )

        logger.info("Successfully fetched %d candles", len(candles))

        # Print first 5 candles
        for i, candle in enumerate(candles[:5]):
            logger.info(
                "Candle %d: %s O=%.2f H=%.2f L=%.2f C=%.2f V=%.0f",
                i + 1,
                candle.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
            )

        # Fetch daily candles for INFY
        logger.info("Fetching daily candles for NSE:INFY-EQ...")
        daily_candles = await provider.get_candles(
            symbol="NSE:INFY-EQ",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.DAY),
            from_date=from_date - timedelta(days=30),  # Last 30 days
            to_date=to_date,
        )

        logger.info("Successfully fetched %d daily candles", len(daily_candles))

        for i, candle in enumerate(daily_candles[-5:]):  # Last 5 days
            logger.info(
                "Daily %d: %s O=%.2f H=%.2f L=%.2f C=%.2f V=%.0f",
                i + 1,
                candle.timestamp.strftime("%Y-%m-%d"),
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
            )
            print(candle)

        # Demonstrate tradingsymbol-only resolution (works across exchanges)
        logger.info("Fetching candles using tradingsymbol only (INFY-EQ)...")
        candles_ts = await provider.get_candles(
            symbol="INFY-EQ",  # Will resolve to NSE:INFY-EQ if unique
            timeframe=Timeframe(value=1, unit=TimeframeUnit.DAY),
            from_date=from_date - timedelta(days=30),
            to_date=to_date,
        )
        logger.info("Successfully fetched %d candles for INFY-EQ", len(candles_ts))

    except Exception as e:
        logger.error("Error fetching candles: %s", e)
        raise
    finally:
        # Clean up
        await session.close()
        logger.info("Session closed")

    logger.info("Example completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
