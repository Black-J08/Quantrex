"""Tests for InstrumentMaster."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

IST = ZoneInfo("Asia/Kolkata")

from quantrex.core.broker.zerodha.exceptions.exceptions import InstrumentMasterError
from quantrex.core.broker.zerodha.instrument_master import InstrumentMaster
from quantrex.core.broker.zerodha.instrument_master.models import ZerodhaInstrument
from quantrex.core.broker.zerodha.session.session import ZerodhaSession
from quantrex.core.exceptions import AmbiguousSymbolError, SymbolNotFoundError


class TestZerodhaInstrument:
    """Tests for ZerodhaInstrument model."""

    def test_from_csv_row_equity(self) -> None:
        """Test creating instrument from equity CSV row."""
        row = {
            "instrument_token": "408065",
            "exchange_token": "1594",
            "tradingsymbol": "INFY",
            "name": "INFOSYS",
            "last_price": "1500.0",
            "expiry": "",
            "strike": "",
            "tick_size": "0.05",
            "lot_size": "1",
            "instrument_type": "EQ",
            "segment": "NSE",
            "exchange": "NSE",
        }
        instrument = ZerodhaInstrument.from_csv_row(row)

        assert instrument.instrument_token == 408065
        assert instrument.exchange_token == 1594
        assert instrument.tradingsymbol == "INFY"
        assert instrument.name == "INFOSYS"
        assert instrument.last_price == Decimal("1500.0")
        assert instrument.expiry is None
        assert instrument.strike is None
        assert instrument.tick_size == Decimal("0.05")
        assert instrument.lot_size == 1
        assert instrument.instrument_type == "EQ"
        assert instrument.segment == "NSE"
        assert instrument.exchange == "NSE"
        assert instrument.symbol == "NSE:INFY"

    def test_from_csv_row_future(self) -> None:
        """Test creating instrument from future CSV row."""
        row = {
            "instrument_token": "5720322",
            "exchange_token": "22345",
            "tradingsymbol": "NIFTY15DECFUT",
            "name": "",
            "last_price": "78.0",
            "expiry": "2015-12-31",
            "strike": "",
            "tick_size": "0.05",
            "lot_size": "75",
            "instrument_type": "FUT",
            "segment": "NFO-FUT",
            "exchange": "NFO",
        }
        instrument = ZerodhaInstrument.from_csv_row(row)

        assert instrument.instrument_token == 5720322
        assert instrument.expiry == date(2015, 12, 31)
        assert instrument.instrument_type == "FUT"
        assert instrument.segment == "NFO-FUT"
        assert instrument.exchange == "NFO"

    def test_from_csv_row_option(self) -> None:
        """Test creating instrument from option CSV row."""
        row = {
            "instrument_token": "5720578",
            "exchange_token": "22346",
            "tradingsymbol": "NIFTY159500CE",
            "name": "",
            "last_price": "23.0",
            "expiry": "2015-12-31",
            "strike": "9500",
            "tick_size": "0.05",
            "lot_size": "75",
            "instrument_type": "CE",
            "segment": "NFO-OPT",
            "exchange": "NFO",
        }
        instrument = ZerodhaInstrument.from_csv_row(row)

        assert instrument.instrument_token == 5720578
        assert instrument.expiry == date(2015, 12, 31)
        assert instrument.strike == Decimal(9500)
        assert instrument.instrument_type == "CE"
        assert instrument.segment == "NFO-OPT"


class TestInstrumentMaster:
    """Tests for InstrumentMaster."""

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create a mock ZerodhaSession."""
        session = MagicMock(spec=ZerodhaSession)
        session.get = AsyncMock()
        return session

    @pytest.fixture
    def sample_instruments(self) -> list[ZerodhaInstrument]:
        """Create sample instruments for testing."""
        return [
            ZerodhaInstrument(
                instrument_token=408065,
                exchange_token=1594,
                tradingsymbol="INFY",
                name="INFOSYS",
                last_price=Decimal(1500),
                expiry=None,
                strike=None,
                tick_size=Decimal("0.05"),
                lot_size=1,
                instrument_type="EQ",
                segment="NSE",
                exchange="NSE",
            ),
            ZerodhaInstrument(
                instrument_token=738561,
                exchange_token=1595,
                tradingsymbol="RELIANCE",
                name="RELIANCE",
                last_price=Decimal(2500),
                expiry=None,
                strike=None,
                tick_size=Decimal("0.05"),
                lot_size=1,
                instrument_type="EQ",
                segment="NSE",
                exchange="NSE",
            ),
            ZerodhaInstrument(
                instrument_token=123456,
                exchange_token=1596,
                tradingsymbol="INFY",
                name="INFOSYS BSE",
                last_price=Decimal(1500),
                expiry=None,
                strike=None,
                tick_size=Decimal("0.05"),
                lot_size=1,
                instrument_type="EQ",
                segment="BSE",
                exchange="BSE",
            ),
        ]

    @pytest.mark.asyncio
    async def test_resolve_symbol_exact_match(self, mock_session, sample_instruments) -> None:
        """Test resolving symbol with exact match."""
        master = InstrumentMaster(mock_session)
        # Manually populate indices
        master._exact_index = {inst.symbol: inst for inst in sample_instruments}
        master._tradingsymbol_index = {}
        for inst in sample_instruments:
            if inst.tradingsymbol not in master._tradingsymbol_index:
                master._tradingsymbol_index[inst.tradingsymbol] = []
            master._tradingsymbol_index[inst.tradingsymbol].append(inst)
        master._loaded = True
        master._metadata = MagicMock()
        master._metadata.is_stale = MagicMock(return_value=False)

        instrument = await master.resolve_symbol("NSE:INFY")
        assert instrument.instrument_token == 408065
        assert instrument.exchange == "NSE"

    @pytest.mark.asyncio
    async def test_resolve_symbol_tradingsymbol_unique(self, mock_session, sample_instruments) -> None:
        """Test resolving symbol with unique tradingsymbol."""
        master = InstrumentMaster(mock_session)
        # Only add RELIANCE to tradingsymbol index (unique)
        master._exact_index = {}
        master._tradingsymbol_index = {"RELIANCE": [sample_instruments[1]]}
        master._loaded = True
        master._metadata = MagicMock()
        master._metadata.is_stale = MagicMock(return_value=False)

        instrument = await master.resolve_symbol("RELIANCE")
        assert instrument.instrument_token == 738561
        assert instrument.exchange == "NSE"

    @pytest.mark.asyncio
    async def test_resolve_symbol_ambiguous(self, mock_session, sample_instruments) -> None:
        """Test resolving ambiguous tradingsymbol raises error."""
        master = InstrumentMaster(mock_session)
        # INFY exists on both NSE and BSE
        master._exact_index = {}
        master._tradingsymbol_index = {"INFY": [sample_instruments[0], sample_instruments[2]]}
        master._loaded = True
        master._metadata = MagicMock()
        master._metadata.is_stale = MagicMock(return_value=False)

        with pytest.raises(AmbiguousSymbolError) as exc_info:
            await master.resolve_symbol("INFY")

        assert exc_info.value.tradingsymbol == "INFY"
        assert len(exc_info.value.candidates) == 2

    @pytest.mark.asyncio
    async def test_resolve_symbol_not_found(self, mock_session) -> None:
        """Test resolving unknown symbol raises error with suggestions."""
        master = InstrumentMaster(mock_session)
        # Use real strings for indices so suggestions work
        master._exact_index = {"NSE:INFY": MagicMock(symbol="NSE:INFY")}
        master._tradingsymbol_index = {"INFY": [MagicMock(tradingsymbol="INFY")]}
        master._loaded = True
        master._metadata = MagicMock()
        master._metadata.is_stale = MagicMock(return_value=False)

        with pytest.raises(SymbolNotFoundError) as exc_info:
            await master.resolve_symbol("NSE:INF")  # Partial match should suggest NSE:INFY

        assert exc_info.value.symbol == "NSE:INF"
        assert len(exc_info.value.suggestions) > 0
        assert "NSE:INFY" in exc_info.value.suggestions

    @pytest.mark.asyncio
    async def test_refresh_if_needed_stale(self, mock_session) -> None:
        """Test refresh is triggered when cache is stale."""
        master = InstrumentMaster(mock_session)
        master._loaded = True
        master._metadata = MagicMock()
        master._metadata.is_stale = MagicMock(return_value=True)
        master._refresh = AsyncMock()

        await master._ensure_loaded()

        master._refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_if_needed_fresh(self, mock_session) -> None:
        """Test refresh is not triggered when cache is fresh."""
        master = InstrumentMaster(mock_session)
        master._loaded = True
        master._metadata = MagicMock()
        master._metadata.is_stale = MagicMock(return_value=False)
        master._refresh = AsyncMock()

        await master._ensure_loaded()

        master._refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_double_checked_locking(self, mock_session, tmp_path) -> None:
        """Test double-checked locking prevents duplicate refreshes using real cache."""
        import gzip

        # Pre-populate cache with stale data
        csv_content = """instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange
408065,1594,INFY,INFOSYS,1500.0,,,0.05,1,EQ,NSE,NSE
"""
        gzipped = gzip.compress(csv_content.encode())

        mock_response = MagicMock()
        mock_response.content = gzipped
        mock_response.headers = {"Content-Encoding": "gzip"}
        mock_session.get = AsyncMock(return_value=mock_response)

        master = InstrumentMaster(mock_session, cache_dir=tmp_path)
        await master._refresh()  # Initial load - cache is now fresh

        # Manually set metadata timestamp to before yesterday's 8:30 AM IST to make it stale
        # Also set _loaded = True to prevent _load_cache() from overwriting our stale timestamp
        from datetime import UTC, datetime, timedelta
        master._loaded = True
        # Set to 2 days ago at 02:00 UTC (before 03:00 UTC expiry)
        master._metadata.timestamp = (datetime.now(UTC) - timedelta(days=2, hours=1)).isoformat()

        # Now mock the session to track refresh calls
        refresh_count = 0

        async def tracking_get(*args, **kwargs):
            nonlocal refresh_count
            refresh_count += 1
            # Return the same mock response
            return mock_response

        mock_session.get = tracking_get

        # Simulate concurrent calls to _ensure_loaded
        await asyncio.gather(
            master._ensure_loaded(),
            master._ensure_loaded(),
            master._ensure_loaded(),
        )

        # Refresh should only be called once due to double-checked locking
        assert refresh_count == 1

    @pytest.mark.asyncio
    async def test_refresh_success(self, mock_session, tmp_path) -> None:
        """Test successful refresh from API."""
        # Create mock response with gzipped CSV
        import gzip

        csv_content = """instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange
408065,1594,INFY,INFOSYS,1500.0,,,0.05,1,EQ,NSE,NSE
738561,1595,RELIANCE,RELIANCE,2500.0,,,0.05,1,EQ,NSE,NSE
"""

        gzipped = gzip.compress(csv_content.encode())

        mock_response = MagicMock()
        mock_response.content = gzipped
        mock_response.headers = {"Content-Encoding": "gzip"}
        mock_session.get = AsyncMock(return_value=mock_response)

        master = InstrumentMaster(mock_session, cache_dir=tmp_path)
        await master._refresh()

        # Verify cache files created
        assert (tmp_path / "instruments.csv").exists()
        assert (tmp_path / "metadata.json").exists()

        # Verify indices built
        assert "NSE:INFY" in master._exact_index
        assert "NSE:RELIANCE" in master._exact_index
        assert master._metadata.record_count == 2
        # Verify timestamp is in IST
        assert "+05:30" in master._metadata.timestamp or "Asia/Kolkata" in master._metadata.timestamp

    @pytest.mark.asyncio
    async def test_refresh_fail_open(self, mock_session, tmp_path) -> None:
        """Test fail-open behavior when refresh fails but stale cache exists."""
        master = InstrumentMaster(mock_session, cache_dir=tmp_path)
        master._loaded = True
        master._metadata = MagicMock()
        master._metadata.is_stale = MagicMock(return_value=True)
        master._exact_index = {"NSE:INFY": MagicMock()}
        master._session.get = AsyncMock(side_effect=Exception("Network error"))

        # Should not raise, should keep stale cache
        await master._refresh_if_needed()

        assert "NSE:INFY" in master._exact_index

    @pytest.mark.asyncio
    async def test_refresh_fail_no_cache(self, mock_session, tmp_path) -> None:
        """Test refresh failure raises when no cache exists."""
        master = InstrumentMaster(mock_session, cache_dir=tmp_path)
        master._loaded = True
        master._metadata = None
        master._session.get = AsyncMock(side_effect=Exception("Network error"))

        with pytest.raises(InstrumentMasterError):
            await master._refresh_if_needed()

    @pytest.mark.asyncio
    async def test_atomic_write(self, mock_session, tmp_path) -> None:
        """Test atomic write with temp files."""
        import gzip

        csv_content = """instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange
408065,1594,INFY,INFOSYS,1500.0,,,0.05,1,EQ,NSE,NSE
"""

        gzipped = gzip.compress(csv_content.encode())

        mock_response = MagicMock()
        mock_response.content = gzipped
        mock_response.headers = {"Content-Encoding": "gzip"}
        mock_session.get = AsyncMock(return_value=mock_response)

        master = InstrumentMaster(mock_session, cache_dir=tmp_path)
        await master._refresh()

        # Verify no temp files left behind
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

        # Verify files have correct permissions
        csv_stat = (tmp_path / "instruments.csv").stat()
        meta_stat = (tmp_path / "metadata.json").stat()
        assert oct(csv_stat.st_mode & 0o777) == "0o600"
        assert oct(meta_stat.st_mode & 0o777) == "0o600"

    def test_is_fresh(self, mock_session) -> None:
        """Test is_fresh method."""
        master = InstrumentMaster(mock_session)
        master._metadata = MagicMock()
        master._metadata.is_stale = MagicMock(return_value=False)

        assert master.is_fresh() is True

        master._metadata.is_stale = MagicMock(return_value=True)
        assert master.is_fresh() is False

    def test_get_stats(self, mock_session) -> None:
        """Test get_stats method."""
        master = InstrumentMaster(mock_session)
        master._loaded = True
        master._metadata = MagicMock()
        master._metadata.record_count = 100
        master._metadata.timestamp = datetime.now(IST).isoformat()
        master._metadata.is_stale = MagicMock(return_value=False)

        stats = master.get_stats()

        assert stats["loaded"] is True
        assert stats["record_count"] == 100
        assert stats["is_fresh"] is True
        assert "cache_age_hours" in stats
        assert "cache_dir" in stats


import asyncio