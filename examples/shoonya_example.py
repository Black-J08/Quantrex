#!/usr/bin/env python3
"""Example script demonstrating the Shoonya historical data API (broker layer).

This script demonstrates:
1. Creating a ShoonyaSession (researcher-owned lifecycle)
2. Creating a ShoonyaHistoricalDataClient with just the session
   (InstrumentMaster is created internally by default)
3. Fetching raw historical OHLCV candles (triggers on-demand instrument master refresh)
4. The lazy authentication flow (triggered on first API request)
5. Closing the session when finished

Requirements:
- Set SHOONYA_CLIENT_ID, SHOONYA_SECRET_KEY, and SHOONYA_REDIRECT_URL in .env file
- Run with: python examples/shoonya_example.py

Note: This example uses the broker layer directly. Raw candle data is returned
as-is from the Shoonya API (flat list of candle dicts). Normalization into
canonical OHLCVCandle models is handled by the data layer (not yet implemented
for Shoonya).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from quantrex.core.broker.shoonya.historical.client import ShoonyaHistoricalDataClient
from quantrex.core.broker.shoonya.session.session import ShoonyaSession
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit

logger = logging.getLogger(__name__)


async def main() -> None:
    """Main example function."""
    logger.info("Starting Shoonya broker example with Instrument Master")

    # Create session (loads credentials from .env)
    # This does NOT trigger authentication yet - it's lazy!
    session = ShoonyaSession()
    logger.info("Created ShoonyaSession (authentication not yet triggered)")

    # Create historical data client with just the session.
    # InstrumentMaster is created internally by default (on-demand refresh enabled).
    client = ShoonyaHistoricalDataClient(session)
    logger.info("Created ShoonyaHistoricalDataClient (instrument master auto-created)")

    # Define time range (last 7 days)
    to_date = datetime.now(UTC)
    from_date = to_date - timedelta(days=7)

    # Fetch 1-minute candles for INFY via TPSeries
    # THIS is where lazy authentication happens - on first API request
    # Instrument master will also refresh on-demand if cache is missing/stale
    logger.info(
        "Fetching 1-minute candles for NSE:INFY-EQ via TPSeries "
        "(this will trigger authentication and instrument master refresh if needed)..."
    )

    try:
        candles = await client.get_raw_candles(
            symbol="NSE:INFY-EQ",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=from_date,
            to_date=to_date,
        )

        logger.info("Successfully fetched %d candles", len(candles))

        # Print first 5 candles
        for i, candle in enumerate(candles[:5]):
            logger.info(
                "Candle %d: time=%s O=%s H=%s L=%s C=%s V=%s",
                i + 1,
                candle.get("time", "N/A"),
                candle.get("into", "N/A"),
                candle.get("inth", "N/A"),
                candle.get("intl", "N/A"),
                candle.get("intc", "N/A"),
                candle.get("v", "N/A"),
            )

    except Exception as e:
        logger.error("Error fetching intraday candles: %s", e)
        raise
    finally:
        # Clean up
        await session.close()
        logger.info("Session closed")

    logger.info("Example completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
