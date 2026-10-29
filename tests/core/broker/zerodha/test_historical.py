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
        mock_session.historical_limiter.acquire = AsyncMock()

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
        # Verify rate limiter was acquired before the request
        mock_session.historical_limiter.acquire.assert_awaited_once()

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
        mock_session.historical_limiter.acquire = AsyncMock()

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
        # Verify rate limiter was acquired before the request
        mock_session.historical_limiter.acquire.assert_awaited_once()

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
        mock_session.historical_limiter.acquire = AsyncMock()

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
        # Verify rate limiter was acquired before the request
        mock_session.historical_limiter.acquire.assert_awaited_once()

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
        mock_session.historical_limiter.acquire = AsyncMock()

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

    @pytest.mark.asyncio
    async def test_month_segments_single_month(self) -> None:
        """Test _month_segments returns one segment for a range within a month."""
        mock_session = MagicMock(spec=ZerodhaSession)
        client = ZerodhaHistoricalDataClient(mock_session)

        from_date = datetime(2024, 1, 15, tzinfo=UTC)
        to_date = datetime(2024, 1, 20, tzinfo=UTC)

        segments = client._month_segments(from_date, to_date)

        assert segments == [(from_date, to_date)]

    @pytest.mark.asyncio
    async def test_month_segments_spans_month_boundary(self) -> None:
        """Test _month_segments splits at month boundaries."""
        mock_session = MagicMock(spec=ZerodhaSession)
        client = ZerodhaHistoricalDataClient(mock_session)

        from_date = datetime(2024, 1, 15, tzinfo=UTC)
        to_date = datetime(2024, 2, 10, tzinfo=UTC)

        segments = client._month_segments(from_date, to_date)

        assert len(segments) == 2
        assert segments[0] == (datetime(2024, 1, 15, tzinfo=UTC), datetime(2024, 2, 1, tzinfo=UTC))
        assert segments[1] == (datetime(2024, 2, 1, tzinfo=UTC), datetime(2024, 2, 10, tzinfo=UTC))

    @pytest.mark.asyncio
    async def test_month_segments_spans_multiple_months(self) -> None:
        """Test _month_segments splits across multiple month boundaries."""
        mock_session = MagicMock(spec=ZerodhaSession)
        client = ZerodhaHistoricalDataClient(mock_session)

        from_date = datetime(2024, 1, 15, tzinfo=UTC)
        to_date = datetime(2024, 4, 10, tzinfo=UTC)

        segments = client._month_segments(from_date, to_date)

        assert len(segments) == 4
        assert segments[0] == (datetime(2024, 1, 15, tzinfo=UTC), datetime(2024, 2, 1, tzinfo=UTC))
        assert segments[1] == (datetime(2024, 2, 1, tzinfo=UTC), datetime(2024, 3, 1, tzinfo=UTC))
        assert segments[2] == (datetime(2024, 3, 1, tzinfo=UTC), datetime(2024, 4, 1, tzinfo=UTC))
        assert segments[3] == (datetime(2024, 4, 1, tzinfo=UTC), datetime(2024, 4, 10, tzinfo=UTC))

    @pytest.mark.asyncio
    async def test_month_segments_adjacent_chunks_gap_free(self) -> None:
        """Test that adjacent segments have no gaps and no overlaps."""
        mock_session = MagicMock(spec=ZerodhaSession)
        client = ZerodhaHistoricalDataClient(mock_session)

        from_date = datetime(2024, 1, 15, tzinfo=UTC)
        to_date = datetime(2024, 5, 20, tzinfo=UTC)

        segments = client._month_segments(from_date, to_date)

        # Verify gap-free coverage
        for i in range(len(segments) - 1):
            assert segments[i][1] == segments[i + 1][0], (
                f"Gap or overlap between segment {i} and {i + 1}"
            )

        # Verify first starts at from_date and last ends at to_date
        assert segments[0][0] == from_date
        assert segments[-1][1] == to_date

    @pytest.mark.asyncio
    async def test_month_segments_year_boundary(self) -> None:
        """Test _month_segments handles year rollover correctly."""
        mock_session = MagicMock(spec=ZerodhaSession)
        client = ZerodhaHistoricalDataClient(mock_session)

        from_date = datetime(2023, 12, 15, tzinfo=UTC)
        to_date = datetime(2024, 1, 10, tzinfo=UTC)

        segments = client._month_segments(from_date, to_date)

        assert len(segments) == 2
        assert segments[0] == (datetime(2023, 12, 15, tzinfo=UTC), datetime(2024, 1, 1, tzinfo=UTC))
        assert segments[1] == (datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 10, tzinfo=UTC))

    @pytest.mark.asyncio
    async def test_get_raw_candles_chunks_large_range(self) -> None:
        """Test that a multi-month range is split into multiple API calls."""
        mock_session = MagicMock(spec=ZerodhaSession)
        mock_session.historical_limiter.acquire = AsyncMock()

        # Each segment returns its own candles
        # Jan 15 → Apr 10 spans 4 segments: Jan15-Feb1, Feb1-Mar1, Mar1-Apr1, Apr1-Apr10
        responses = [
            {"status": "success", "data": {"candles": [[1, 2, 3, 4, 5, 6]]}},
            {"status": "success", "data": {"candles": [[7, 8, 9, 10, 11, 12]]}},
            {"status": "success", "data": {"candles": [[13, 14, 15, 16, 17, 18]]}},
            {"status": "success", "data": {"candles": [[19, 20, 21, 22, 23, 24]]}},
        ]
        mock_session.get = AsyncMock(side_effect=[MagicMock(json=lambda r=r: r) for r in responses])

        from_date = datetime(2024, 1, 15, tzinfo=UTC)
        to_date = datetime(2024, 4, 10, tzinfo=UTC)

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

        # 4 segments → 4 API calls
        assert mock_session.get.await_count == 4
        # 4 segments → 4 rate-limit acquisitions
        assert mock_session.historical_limiter.acquire.await_count == 4
        # All candles merged, no duplication
        assert len(raw_data["data"]["candles"]) == 4

    @pytest.mark.asyncio
    async def test_get_raw_candles_single_segment_no_chunking(self) -> None:
        """Test that a range within one month makes a single API call."""
        mock_session = MagicMock(spec=ZerodhaSession)
        mock_session.historical_limiter.acquire = AsyncMock()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {"candles": [[1, 2, 3, 4, 5, 6]]},
        }
        mock_session.get = AsyncMock(return_value=mock_response)

        from_date = datetime(2024, 1, 15, tzinfo=UTC)
        to_date = datetime(2024, 1, 20, tzinfo=UTC)

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

        assert mock_session.get.await_count == 1
        assert mock_session.historical_limiter.acquire.await_count == 1
        assert len(raw_data["data"]["candles"]) == 1

    @pytest.mark.asyncio
    async def test_get_raw_candles_each_segment_respects_rate_limit(self) -> None:
        """Test that acquire() is called before each segment request."""
        mock_session = MagicMock(spec=ZerodhaSession)
        mock_session.historical_limiter.acquire = AsyncMock()

        responses = [
            {"status": "success", "data": {"candles": [[1, 2, 3, 4, 5, 6]]}},
            {"status": "success", "data": {"candles": [[7, 8, 9, 10, 11, 12]]}},
        ]
        mock_session.get = AsyncMock(side_effect=[MagicMock(json=lambda r=r: r) for r in responses])

        from_date = datetime(2024, 1, 15, tzinfo=UTC)
        to_date = datetime(2024, 2, 10, tzinfo=UTC)

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
        )

        # acquire() called before each of the 2 segments
        assert mock_session.historical_limiter.acquire.await_count == 2
        # Each segment gets its own from/to params (converted to IST wall clock)
        calls = mock_session.get.await_args_list
        assert calls[0].kwargs["params"]["from"] == "2024-01-15 05:30:00"
        assert calls[0].kwargs["params"]["to"] == "2024-02-01 05:30:00"
        assert calls[1].kwargs["params"]["from"] == "2024-02-01 05:30:00"
        assert calls[1].kwargs["params"]["to"] == "2024-02-10 05:30:00"

    @pytest.mark.asyncio
    async def test_get_raw_candles_segment_failure_propagates(self) -> None:
        """Test that a segment failure propagates without fetching remaining segments."""
        mock_session = MagicMock(spec=ZerodhaSession)
        mock_session.historical_limiter.acquire = AsyncMock()

        # First segment succeeds, second fails
        mock_response_ok = MagicMock()
        mock_response_ok.json.return_value = {
            "status": "success",
            "data": {"candles": [[1, 2, 3, 4, 5, 6]]},
        }
        mock_response_err = MagicMock()
        mock_response_err.json.return_value = {
            "status": "error",
            "message": "API error",
        }
        mock_session.get = AsyncMock(side_effect=[mock_response_ok, mock_response_err])

        from_date = datetime(2024, 1, 15, tzinfo=UTC)
        to_date = datetime(2024, 2, 10, tzinfo=UTC)

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

        with pytest.raises(RuntimeError, match="API error: API error"):
            await client.get_raw_candles(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                from_date=from_date,
                to_date=to_date,
            )

        # Only 2 acquire calls (one per segment attempted), not more
        assert mock_session.historical_limiter.acquire.await_count == 2