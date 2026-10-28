"""Tests for ZerodhaHistoricalDataClient."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantrex.core.broker.zerodha.historical.client import ZerodhaHistoricalDataClient
from quantrex.core.broker.zerodha.instrument_master.master import InstrumentMaster
from quantrex.core.broker.zerodha.instrument_master.models import ZerodhaInstrument
from quantrex.core.broker.zerodha.session.session import ZerodhaSession
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit


class TestZerodhaHistoricalDataClient:
    """Tests for ZerodhaHistoricalDataClient."""

    def test_init_with_default_instrument_master(self) -> None:
        """Test initialization creates default InstrumentMaster."""
        mock_session = MagicMock(spec=ZerodhaSession)
        client = ZerodhaHistoricalDataClient(mock_session)

        assert client._instrument_master is not None
        assert isinstance(client._instrument_master, InstrumentMaster)

    def test_init_with_custom_instrument_master(self) -> None:
        """Test initialization with custom InstrumentMaster."""
        mock_session = MagicMock(spec=ZerodhaSession)
        mock_master = MagicMock(spec=InstrumentMaster)
        client = ZerodhaHistoricalDataClient(mock_session, mock_master)

        assert client._instrument_master is mock_master

    def test_map_timeframe_to_interval_minute(self) -> None:
        """Test mapping minute timeframes."""
        mock_session = MagicMock(spec=ZerodhaSession)
        client = ZerodhaHistoricalDataClient(mock_session)

        assert client._map_timeframe_to_interval(Timeframe(value=1, unit=TimeframeUnit.MINUTE)).value == "minute"
        assert client._map_timeframe_to_interval(Timeframe(value=3, unit=TimeframeUnit.MINUTE)).value == "3minute"
        assert client._map_timeframe_to_interval(Timeframe(value=5, unit=TimeframeUnit.MINUTE)).value == "5minute"
        assert client._map_timeframe_to_interval(Timeframe(value=10, unit=TimeframeUnit.MINUTE)).value == "10minute"
        assert client._map_timeframe_to_interval(Timeframe(value=15, unit=TimeframeUnit.MINUTE)).value == "15minute"
        assert client._map_timeframe_to_interval(Timeframe(value=30, unit=TimeframeUnit.MINUTE)).value == "30minute"
        assert client._map_timeframe_to_interval(Timeframe(value=60, unit=TimeframeUnit.MINUTE)).value == "60minute"

    def test_map_timeframe_to_interval_hour(self) -> None:
        """Test mapping hour timeframe."""
        mock_session = MagicMock(spec=ZerodhaSession)
        client = ZerodhaHistoricalDataClient(mock_session)

        assert client._map_timeframe_to_interval(Timeframe(value=1, unit=TimeframeUnit.HOUR)).value == "60minute"

    def test_map_timeframe_to_interval_day(self) -> None:
        """Test mapping day timeframe."""
        mock_session = MagicMock(spec=ZerodhaSession)
        client = ZerodhaHistoricalDataClient(mock_session)

        assert client._map_timeframe_to_interval(Timeframe(value=1, unit=TimeframeUnit.DAY)).value == "day"

    def test_map_timeframe_to_interval_unsupported(self) -> None:
        """Test mapping unsupported timeframe raises error."""
        mock_session = MagicMock(spec=ZerodhaSession)
        client = ZerodhaHistoricalDataClient(mock_session)

        with pytest.raises(ValueError, match="Unsupported timeframe"):
            client._map_timeframe_to_interval(Timeframe(value=2, unit=TimeframeUnit.HOUR))

        with pytest.raises(ValueError, match="Unsupported timeframe"):
            client._map_timeframe_to_interval(Timeframe(value=2, unit=TimeframeUnit.DAY))

    def test_format_datetime(self) -> None:
        """Test datetime formatting for API."""
        mock_session = MagicMock(spec=ZerodhaSession)
        client = ZerodhaHistoricalDataClient(mock_session)

        dt = datetime(2024, 1, 15, 9, 30, 0, tzinfo=UTC)
        formatted = client._format_datetime(dt)
        # The API interprets request bounds as IST wall-clock time, so a UTC
        # instant is converted to IST before rendering.
        assert formatted == "2024-01-15 15:00:00"

    def test_format_datetime_converts_to_ist(self) -> None:
        """Test that request bounds are rendered in IST, not UTC."""
        mock_session = MagicMock(spec=ZerodhaSession)
        client = ZerodhaHistoricalDataClient(mock_session)

        utc_dt = datetime(2024, 1, 15, 3, 45, 0, tzinfo=UTC)
        ist_dt = datetime(2024, 1, 15, 9, 15, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))

        # The same instant in two zones must produce the same request bound.
        assert client._format_datetime(utc_dt) == "2024-01-15 09:15:00"
        assert client._format_datetime(ist_dt) == "2024-01-15 09:15:00"

    def test_format_datetime_assumes_ist_for_naive(self) -> None:
        """Test that a naive datetime is treated as IST."""
        mock_session = MagicMock(spec=ZerodhaSession)
        client = ZerodhaHistoricalDataClient(mock_session)

        naive = datetime(2024, 1, 15, 9, 15, 0)  # noqa: DTZ001 - naive on purpose
        assert client._format_datetime(naive) == "2024-01-15 09:15:00"

    @pytest.mark.asyncio
    async def test_get_raw_candles_success(self) -> None:
        """Test successful raw candle fetching."""
        mock_session = MagicMock(spec=ZerodhaSession)
        client = ZerodhaHistoricalDataClient(mock_session)

        # Mock session response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "candles": [
                    ["2024-01-15T09:15:00+05:30", 1500.0, 1510.0, 1495.0, 1505.0, 100000],
                    ["2024-01-15T09:16:00+05:30", 1505.0, 1515.0, 1500.0, 1510.0, 80000],
                ],
            },
        }
        mock_session.get = AsyncMock(return_value=mock_response)

        from_date = datetime(2024, 1, 15, 9, 15, tzinfo=UTC)
        to_date = datetime(2024, 1, 15, 9, 16, tzinfo=UTC)

        # Mock instrument master to return a known instrument
        mock_instrument = ZerodhaInstrument(
            instrument_token=408065,
            exchange_token=1594,
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
        client = ZerodhaHistoricalDataClient(mock_session, mock_master)

        raw_data = await client.get_raw_candles(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=from_date,
            to_date=to_date,
        )

        assert raw_data["status"] == "success"
        assert len(raw_data["data"]["candles"]) == 2
        # Verify instrument master was called
        mock_master.resolve_symbol.assert_called_once_with("NSE:INFY")

    @pytest.mark.asyncio
    async def test_get_raw_candles_with_oi(self) -> None:
        """Test raw candle fetching with OI data."""
        mock_session = MagicMock(spec=ZerodhaSession)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "candles": [
                    ["2024-01-15T09:15:00+05:30", 1500.0, 1510.0, 1495.0, 1505.0, 100000, 5000],
                ],
            },
        }
        mock_session.get = AsyncMock(return_value=mock_response)

        from_date = datetime(2024, 1, 15, 9, 15, tzinfo=UTC)
        to_date = datetime(2024, 1, 15, 9, 16, tzinfo=UTC)

        mock_instrument = ZerodhaInstrument(
            instrument_token=408065,
            exchange_token=1594,
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
        client = ZerodhaHistoricalDataClient(mock_session, mock_master)

        raw_data = await client.get_raw_candles(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=from_date,
            to_date=to_date,
            oi=True,
        )

        assert raw_data["status"] == "success"
        assert len(raw_data["data"]["candles"]) == 1
        # Verify OI parameter was passed
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["oi"] == "1"

    @pytest.mark.asyncio
    async def test_get_raw_candles_continuous(self) -> None:
        """Test raw candle fetching with continuous flag."""
        mock_session = MagicMock(spec=ZerodhaSession)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {"candles": []},
        }
        mock_session.get = AsyncMock(return_value=mock_response)

        from_date = datetime(2024, 1, 15, 9, 15, tzinfo=UTC)
        to_date = datetime(2024, 1, 15, 9, 16, tzinfo=UTC)

        mock_instrument = ZerodhaInstrument(
            instrument_token=408065,
            exchange_token=1594,
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
        client = ZerodhaHistoricalDataClient(mock_session, mock_master)

        await client.get_raw_candles(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=from_date,
            to_date=to_date,
            continuous=True,
        )

        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["continuous"] == "1"

    @pytest.mark.asyncio
    async def test_get_raw_candles_api_error(self) -> None:
        """Test handling API error response."""
        mock_session = MagicMock(spec=ZerodhaSession)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "error",
            "message": "Invalid instrument_token",
        }
        mock_session.get = AsyncMock(return_value=mock_response)

        from_date = datetime(2024, 1, 15, 9, 15, tzinfo=UTC)
        to_date = datetime(2024, 1, 15, 9, 16, tzinfo=UTC)

        mock_instrument = ZerodhaInstrument(
            instrument_token=408065,
            exchange_token=1594,
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
        client = ZerodhaHistoricalDataClient(mock_session, mock_master)

        with pytest.raises(RuntimeError, match="API error: Invalid instrument_token"):
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

        mock_session = MagicMock(spec=ZerodhaSession)
        mock_master = AsyncMock(spec=InstrumentMaster)
        mock_master.resolve_symbol = AsyncMock(side_effect=SymbolNotFoundError("NSE:UNKNOWN"))
        client = ZerodhaHistoricalDataClient(mock_session, mock_master)

        from_date = datetime(2024, 1, 15, 9, 15, tzinfo=UTC)
        to_date = datetime(2024, 1, 15, 9, 16, tzinfo=UTC)

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

        mock_session = MagicMock(spec=ZerodhaSession)
        mock_master = AsyncMock(spec=InstrumentMaster)
        mock_master.resolve_symbol = AsyncMock(side_effect=AmbiguousSymbolError("INFY", []))
        client = ZerodhaHistoricalDataClient(mock_session, mock_master)

        from_date = datetime(2024, 1, 15, 9, 15, tzinfo=UTC)
        to_date = datetime(2024, 1, 15, 9, 16, tzinfo=UTC)

        with pytest.raises(AmbiguousSymbolError):
            await client.get_raw_candles(
                symbol="INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=from_date,
                to_date=to_date,
            )