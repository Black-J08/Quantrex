"""Shoonya historical data client - raw historical data fetching from the API."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from quantrex.core.broker.shoonya.instrument_master.master import InstrumentMaster
from quantrex.core.broker.shoonya.models.models import ShoonyaInterval
from quantrex.core.broker.shoonya.session.session import ShoonyaSession
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit

logger = logging.getLogger(__name__)

# Endpoints
TP_SERIES_ENDPOINT = "/TPSeries"
EOD_CHART_DATA_ENDPOINT = "/EODChartData"

# Intraday intervals supported by TPSeries (minutes)
INTRADAY_INTERVALS = frozenset({1, 3, 5, 10, 15, 30, 60, 120, 240})


class ShoonyaHistoricalDataClient:
    """Client for fetching raw historical data from the Shoonya API.

    Endpoint selection by interval:
    - Intraday (1m, 3m, 5m, 10m, 15m, 30m, 60m, 120m, 240m): TPSeries
      with exch/token/st/et/intrv parameters (epoch seconds).
    - Daily (1D): EODChartData with sym/from/to parameters (epoch seconds).
    - Unsupported intervals raise ValueError (to be resampled in data layer).

    This client only handles vendor API communication (auth, HTTP, rate limiting).
    Normalization of vendor responses to canonical models is handled by the data layer.
    """

    def __init__(
        self,
        session: ShoonyaSession,
        instrument_master: InstrumentMaster | None = None,
    ):
        """Initialize historical data provider.

        Args:
            session: ShoonyaSession for making authenticated requests
            instrument_master: Optional InstrumentMaster instance (creates default if not provided)
        """
        self._session = session
        self._instrument_master = instrument_master or InstrumentMaster(session)

    def _map_timeframe_to_endpoint(
        self, timeframe: Timeframe
    ) -> tuple[str, ShoonyaInterval]:
        """Map Quantrex Timeframe to Shoonya endpoint and interval.

        Returns:
            Tuple of (endpoint_path, interval) for the given timeframe.

        Raises:
            ValueError: If the timeframe is not supported by Shoonya.
        """
        if timeframe.unit == TimeframeUnit.DAY and timeframe.value == 1:
            return EOD_CHART_DATA_ENDPOINT, ShoonyaInterval.DAY

        if timeframe.unit == TimeframeUnit.MINUTE and timeframe.value in INTRADAY_INTERVALS:
            return TP_SERIES_ENDPOINT, ShoonyaInterval(str(timeframe.value))

        raise ValueError(f"Unsupported timeframe: {timeframe}")

    def _format_epoch_seconds(self, dt: datetime) -> str:
        """Format a datetime as epoch seconds for the Shoonya API.

        Shoonya APIs expect `st`/`et` and `from`/`to` as epoch seconds
        (not milliseconds, not IST wall-clock strings).
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return str(int(dt.timestamp()))

    async def _fetch_tp_series(
        self,
        symbol: str,
        exchange: str,
        token: str,
        interval: ShoonyaInterval,
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        """Fetch intraday candles via TPSeries endpoint.

        Acquires rate-limit capacity from the shared session limiter before
        making the request.
        """
        await self._session.historical_limiter.acquire()

        params: dict[str, Any] = {
            "uid": self._session.client_id,
            "exch": exchange,
            "token": token,
            "st": self._format_epoch_seconds(start),
            "et": self._format_epoch_seconds(end),
            "intrv": interval.value,
        }

        logger.info(
            "Fetching raw TPSeries candles for %s (exch=%s, token=%s, interval=%s) from %s to %s",
            symbol,
            exchange,
            token,
            interval.value,
            start,
            end,
        )

        response = await self._session.post(TP_SERIES_ENDPOINT, json=params)
        data = response.json()

        # TPSeries returns a flat list on success, or an error object with stat: Not_Ok
        if isinstance(data, dict) and data.get("stat") != "Ok":
            raise RuntimeError(f"TPSeries API error: {data.get('emsg', 'Unknown error')}")

        return data

    async def _fetch_eod_chart_data(
        self,
        symbol: str,
        sym: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        """Fetch daily candles via EODChartData endpoint.

        Acquires rate-limit capacity from the shared session limiter before
        making the request.
        """
        await self._session.historical_limiter.acquire()

        params: dict[str, Any] = {
            "uid": self._session.client_id,
            "sym": sym,
            "from": self._format_epoch_seconds(start),
            "to": self._format_epoch_seconds(end),
        }

        logger.info(
            "Fetching raw EODChartData candles for %s (sym=%s) from %s to %s",
            symbol,
            sym,
            start,
            end,
        )

        response = await self._session.post(EOD_CHART_DATA_ENDPOINT, json=params)
        data = response.json()

        # EODChartData returns a flat list on success, or an error object with stat: Not_Ok
        if isinstance(data, dict) and data.get("stat") != "Ok":
            raise RuntimeError(f"EODChartData API error: {data.get('emsg', 'Unknown error')}")

        return data

    async def get_raw_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime,
    ) -> dict[str, Any]:
        """Fetch raw historical candle data from Shoonya API.

        Selects the appropriate endpoint based on the timeframe:
        - Intraday intervals (1m–240m): TPSeries with exch/token/st/et/intrv
        - Daily (1D): EODChartData with sym/from/to

        Returns the raw JSON response from the API without normalization.
        Normalization to canonical models is handled by the data layer.

        Args:
            symbol: Trading symbol (e.g., "NSE:INFY" or "INFY")
            timeframe: Candle timeframe
            from_date: Start date (inclusive)
            to_date: End date (inclusive)

        Returns:
            Raw JSON response from Shoonya API (flat list of candle objects).

        Raises:
            SymbolNotFoundError: If symbol cannot be resolved
            AmbiguousSymbolError: If symbol is ambiguous across exchanges
            ValueError: If timeframe unsupported
            ShoonyaError: If API request fails
        """
        # Resolve symbol to instrument via InstrumentMaster (triggers refresh if needed)
        instrument = await self._instrument_master.resolve_symbol(symbol)
        endpoint, interval = self._map_timeframe_to_endpoint(timeframe)

        if endpoint == TP_SERIES_ENDPOINT:
            # Intraday: use exchange + token
            data = await self._fetch_tp_series(
                symbol=symbol,
                exchange=instrument.exchange,
                token=str(instrument.instrument_token),
                interval=interval,
                start=from_date,
                end=to_date,
            )
        else:
            # Daily: use exchange:tradingsymbol
            sym = f"{instrument.exchange}:{instrument.tradingsymbol}"
            data = await self._fetch_eod_chart_data(
                symbol=symbol,
                sym=sym,
                start=from_date,
                end=to_date,
            )

        return data
