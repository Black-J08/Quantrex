"""Zerodha historical data provider - fetches OHLCV candles."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from quantrex.core.broker.zerodha.instrument_master import InstrumentMaster
from quantrex.core.broker.zerodha.models.models import RawCandle, ZerodhaInterval
from quantrex.core.broker.zerodha.session.session import ZerodhaSession
from quantrex.core.models import OHLCVCandle, Timeframe, TimeframeUnit

logger = logging.getLogger(__name__)


class ZerodhaHistoricalDataProvider:
    """Provider for fetching historical OHLCV candles from Zerodha."""

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
        """Format datetime for Zerodha API (yyyy-mm-dd hh:mm:ss)."""
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    async def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime,
        continuous: bool = False,
        oi: bool = False,
    ) -> list[OHLCVCandle]:
        """Fetch historical OHLCV candles for a symbol.

        Args:
            symbol: Trading symbol (e.g., "NSE:INFY" or "INFY")
            timeframe: Candle timeframe
            from_date: Start date (inclusive)
            to_date: End date (inclusive)
            continuous: Whether to fetch continuous data for futures
            oi: Whether to include open interest data

        Returns:
            List of OHLCVCandle objects

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
            "Fetching candles for %s (token=%d, interval=%s) from %s to %s",
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
        logger.info("Received %d candles for %s", len(candles_data), symbol)

        # Parse candles
        candles = []
        for candle_data in candles_data:
            try:
                raw_candle = RawCandle.from_api_response(candle_data)
                ohlcv = self._raw_to_ohlcv(raw_candle, symbol, timeframe)
                candles.append(ohlcv)
            except (ValueError, IndexError, TypeError) as e:
                logger.warning("Failed to parse candle: %s, data: %s", e, candle_data)
                continue

        return candles

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
