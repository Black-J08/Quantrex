"""Tests for ZerodhaHistoricalDataProvider."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from decimal import Decimal

from quantrex.core.broker.zerodha.historical.provider import ZerodhaHistoricalDataProvider
from quantrex.core.broker.zerodha.instrument_master import InstrumentMaster
from quantrex.core.broker.zerodha.instrument_master.models import ZerodhaInstrument
from quantrex.core.broker.zerodha.session.session import ZerodhaSession
from quantrex.core.models import Timeframe, TimeframeUnit, OHLCVCandle


class TestZerodhaHistoricalDataProvider:
    """Tests for ZerodhaHistoricalDataProvider."""

    def test_init_with_default_instrument_master(self) -> None:
        """Test initialization creates default InstrumentMaster."""
        mock_session = MagicMock(spec=ZerodhaSession)
        provider = ZerodhaHistoricalDataProvider(mock_session)

        assert provider._instrument_master is not None
        assert isinstance(provider._instrument_master, InstrumentMaster)

    def test_init_with_custom_instrument_master(self) -> None:
        """Test initialization with custom InstrumentMaster."""
        mock_session = MagicMock(spec=ZerodhaSession)
        mock_master = MagicMock(spec=InstrumentMaster)
        provider = ZerodhaHistoricalDataProvider(mock_session, mock_master)

        assert provider._instrument_master is mock_master

    def test_map_timeframe_to_interval_minute(self) -> None:
        """Test mapping minute timeframes."""
        mock_session = MagicMock(spec=ZerodhaSession)
        provider = ZerodhaHistoricalDataProvider(mock_session)

        assert provider._map_timeframe_to_interval(Timeframe(value=1, unit=TimeframeUnit.MINUTE)).value == "minute"
        assert provider._map_timeframe_to_interval(Timeframe(value=3, unit=TimeframeUnit.MINUTE)).value == "3minute"
        assert provider._map_timeframe_to_interval(Timeframe(value=5, unit=TimeframeUnit.MINUTE)).value == "5minute"
        assert provider._map_timeframe_to_interval(Timeframe(value=10, unit=TimeframeUnit.MINUTE)).value == "10minute"
        assert provider._map_timeframe_to_interval(Timeframe(value=15, unit=TimeframeUnit.MINUTE)).value == "15minute"
        assert provider._map_timeframe_to_interval(Timeframe(value=30, unit=TimeframeUnit.MINUTE)).value == "30minute"
        assert provider._map_timeframe_to_interval(Timeframe(value=60, unit=TimeframeUnit.MINUTE)).value == "60minute"

    def test_map_timeframe_to_interval_hour(self) -> None:
        """Test mapping hour timeframe."""
        mock_session = MagicMock(spec=ZerodhaSession)
        provider = ZerodhaHistoricalDataProvider(mock_session)

        assert provider._map_timeframe_to_interval(Timeframe(value=1, unit=TimeframeUnit.HOUR)).value == "60minute"

    def test_map_timeframe_to_interval_day(self) -> None:
        """Test mapping day timeframe."""
        mock_session = MagicMock(spec=ZerodhaSession)
        provider = ZerodhaHistoricalDataProvider(mock_session)

        assert provider._map_timeframe_to_interval(Timeframe(value=1, unit=TimeframeUnit.DAY)).value == "day"

    def test_map_timeframe_to_interval_unsupported(self) -> None:
        """Test mapping unsupported timeframe raises error."""
        mock_session = MagicMock(spec=ZerodhaSession)
        provider = ZerodhaHistoricalDataProvider(mock_session)

        with pytest.raises(ValueError, match="Unsupported timeframe"):
            provider._map_timeframe_to_interval(Timeframe(value=2, unit=TimeframeUnit.HOUR))

        with pytest.raises(ValueError, match="Unsupported timeframe"):
            provider._map_timeframe_to_interval(Timeframe(value=2, unit=TimeframeUnit.DAY))

    def test_format_datetime(self) -> None:
        """Test datetime formatting for API."""
        mock_session = MagicMock(spec=ZerodhaSession)
        provider = ZerodhaHistoricalDataProvider(mock_session)

        dt = datetime(2024, 1, 15, 9, 30, 0, tzinfo=timezone.utc)
        formatted = provider._format_datetime(dt)
        assert formatted == "2024-01-15 09:30:00"

    @pytest.mark.asyncio
    async def test_get_candles_success(self) -> None:
        """Test successful candle fetching."""
        mock_session = MagicMock(spec=ZerodhaSession)
        provider = ZerodhaHistoricalDataProvider(mock_session)

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

        from_date = datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc)
        to_date = datetime(2024, 1, 15, 9, 16, tzinfo=timezone.utc)

        # Mock instrument master to return a known instrument
        mock_instrument = ZerodhaInstrument(
            instrument_token=408065,
            exchange_token=1594,
            tradingsymbol="INFY",
            name="INFOSYS",
            last_price=Decimal("0"),
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
        provider = ZerodhaHistoricalDataProvider(mock_session, mock_master)

        candles = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=from_date,
            to_date=to_date,
        )

        assert len(candles) == 2
        assert all(isinstance(c, OHLCVCandle) for c in candles)
        assert candles[0].symbol == "NSE:INFY"
        assert candles[0].open == Decimal("1500.0")
        assert candles[0].high == Decimal("1510.0")
        assert candles[0].low == Decimal("1495.0")
        assert candles[0].close == Decimal("1505.0")
        assert candles[0].volume == Decimal("100000")
        # Verify instrument master was called
        mock_master.resolve_symbol.assert_called_once_with("NSE:INFY")

    @pytest.mark.asyncio
    async def test_get_candles_with_oi(self) -> None:
        """Test candle fetching with OI data."""
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

        from_date = datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc)
        to_date = datetime(2024, 1, 15, 9, 16, tzinfo=timezone.utc)

        mock_instrument = ZerodhaInstrument(
            instrument_token=408065,
            exchange_token=1594,
            tradingsymbol="INFY",
            name="INFOSYS",
            last_price=Decimal("0"),
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
        provider = ZerodhaHistoricalDataProvider(mock_session, mock_master)

        candles = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=from_date,
            to_date=to_date,
            oi=True,
        )

        assert len(candles) == 1
        # Verify OI parameter was passed
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["oi"] == "1"

    @pytest.mark.asyncio
    async def test_get_candles_continuous(self) -> None:
        """Test candle fetching with continuous flag."""
        mock_session = MagicMock(spec=ZerodhaSession)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {"candles": []},
        }
        mock_session.get = AsyncMock(return_value=mock_response)

        from_date = datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc)
        to_date = datetime(2024, 1, 15, 9, 16, tzinfo=timezone.utc)

        mock_instrument = ZerodhaInstrument(
            instrument_token=408065,
            exchange_token=1594,
            tradingsymbol="INFY",
            name="INFOSYS",
            last_price=Decimal("0"),
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
        provider = ZerodhaHistoricalDataProvider(mock_session, mock_master)

        await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=from_date,
            to_date=to_date,
            continuous=True,
        )

        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["continuous"] == "1"

    @pytest.mark.asyncio
    async def test_get_candles_api_error(self) -> None:
        """Test handling API error response."""
        mock_session = MagicMock(spec=ZerodhaSession)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "error",
            "message": "Invalid instrument_token",
        }
        mock_session.get = AsyncMock(return_value=mock_response)

        from_date = datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc)
        to_date = datetime(2024, 1, 15, 9, 16, tzinfo=timezone.utc)

        mock_instrument = ZerodhaInstrument(
            instrument_token=408065,
            exchange_token=1594,
            tradingsymbol="INFY",
            name="INFOSYS",
            last_price=Decimal("0"),
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
        provider = ZerodhaHistoricalDataProvider(mock_session, mock_master)

        with pytest.raises(RuntimeError, match="API error: Invalid instrument_token"):
            await provider.get_candles(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=from_date,
                to_date=to_date,
            )

    @pytest.mark.asyncio
    async def test_get_candles_parsing_error(self) -> None:
        """Test handling candle parsing errors."""
        mock_session = MagicMock(spec=ZerodhaSession)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "candles": [
                    ["2024-01-15T09:15:00+05:30", 1500.0, 1510.0, 1495.0, 1505.0, 100000],
                    ["invalid", "data", "here"],  # Invalid candle
                ],
            },
        }
        mock_session.get = AsyncMock(return_value=mock_response)

        from_date = datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc)
        to_date = datetime(2024, 1, 15, 9, 16, tzinfo=timezone.utc)

        mock_instrument = ZerodhaInstrument(
            instrument_token=408065,
            exchange_token=1594,
            tradingsymbol="INFY",
            name="INFOSYS",
            last_price=Decimal("0"),
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
        provider = ZerodhaHistoricalDataProvider(mock_session, mock_master)

        candles = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=from_date,
            to_date=to_date,
        )

        # Should only return the valid candle
        assert len(candles) == 1

    @pytest.mark.asyncio
    async def test_get_candles_symbol_not_found(self) -> None:
        """Test handling symbol not found error."""
        from quantrex.core.broker.zerodha.exceptions.exceptions import SymbolNotFoundError

        mock_session = MagicMock(spec=ZerodhaSession)
        mock_master = AsyncMock(spec=InstrumentMaster)
        mock_master.resolve_symbol = AsyncMock(side_effect=SymbolNotFoundError("NSE:UNKNOWN"))
        provider = ZerodhaHistoricalDataProvider(mock_session, mock_master)

        from_date = datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc)
        to_date = datetime(2024, 1, 15, 9, 16, tzinfo=timezone.utc)

        with pytest.raises(SymbolNotFoundError):
            await provider.get_candles(
                symbol="NSE:UNKNOWN",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=from_date,
                to_date=to_date,
            )

    @pytest.mark.asyncio
    async def test_get_candles_ambiguous_symbol(self) -> None:
        """Test handling ambiguous symbol error."""
        from quantrex.core.broker.zerodha.exceptions.exceptions import AmbiguousSymbolError

        mock_session = MagicMock(spec=ZerodhaSession)
        mock_master = AsyncMock(spec=InstrumentMaster)
        mock_master.resolve_symbol = AsyncMock(side_effect=AmbiguousSymbolError("INFY", []))
        provider = ZerodhaHistoricalDataProvider(mock_session, mock_master)

        from_date = datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc)
        to_date = datetime(2024, 1, 15, 9, 16, tzinfo=timezone.utc)

        with pytest.raises(AmbiguousSymbolError):
            await provider.get_candles(
                symbol="INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=from_date,
                to_date=to_date,
            )