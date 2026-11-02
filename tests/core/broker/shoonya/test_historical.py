"""Tests for ShoonyaHistoricalDataClient."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantrex.core.broker.shoonya.historical.client import ShoonyaHistoricalDataClient
from quantrex.core.broker.shoonya.instrument_master.master import InstrumentMaster
from quantrex.core.broker.shoonya.instrument_master.models import ShoonyaInstrument
from quantrex.core.broker.shoonya.models.models import ShoonyaInterval
from quantrex.core.broker.shoonya.session.session import ShoonyaSession
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit


class TestShoonyaHistoricalDataClient:
    """Tests for ShoonyaHistoricalDataClient."""

    def test_init_with_default_instrument_master(self) -> None:
        """Test initialization creates default InstrumentMaster."""
        mock_session = MagicMock(spec=ShoonyaSession)
        client = ShoonyaHistoricalDataClient(mock_session)

        assert client._instrument_master is not None
        assert isinstance(client._instrument_master, InstrumentMaster)

    def test_init_with_custom_instrument_master(self) -> None:
        """Test initialization with custom InstrumentMaster."""
        mock_session = MagicMock(spec=ShoonyaSession)
        mock_master = MagicMock(spec=InstrumentMaster)
        client = ShoonyaHistoricalDataClient(mock_session, mock_master)

        assert client._instrument_master is mock_master

    def test_map_timeframe_to_endpoint_intraday(self) -> None:
        """Test mapping intraday timeframes to TPSeries endpoint."""
        mock_session = MagicMock(spec=ShoonyaSession)
        client = ShoonyaHistoricalDataClient(mock_session)

        for value in [1, 3, 5, 10, 15, 30, 60, 120, 240]:
            endpoint, interval = client._map_timeframe_to_endpoint(
                Timeframe(value=value, unit=TimeframeUnit.MINUTE)
            )
            assert endpoint == "/TPSeries"
            assert interval.value == str(value)

    def test_map_timeframe_to_endpoint_daily(self) -> None:
        """Test mapping daily timeframe to EODChartData endpoint."""
        mock_session = MagicMock(spec=ShoonyaSession)
        client = ShoonyaHistoricalDataClient(mock_session)

        endpoint, interval = client._map_timeframe_to_endpoint(
            Timeframe(value=1, unit=TimeframeUnit.DAY)
        )
        assert endpoint == "/EODChartData"
        assert interval == ShoonyaInterval.DAY

    def test_map_timeframe_to_endpoint_unsupported(self) -> None:
        """Test mapping unsupported timeframe raises ValueError."""
        mock_session = MagicMock(spec=ShoonyaSession)
        client = ShoonyaHistoricalDataClient(mock_session)

        with pytest.raises(ValueError, match="Unsupported timeframe"):
            client._map_timeframe_to_endpoint(Timeframe(value=2, unit=TimeframeUnit.MINUTE))

        with pytest.raises(ValueError, match="Unsupported timeframe"):
            client._map_timeframe_to_endpoint(Timeframe(value=1, unit=TimeframeUnit.HOUR))

        with pytest.raises(ValueError, match="Unsupported timeframe"):
            client._map_timeframe_to_endpoint(Timeframe(value=1, unit=TimeframeUnit.WEEK))

    def test_format_epoch_seconds(self) -> None:
        """Test datetime formatting as epoch seconds."""
        mock_session = MagicMock(spec=ShoonyaSession)
        client = ShoonyaHistoricalDataClient(mock_session)

        dt = datetime(2024, 1, 15, 9, 15, 0, tzinfo=UTC)
        epoch = client._format_epoch_seconds(dt)
        assert epoch == str(int(dt.timestamp()))

    def test_format_epoch_seconds_naive_assumes_utc(self) -> None:
        """Test naive datetime is treated as UTC."""
        mock_session = MagicMock(spec=ShoonyaSession)
        client = ShoonyaHistoricalDataClient(mock_session)

        naive = datetime(2024, 1, 15, 9, 15, 0, tzinfo=UTC)
        epoch = client._format_epoch_seconds(naive)
        assert epoch == str(int(naive.timestamp()))

    @pytest.mark.asyncio
    async def test_get_raw_candles_intraday_success(self) -> None:
        """Test successful intraday raw candle fetching via TPSeries."""
        mock_session = MagicMock(spec=ShoonyaSession)
        mock_session.client_id = "ABC123"
        mock_session.historical_limiter.acquire = AsyncMock()

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "time": "07-12-2022 09:15:00",
                "into": "255.00",
                "inth": "255.65",
                "intl": "254.65",
                "intc": "255.65",
                "intv": "146",
                "v": "146",
                "oi": "0",
            },
        ]
        mock_session.post = AsyncMock(return_value=mock_response)

        from_date = datetime(2024, 1, 15, 9, 15, tzinfo=UTC)
        to_date = datetime(2024, 1, 15, 9, 16, tzinfo=UTC)

        mock_instrument = ShoonyaInstrument(
            instrument_token="2885",
            exchange_token="1594",
            tradingsymbol="INFY",
            name="INFOSYS",
            last_price=Decimal(0),
            expiry=None,
            strike=None,
            tick_size=Decimal("0.05"),
            lot_size=1,
            instrument_type="EQ",
            segment="NSE",
            exchange="NSE",
        )
        mock_master = AsyncMock(spec=InstrumentMaster)
        mock_master.resolve_symbol = AsyncMock(return_value=mock_instrument)
        client = ShoonyaHistoricalDataClient(mock_session, mock_master)

        raw_data = await client.get_raw_candles(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=from_date,
            to_date=to_date,
        )

        assert isinstance(raw_data, list)
        assert len(raw_data) == 1
        # Verify instrument master was called
        mock_master.resolve_symbol.assert_called_once_with("NSE:INFY")
        # Verify rate limiter was acquired
        mock_session.historical_limiter.acquire.assert_awaited_once()
        # Verify TPSeries was called with correct params
        call_args = mock_session.post.call_args
        assert call_args.args[0] == "/TPSeries"
        params = call_args.kwargs["json"]
        assert params["uid"] == "ABC123"
        assert params["exch"] == "NSE"
        assert params["token"] == "2885"
        assert params["intrv"] == "1"

    @pytest.mark.asyncio
    async def test_get_raw_candles_daily_success(self) -> None:
        """Test successful daily raw candle fetching via EODChartData."""
        mock_session = MagicMock(spec=ShoonyaSession)
        mock_session.client_id = "ABC123"
        mock_session.historical_limiter.acquire = AsyncMock()

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "time": "05-DEC-2022",
                "into": "2145.00",
                "inth": "2168.90",
                "intl": "2130.25",
                "intc": "2160.10",
                "v": "412300",
                "oi": "0",
            },
        ]
        mock_session.post = AsyncMock(return_value=mock_response)

        from_date = datetime(2024, 1, 15, tzinfo=UTC)
        to_date = datetime(2024, 1, 20, tzinfo=UTC)

        mock_instrument = ShoonyaInstrument(
            instrument_token="2885",
            exchange_token="1594",
            tradingsymbol="INFY",
            name="INFOSYS",
            last_price=Decimal(0),
            expiry=None,
            strike=None,
            tick_size=Decimal("0.05"),
            lot_size=1,
            instrument_type="EQ",
            segment="NSE",
            exchange="NSE",
        )
        mock_master = AsyncMock(spec=InstrumentMaster)
        mock_master.resolve_symbol = AsyncMock(return_value=mock_instrument)
        client = ShoonyaHistoricalDataClient(mock_session, mock_master)

        raw_data = await client.get_raw_candles(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.DAY),
            from_date=from_date,
            to_date=to_date,
        )

        assert isinstance(raw_data, list)
        assert len(raw_data) == 1
        # Verify EODChartData was called with correct params
        call_args = mock_session.post.call_args
        assert call_args.args[0] == "/EODChartData"
        params = call_args.kwargs["json"]
        assert params["uid"] == "ABC123"
        assert params["sym"] == "NSE:INFY"

    @pytest.mark.asyncio
    async def test_get_raw_candles_api_error(self) -> None:
        """Test handling API error response."""
        mock_session = MagicMock(spec=ShoonyaSession)
        mock_session.client_id = "ABC123"
        mock_session.historical_limiter.acquire = AsyncMock()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "stat": "Not_Ok",
            "emsg": "Invalid token",
        }
        mock_session.post = AsyncMock(return_value=mock_response)

        from_date = datetime(2024, 1, 15, tzinfo=UTC)
        to_date = datetime(2024, 1, 16, tzinfo=UTC)

        mock_instrument = ShoonyaInstrument(
            instrument_token="2885",
            exchange_token="1594",
            tradingsymbol="INFY",
            name="INFOSYS",
            last_price=Decimal(0),
            expiry=None,
            strike=None,
            tick_size=Decimal("0.05"),
            lot_size=1,
            instrument_type="EQ",
            segment="NSE",
            exchange="NSE",
        )
        mock_master = AsyncMock(spec=InstrumentMaster)
        mock_master.resolve_symbol = AsyncMock(return_value=mock_instrument)
        client = ShoonyaHistoricalDataClient(mock_session, mock_master)

        with pytest.raises(RuntimeError, match="TPSeries API error"):
            await client.get_raw_candles(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=from_date,
                to_date=to_date,
            )

    @pytest.mark.asyncio
    async def test_get_raw_candles_symbol_not_found(self) -> None:
        """Test handling symbol not found error."""
        from quantrex.core.broker.exceptions.exceptions import SymbolNotFoundError

        mock_session = MagicMock(spec=ShoonyaSession)
        mock_master = AsyncMock(spec=InstrumentMaster)
        mock_master.resolve_symbol = AsyncMock(side_effect=SymbolNotFoundError("NSE:UNKNOWN"))
        client = ShoonyaHistoricalDataClient(mock_session, mock_master)

        from_date = datetime(2024, 1, 15, tzinfo=UTC)
        to_date = datetime(2024, 1, 16, tzinfo=UTC)

        with pytest.raises(SymbolNotFoundError):
            await client.get_raw_candles(
                symbol="NSE:UNKNOWN",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=from_date,
                to_date=to_date,
            )

    @pytest.mark.asyncio
    async def test_get_raw_candles_ambiguous_symbol(self) -> None:
        """Test handling ambiguous symbol error."""
        from quantrex.core.broker.exceptions.exceptions import AmbiguousSymbolError

        mock_session = MagicMock(spec=ShoonyaSession)
        mock_master = AsyncMock(spec=InstrumentMaster)
        mock_master.resolve_symbol = AsyncMock(side_effect=AmbiguousSymbolError("INFY", []))
        client = ShoonyaHistoricalDataClient(mock_session, mock_master)

        from_date = datetime(2024, 1, 15, tzinfo=UTC)
        to_date = datetime(2024, 1, 16, tzinfo=UTC)

        with pytest.raises(AmbiguousSymbolError):
            await client.get_raw_candles(
                symbol="INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=from_date,
                to_date=to_date,
            )
