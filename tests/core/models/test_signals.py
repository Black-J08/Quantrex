"""Tests for signal models."""

from __future__ import annotations

import pytest
from decimal import Decimal

from quantrex.core.models import (
    Signal,
    SignalType,
)


class TestSignalType:
    """Tests for SignalType enum."""

    def test_values(self) -> None:
        assert SignalType.ENTRY_LONG.value == "ENTRY_LONG"
        assert SignalType.ENTRY_SHORT.value == "ENTRY_SHORT"
        assert SignalType.EXIT_LONG.value == "EXIT_LONG"
        assert SignalType.EXIT_SHORT.value == "EXIT_SHORT"


class TestSignal:
    """Tests for Signal."""

    def test_entry_long_creation(self) -> None:
        """Test creating an entry long signal."""
        signal = Signal(
            symbol="AAPL",
            signal_type=SignalType.ENTRY_LONG,
            price=Decimal("150.0"),
            quantity=Decimal("100"),
        )
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.ENTRY_LONG
        assert signal.price == Decimal("150.0")
        assert signal.quantity == Decimal("100")

    def test_entry_short_creation(self) -> None:
        """Test creating an entry short signal."""
        signal = Signal(
            symbol="AAPL",
            signal_type=SignalType.ENTRY_SHORT,
            price=Decimal("150.0"),
            quantity=Decimal("100"),
        )
        assert signal.signal_type == SignalType.ENTRY_SHORT

    def test_exit_long_creation(self) -> None:
        """Test creating an exit long signal."""
        signal = Signal(
            symbol="AAPL",
            signal_type=SignalType.EXIT_LONG,
            price=Decimal("155.0"),
        )
        assert signal.signal_type == SignalType.EXIT_LONG
        assert signal.quantity is None

    def test_exit_short_creation(self) -> None:
        """Test creating an exit short signal."""
        signal = Signal(
            symbol="AAPL",
            signal_type=SignalType.EXIT_SHORT,
            price=Decimal("145.0"),
        )
        assert signal.signal_type == SignalType.EXIT_SHORT

    def test_empty_symbol_raises(self) -> None:
        """Test that empty symbol raises."""
        with pytest.raises(ValueError, match="symbol cannot be empty"):
            Signal(
                symbol="",
                signal_type=SignalType.ENTRY_LONG,
                price=Decimal("150.0"),
            )

    def test_negative_price_raises(self) -> None:
        """Test that negative price raises."""
        with pytest.raises(ValueError, match="price cannot be negative"):
            Signal(
                symbol="AAPL",
                signal_type=SignalType.ENTRY_LONG,
                price=Decimal("-150.0"),
            )

    def test_zero_quantity_raises(self) -> None:
        """Test that zero quantity raises."""
        with pytest.raises(ValueError, match="quantity must be positive"):
            Signal(
                symbol="AAPL",
                signal_type=SignalType.ENTRY_LONG,
                price=Decimal("150.0"),
                quantity=Decimal("0"),
            )

    def test_negative_quantity_raises(self) -> None:
        """Test that negative quantity raises."""
        with pytest.raises(ValueError, match="quantity must be positive"):
            Signal(
                symbol="AAPL",
                signal_type=SignalType.ENTRY_LONG,
                price=Decimal("150.0"),
                quantity=Decimal("-100"),
            )

    def test_optional_quantity(self) -> None:
        """Test that quantity is optional."""
        signal = Signal(
            symbol="AAPL",
            signal_type=SignalType.EXIT_LONG,
            price=Decimal("155.0"),
        )
        assert signal.quantity is None

    def test_immutability(self) -> None:
        signal = Signal(
            symbol="AAPL",
            signal_type=SignalType.ENTRY_LONG,
            price=Decimal("150.0"),
        )
        with pytest.raises(Exception):
            signal.symbol = "GOOGL"