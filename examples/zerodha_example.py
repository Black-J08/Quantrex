#!/usr/bin/env python3
"""Example script demonstrating Zerodha broker usage with Instrument Master.

This script demonstrates:
1. Creating a ZerodhaSession
2. Creating an InstrumentMaster for on-demand instrument resolution
3. Fetching historical OHLCV candles (triggers on-demand instrument master refresh)
4. The lazy authentication flow (triggered on first API request)

Requirements:
- Set ZERODHA_API_KEY, ZERODHA_API_SECRET, and ZERODHA_REDIRECT_URL in .env file
- Run with: python examples/zerodha_example.py
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from quantrex.core.broker.zerodha import (
    ZerodhaSession,
    ZerodhaHistoricalDataProvider,
    InstrumentMaster,
)
from quantrex.core.models import Timeframe, TimeframeUnit

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Main example function."""
    logger.info("Starting Zerodha broker example with Instrument Master")

    # Create session (loads credentials from .env)
    # This does NOT trigger authentication yet - it's lazy!
    session = ZerodhaSession()
    logger.info("Created ZerodhaSession (authentication not yet triggered)")

    # Create instrument master for on-demand instrument resolution
    # This will download and cache the instrument master on first use
    instrument_master = InstrumentMaster(session)
    logger.info("Created InstrumentMaster (on-demand refresh enabled)")

    # Create historical data provider with instrument master
    provider = ZerodhaHistoricalDataProvider(session, instrument_master)
    logger.info("Created ZerodhaHistoricalDataProvider")

    # Show instrument master stats
    stats = instrument_master.get_stats()
    logger.info("Instrument master stats: %s", stats)

    # Define time range (last 7 days)
    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=7)

    # Fetch 1-minute candles for INFY
    # THIS is where lazy authentication happens - on first API request
    # Instrument master will also refresh on-demand if cache is missing/stale
    logger.info("Fetching 1-minute candles for NSE:INFY (this will trigger authentication and instrument master refresh if needed)...")

    try:
        candles = await provider.get_candles(
            symbol="NSE:INFY",
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

        # Fetch daily candles for NIFTY 50
        logger.info("Fetching daily candles for NSE:NIFTY 50...")
        daily_candles = await provider.get_candles(
            symbol="NSE:NIFTY 50",
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

        # Demonstrate tradingsymbol-only resolution (works across exchanges)
        logger.info("Fetching candles using tradingsymbol only (INFY)...")
        candles_ts = await provider.get_candles(
            symbol="INFY",  # Will resolve to NSE:INFY if unique
            timeframe=Timeframe(value=1, unit=TimeframeUnit.DAY),
            from_date=from_date - timedelta(days=30),
            to_date=to_date,
        )
        logger.info("Successfully fetched %d candles for INFY", len(candles_ts))

        # Show updated instrument master stats
        stats = instrument_master.get_stats()
        logger.info("Updated instrument master stats: %s", stats)

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


if __name__ == "__main__":
    asyncio.run(main())
