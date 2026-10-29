"""Tests for Zerodha broker models."""

from __future__ import annotations

import pytest

from quantrex.core.broker.zerodha.models.models import (
    InstrumentToken,
    SymbolMapping,
    ZerodhaInterval,
)


class TestZerodhaInterval:
    """Tests for ZerodhaInterval enum."""

    def test_minute_value(self) -> None:
        """Test MINUTE interval value."""
        assert ZerodhaInterval.MINUTE == "minute"

    def test_three_minute_value(self) -> None:
        """Test THREE_MINUTE interval value."""
        assert ZerodhaInterval.THREE_MINUTE == "3minute"

    def test_five_minute_value(self) -> None:
        """Test FIVE_MINUTE interval value."""
        assert ZerodhaInterval.FIVE_MINUTE == "5minute"

    def test_ten_minute_value(self) -> None:
        """Test TEN_MINUTE interval value."""
        assert ZerodhaInterval.TEN_MINUTE == "10minute"

    def test_fifteen_minute_value(self) -> None:
        """Test FIFTEEN_MINUTE interval value."""
        assert ZerodhaInterval.FIFTEEN_MINUTE == "15minute"

    def test_thirty_minute_value(self) -> None:
        """Test THIRTY_MINUTE interval value."""
        assert ZerodhaInterval.THIRTY_MINUTE == "30minute"

    def test_sixty_minute_value(self) -> None:
        """Test SIXTY_MINUTE interval value."""
        assert ZerodhaInterval.SIXTY_MINUTE == "60minute"

    def test_day_value(self) -> None:
        """Test DAY interval value."""
        assert ZerodhaInterval.DAY == "day"

    def test_all_intervals_are_strings(self) -> None:
        """Test that all interval values are strings."""
        for interval in ZerodhaInterval:
            assert isinstance(interval.value, str)


class TestInstrumentToken:
    """Tests for InstrumentToken dataclass."""

    def test_creation(self) -> None:
        """Test creating an InstrumentToken."""
        token = InstrumentToken(value=408065)
        assert token.value == 408065

    def test_str(self) -> None:
        """Test string representation."""
        token = InstrumentToken(value=408065)
        assert str(token) == "408065"

    def test_equality(self) -> None:
        """Test equality comparison."""
        assert InstrumentToken(value=1) == InstrumentToken(value=1)
        assert InstrumentToken(value=1) != InstrumentToken(value=2)

    def test_frozen(self) -> None:
        """Test that InstrumentToken is frozen."""
        token = InstrumentToken(value=1)
        with pytest.raises(AttributeError):
            token.value = 2


class TestSymbolMapping:
    """Tests for SymbolMapping dataclass."""

    def test_creation(self) -> None:
        """Test creating a SymbolMapping."""
        token = InstrumentToken(value=408065)
        mapping = SymbolMapping(
            symbol="NSE:INFY",
            instrument_token=token,
            exchange="NSE",
            tradingsymbol="INFY",
        )
        assert mapping.symbol == "NSE:INFY"
        assert mapping.instrument_token == token
        assert mapping.exchange == "NSE"
        assert mapping.tradingsymbol == "INFY"

    def test_equality(self) -> None:
        """Test equality comparison."""
        token = InstrumentToken(value=408065)
        mapping1 = SymbolMapping(
            symbol="NSE:INFY",
            instrument_token=token,
            exchange="NSE",
            tradingsymbol="INFY",
        )
        mapping2 = SymbolMapping(
            symbol="NSE:INFY",
            instrument_token=token,
            exchange="NSE",
            tradingsymbol="INFY",
        )
        assert mapping1 == mapping2

    def test_frozen(self) -> None:
        """Test that SymbolMapping is frozen."""
        token = InstrumentToken(value=408065)
        mapping = SymbolMapping(
            symbol="NSE:INFY",
            instrument_token=token,
            exchange="NSE",
            tradingsymbol="INFY",
        )
        with pytest.raises(AttributeError):
            mapping.symbol = "NSE:RELIANCE"
