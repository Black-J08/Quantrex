"""Tests for position models."""

from __future__ import annotations

import pytest
from decimal import Decimal
from datetime import datetime, timezone

from quantrex.core.models import (
    Position,
    PositionSide,
)


class TestPositionSide:
    """Tests for PositionSide enum."""

    def test_values(self) -> None:
        assert PositionSide.LONG.value == "LONG"
        assert PositionSide.SHORT.value == "SHORT"


class TestPosition:
    """Tests for Position."""

    def test_long_position_creation(self) -> None:
        """Test creating a long position."""
        pos = Position(
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=Decimal("100"),
            entry_price=Decimal("150.0"),
            current_price=Decimal("151.0"),
            unrealized_pnl=Decimal("100.0"),
        )
        assert pos.symbol == "AAPL"
        assert pos.side == PositionSide.LONG
        assert pos.quantity == Decimal("100")
        assert pos.entry_price == Decimal("150.0")
        assert pos.current_price == Decimal("151.0")
        assert pos.unrealized_pnl == Decimal("100.0")

    def test_short_position_creation(self) -> None:
        """Test creating a short position."""
        pos = Position(
            symbol="AAPL",
            side=PositionSide.SHORT,
            quantity=Decimal("-100"),
            entry_price=Decimal("150.0"),
            current_price=Decimal("149.0"),
            unrealized_pnl=Decimal("100.0"),
        )
        assert pos.side == PositionSide.SHORT
        assert pos.quantity == Decimal("-100")

    def test_long_with_negative_quantity_raises(self) -> None:
        """Test that long position with negative quantity raises."""
        with pytest.raises(ValueError, match="positive for LONG"):
            Position(
                symbol="AAPL",
                side=PositionSide.LONG,
                quantity=Decimal("-100"),
                entry_price=Decimal("150.0"),
                current_price=Decimal("151.0"),
                unrealized_pnl=Decimal("100.0"),
            )

    def test_long_with_zero_quantity_raises(self) -> None:
        """Test that long position with zero quantity raises."""
        with pytest.raises(ValueError, match="positive for LONG"):
            Position(
                symbol="AAPL",
                side=PositionSide.LONG,
                quantity=Decimal("0"),
                entry_price=Decimal("150.0"),
                current_price=Decimal("151.0"),
                unrealized_pnl=Decimal("100.0"),
            )

    def test_short_with_positive_quantity_raises(self) -> None:
        """Test that short position with positive quantity raises."""
        with pytest.raises(ValueError, match="negative for SHORT"):
            Position(
                symbol="AAPL",
                side=PositionSide.SHORT,
                quantity=Decimal("100"),
                entry_price=Decimal("150.0"),
                current_price=Decimal("149.0"),
                unrealized_pnl=Decimal("100.0"),
            )

    def test_short_with_zero_quantity_raises(self) -> None:
        """Test that short position with zero quantity raises."""
        with pytest.raises(ValueError, match="negative for SHORT"):
            Position(
                symbol="AAPL",
                side=PositionSide.SHORT,
                quantity=Decimal("0"),
                entry_price=Decimal("150.0"),
                current_price=Decimal("149.0"),
                unrealized_pnl=Decimal("100.0"),
            )

    def test_negative_entry_price_raises(self) -> None:
        """Test that negative entry_price raises."""
        with pytest.raises(ValueError, match="entry_price cannot be negative"):
            Position(
                symbol="AAPL",
                side=PositionSide.LONG,
                quantity=Decimal("100"),
                entry_price=Decimal("-150"),
                current_price=Decimal("151.0"),
                unrealized_pnl=Decimal("100.0"),
            )

    def test_negative_current_price_raises(self) -> None:
        """Test that negative current_price raises."""
        with pytest.raises(ValueError, match="current_price cannot be negative"):
            Position(
                symbol="AAPL",
                side=PositionSide.LONG,
                quantity=Decimal("100"),
                entry_price=Decimal("150.0"),
                current_price=Decimal("-151"),
                unrealized_pnl=Decimal("100.0"),
            )

    def test_empty_symbol_raises(self) -> None:
        """Test that empty symbol raises."""
        with pytest.raises(ValueError, match="symbol cannot be empty"):
            Position(
                symbol="",
                side=PositionSide.LONG,
                quantity=Decimal("100"),
                entry_price=Decimal("150.0"),
                current_price=Decimal("151.0"),
                unrealized_pnl=Decimal("100.0"),
            )

    def test_naive_entry_time_raises(self) -> None:
        """Test that naive entry_time raises."""
        with pytest.raises(ValueError, match="timezone-aware"):
            Position(
                symbol="AAPL",
                side=PositionSide.LONG,
                quantity=Decimal("100"),
                entry_price=Decimal("150.0"),
                current_price=Decimal("151.0"),
                unrealized_pnl=Decimal("100.0"),
                entry_time=datetime.now(),
            )

    def test_custom_entry_time(self) -> None:
        """Test custom entry_time."""
        ts = datetime.now(timezone.utc)
        pos = Position(
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=Decimal("100"),
            entry_price=Decimal("150.0"),
            current_price=Decimal("151.0"),
            unrealized_pnl=Decimal("100.0"),
            entry_time=ts,
        )
        assert pos.entry_time == ts

    def test_immutability(self) -> None:
        pos = Position(
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=Decimal("100"),
            entry_price=Decimal("150.0"),
            current_price=Decimal("151.0"),
            unrealized_pnl=Decimal("100.0"),
        )
        with pytest.raises(Exception):
            pos.symbol = "GOOGL"