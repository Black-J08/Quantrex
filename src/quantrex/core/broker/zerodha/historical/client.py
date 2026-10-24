"""Zerodha historical data client - raw historical data fetching from the API."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from quantrex.core.broker.zerodha.instrument_master import InstrumentMaster
from quantrex.core.broker.zerodha.models.models import ZerodhaInterval
from quantrex.core.broker.zerodha.session.session import ZerodhaSession
from quantrex.core.broker.zerodha.timezone import IST
from quantrex.core.models import Timeframe, TimeframeUnit

logger = logging.getLogger(__name__)


class ZerodhaHistoricalDataClient:
    """Client for fetching raw historical data from the Zerodha API.

    This client only handles vendor API communication (auth, HTTP, rate limiting).
    Normalization of vendor responses to canonical models is handled by the data layer.
    """

    def __init__(self, session: ZerodhaSession, instrument_master: InstrumentMaster | None = None):
        """Initialize historical data provider.

        Args:
            session: ZerodhaSession for making authenticated requests
            instrument_master: Optional InstrumentMaster instance (creates default if not provided)
        """
        self._session = session
        self._instrument_master = instrument_master or InstrumentMaster(session)

    def _map_timeframe_to_interval(self, timeframe: Timeframe) -> ZerodhaInterval:
        """Map Quantrex Timeframe to Zerodha interval."""
        if timeframe.unit == TimeframeUnit.MINUTE:
            if timeframe.value == 1:
                return ZerodhaInterval.MINUTE
            if timeframe.value == 3:
                return ZerodhaInterval.THREE_MINUTE
            if timeframe.value == 5:
                return ZerodhaInterval.FIVE_MINUTE
            if timeframe.value == 10:
                return ZerodhaInterval.TEN_MINUTE
            if timeframe.value == 15:
                return ZerodhaInterval.FIFTEEN_MINUTE
            if timeframe.value == 30:
                return ZerodhaInterval.THIRTY_MINUTE
            if timeframe.value == 60:
                return ZerodhaInterval.SIXTY_MINUTE
        if timeframe.unit == TimeframeUnit.HOUR and timeframe.value == 1:
            return ZerodhaInterval.SIXTY_MINUTE
        if timeframe.unit == TimeframeUnit.DAY and timeframe.value == 1:
            return ZerodhaInterval.DAY

        raise ValueError(f"Unsupported timeframe: {timeframe}")

    def _format_datetime(self, dt: datetime) -> str:
        """Format a datetime as an IST wall-clock string for the Zerodha API.

        The API interprets `from` and `to` as Indian market time, so the
        instant is converted to IST before its wall clock is rendered. A
        naive datetime is taken to already be IST.
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return dt.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")

    async def get_raw_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime,
        continuous: bool = False,
        oi: bool = False,
    ) -> dict[str, Any]:
        """Fetch raw historical candle data from Zerodha API.
        
        Returns the raw JSON response from the API without normalization.
        Normalization to canonical models is handled by the data layer.

        Args:
            symbol: Trading symbol (e.g., "NSE:INFY" or "INFY")
            timeframe: Candle timeframe
            from_date: Start date (inclusive)
            to_date: End date (inclusive)
            continuous: Whether to fetch continuous data for futures
            oi: Whether to include open interest data

        Returns:
            Raw JSON response from Zerodha API

        Raises:
            SymbolNotFoundError: If symbol cannot be resolved
            AmbiguousSymbolError: If symbol is ambiguous across exchanges
            ValueError: If timeframe unsupported
            ZerodhaError: If API request fails
        """
        # Resolve symbol to instrument token via InstrumentMaster (triggers refresh if needed)
        instrument = await self._instrument_master.resolve_symbol(symbol)
        interval = self._map_timeframe_to_interval(timeframe)

        # Build request parameters
        params: dict[str, Any] = {
            "from": self._format_datetime(from_date),
            "to": self._format_datetime(to_date),
        }
        if continuous:
            params["continuous"] = "1"
        if oi:
            params["oi"] = "1"

        # Make API request
        path = f"/instruments/historical/{instrument.instrument_token}/{interval.value}"
        logger.info(
            "Fetching raw candles for %s (token=%d, interval=%s) from %s to %s",
            symbol,
            instrument.instrument_token,
            interval.value,
            from_date,
            to_date,
        )

        response = await self._session.get(path, params=params, apply_rate_limit=True)
        data = response.json()

        if data.get("status") != "success":
            # Handle 404 for expired contracts - retry with continuous if not already tried
            if response.status_code == 404 and not continuous:
                logger.info("Instrument not found (possibly expired), retrying with continuous=True")
                params["continuous"] = "1"
                response = await self._session.get(path, params=params, apply_rate_limit=True)
                data = response.json()

            if data.get("status") != "success":
                raise RuntimeError(f"API error: {data.get('message', 'Unknown error')}")

        candles_data = data.get("data", {}).get("candles", [])
        logger.info("Received %d raw candles for %s", len(candles_data), symbol)

        return data
