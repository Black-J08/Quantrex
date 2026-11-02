"""Tests for InstrumentMaster."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

IST = ZoneInfo("Asia/Kolkata")

from quantrex.core.broker.exceptions.exceptions import (
    AmbiguousSymbolError,
    SymbolNotFoundError,
)
from quantrex.core.broker.shoonya.instrument_master.master import (
    CacheMetadata,
    InstrumentMaster,
)
from quantrex.core.broker.shoonya.instrument_master.models import ShoonyaInstrument
from quantrex.core.broker.shoonya.session.session import ShoonyaSession


class TestShoonyaInstrument:
    """Tests for ShoonyaInstrument model."""

    def test_instrument_creation(self) -> None:
        """Test creating instrument from fields."""
        instrument = ShoonyaInstrument(
            instrument_token="2885",
            exchange_token="1594",
            tradingsymbol="INFY",
            name="INFOSYS",
            last_price=Decimal("1500.0"),
            expiry=None,
            strike=None,
            tick_size=Decimal("0.05"),
            lot_size=1,
            instrument_type="EQ",
            segment="NSE",
            exchange="NSE",
        )

        assert instrument.instrument_token == "2885"
        assert instrument.exchange_token == "1594"
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

    def test_instrument_with_future(self) -> None:
        """Test creating instrument for a future contract."""
        expiry = date(2024, 3, 28)
        instrument = ShoonyaInstrument(
            instrument_token="12345",
            exchange_token="6789",
            tradingsymbol="INFY24MARFUT",
            name="INFOSYS FUT",
            last_price=Decimal("1510.0"),
            expiry=expiry,
            strike=None,
            tick_size=Decimal("0.05"),
            lot_size=100,
            instrument_type="FUT",
            segment="NFO",
            exchange="NSE",
        )

        assert instrument.expiry == expiry
        assert instrument.strike is None
        assert instrument.instrument_type == "FUT"
        assert instrument.segment == "NFO"
        assert instrument.symbol == "NSE:INFY24MARFUT"

    def test_instrument_with_option(self) -> None:
        """Test creating instrument for an option contract."""
        expiry = date(2024, 3, 28)
        instrument = ShoonyaInstrument(
            instrument_token="54321",
            exchange_token="9876",
            tradingsymbol="INFY24MAR2500CE",
            name="INFOSYS OPT",
            last_price=Decimal("50.0"),
            expiry=expiry,
            strike=Decimal("2500.0"),
            tick_size=Decimal("0.05"),
            lot_size=100,
            instrument_type="OPT",
            segment="NFO",
            exchange="NSE",
        )

        assert instrument.expiry == expiry
        assert instrument.strike == Decimal("2500.0")
        assert instrument.instrument_type == "OPT"
        assert instrument.symbol == "NSE:INFY24MAR2500CE"


class TestInstrumentMaster:
    """Tests for InstrumentMaster."""

    @pytest.mark.asyncio
    async def test_resolve_symbol_exact_match(self) -> None:
        """Test exact symbol match returns instrument."""
        mock_session = MagicMock(spec=ShoonyaSession)
        master = InstrumentMaster(mock_session)

        instrument = ShoonyaInstrument(
            instrument_token="2885",
            exchange_token="1594",
            tradingsymbol="INFY",
            name="INFOSYS",
            last_price=Decimal("1500.0"),
            expiry=None,
            strike=None,
            tick_size=Decimal("0.05"),
            lot_size=1,
            instrument_type="EQ",
            segment="NSE",
            exchange="NSE",
        )
        master._exact_index["NSE:INFY"] = instrument
        master._loaded = True
        master._metadata = CacheMetadata(
            timestamp=datetime.now(IST).isoformat(),
            record_count=1,
            segments=["NSE"],
        )

        result = await master.resolve_symbol("NSE:INFY")
        assert result is instrument

    @pytest.mark.asyncio
    async def test_resolve_symbol_tradingsymbol_unique(self) -> None:
        """Test tradingsymbol-only match when unique."""
        mock_session = MagicMock(spec=ShoonyaSession)
        master = InstrumentMaster(mock_session)

        instrument = ShoonyaInstrument(
            instrument_token="2885",
            exchange_token="1594",
            tradingsymbol="INFY",
            name="INFOSYS",
            last_price=Decimal("1500.0"),
            expiry=None,
            strike=None,
            tick_size=Decimal("0.05"),
            lot_size=1,
            instrument_type="EQ",
            segment="NSE",
            exchange="NSE",
        )
        master._tradingsymbol_index["INFY"] = [instrument]
        master._loaded = True
        master._metadata = CacheMetadata(
            timestamp=datetime.now(IST).isoformat(),
            record_count=1,
            segments=["NSE"],
        )

        result = await master.resolve_symbol("INFY")
        assert result is instrument

    @pytest.mark.asyncio
    async def test_resolve_symbol_ambiguous(self) -> None:
        """Test ambiguous tradingsymbol raises AmbiguousSymbolError."""
        mock_session = MagicMock(spec=ShoonyaSession)
        master = InstrumentMaster(mock_session)

        inst1 = ShoonyaInstrument(
            instrument_token="2885",
            exchange_token="1594",
            tradingsymbol="INFY",
            name="INFOSYS",
            last_price=Decimal("1500.0"),
            expiry=None,
            strike=None,
            tick_size=Decimal("0.05"),
            lot_size=1,
            instrument_type="EQ",
            segment="NSE",
            exchange="NSE",
        )
        inst2 = ShoonyaInstrument(
            instrument_token="99999",
            exchange_token="1111",
            tradingsymbol="INFY",
            name="INFOSYS",
            last_price=Decimal("1500.0"),
            expiry=None,
            strike=None,
            tick_size=Decimal("0.05"),
            lot_size=1,
            instrument_type="EQ",
            segment="BSE",
            exchange="BSE",
        )
        master._tradingsymbol_index["INFY"] = [inst1, inst2]
        master._loaded = True
        master._metadata = CacheMetadata(
            timestamp=datetime.now(IST).isoformat(),
            record_count=2,
            segments=["NSE", "BSE"],
        )

        with pytest.raises(AmbiguousSymbolError):
            await master.resolve_symbol("INFY")

    @pytest.mark.asyncio
    async def test_resolve_symbol_not_found(self) -> None:
        """Test unknown symbol raises SymbolNotFoundError."""
        mock_session = MagicMock(spec=ShoonyaSession)
        master = InstrumentMaster(mock_session)
        master._loaded = True
        master._metadata = CacheMetadata(
            timestamp=datetime.now(IST).isoformat(),
            record_count=0,
            segments=["NSE"],
        )

        with pytest.raises(SymbolNotFoundError):
            await master.resolve_symbol("NSE:UNKNOWN")

    def test_find_suggestions(self) -> None:
        """Test finding similar symbol suggestions."""
        mock_session = MagicMock(spec=ShoonyaSession)
        master = InstrumentMaster(mock_session)

        instrument = ShoonyaInstrument(
            instrument_token="2885",
            exchange_token="1594",
            tradingsymbol="INFY",
            name="INFOSYS",
            last_price=Decimal("1500.0"),
            expiry=None,
            strike=None,
            tick_size=Decimal("0.05"),
            lot_size=1,
            instrument_type="EQ",
            segment="NSE",
            exchange="NSE",
        )
        master._exact_index["NSE:INFY"] = instrument
        master._loaded = True

        suggestions = master._find_suggestions("INFY")
        assert "NSE:INFY" in suggestions

    def test_is_fresh_no_metadata(self) -> None:
        """Test is_fresh returns False when no metadata."""
        mock_session = MagicMock(spec=ShoonyaSession)
        master = InstrumentMaster(mock_session)
        assert not master.is_fresh()

    def test_get_stats(self) -> None:
        """Test get_stats returns cache statistics."""
        mock_session = MagicMock(spec=ShoonyaSession)
        master = InstrumentMaster(mock_session)

        stats = master.get_stats()
        assert "loaded" in stats
        assert "record_count" in stats
        assert "cache_dir" in stats
        assert "segments" in stats
        assert stats["segments"] == ["NSE"]
