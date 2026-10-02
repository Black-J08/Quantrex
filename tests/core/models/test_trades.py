"""Tests for trade models."""

from __future__ import annotations

import pytest
from decimal import Decimal
from datetime import datetime, timezone

from quantrex.core.models import Trade


class TestTrade:
    """Tests for Trade."""

    def test_valid_creation(self) -> None:
        """Test creating a valid trade."""
        entry_time = datetime.now(timezone.utc)
        exit_time = datetime.now(timezone.utc)
        trade = Trade(
            symbol="AAPL",
            side="BUY",
            quantity=Decimal("100"),
            entry_price=Decimal("150.0"),
            exit_price=Decimal("155.0"),
            entry_time=entry_time,
            exit_time=exit_time,
            entry_reason="Signal",
            exit_reason="Take Profit",
            pnl=Decimal("500.0"),
        )
        assert trade.symbol == "AAPL"
        assert trade.side == "BUY"
        assert trade.quantity == Decimal("100")
        assert trade.entry_price == Decimal("150.0")
        assert trade.exit_price == Decimal("155.0")
        assert trade.entry_time == entry_time
        assert trade.exit_time == exit_time
        assert trade.entry_reason == "Signal"
        assert trade.exit_reason == "Take Profit"
        assert trade.pnl == Decimal("500.0")

    def test_sell_side(self) -> None:
        """Test trade with SELL side."""
        trade = Trade(
            symbol="AAPL",
            side="SELL",
            quantity=Decimal("100"),
            entry_price=Decimal("155.0"),
            exit_price=Decimal("150.0"),
            entry_time=datetime.now(timezone.utc),
            exit_time=datetime.now(timezone.utc),
            pnl=Decimal("500.0"),
        )
        assert trade.side == "SELL"

    def test_empty_symbol_raises(self) -> None:
        """Test that empty symbol raises."""
        with pytest.raises(ValueError, match="symbol cannot be empty"):
            Trade(
                symbol="",
                side="BUY",
                quantity=Decimal("100"),
                entry_price=Decimal("150"),
                exit_price=Decimal("155"),
                entry_time=datetime.now(timezone.utc),
                exit_time=datetime.now(timezone.utc),
                pnl=Decimal("500"),
            )

    def test_invalid_side_raises(self) -> None:
        """Test that invalid side raises."""
        with pytest.raises(ValueError, match="side must be 'BUY' or 'SELL'"):
            Trade(
                symbol="AAPL",
                side="INVALID",
                quantity=Decimal("100"),
                entry_price=Decimal("150"),
                exit_price=Decimal("155"),
                entry_time=datetime.now(timezone.utc),
                exit_time=datetime.now(timezone.utc),
                pnl=Decimal("500"),
            )

    def test_zero_quantity_raises(self) -> None:
        """Test that zero quantity raises."""
        with pytest.raises(ValueError, match="quantity must be positive"):
            Trade(
                symbol="AAPL",
                side="BUY",
                quantity=Decimal("0"),
                entry_price=Decimal("150"),
                exit_price=Decimal("155"),
                entry_time=datetime.now(timezone.utc),
                exit_time=datetime.now(timezone.utc),
                pnl=Decimal("500"),
            )

    def test_negative_quantity_raises(self) -> None:
        """Test that negative quantity raises."""
        with pytest.raises(ValueError, match="quantity must be positive"):
            Trade(
                symbol="AAPL",
                side="BUY",
                quantity=Decimal("-100"),
                entry_price=Decimal("150"),
                exit_price=Decimal("155"),
                entry_time=datetime.now(timezone.utc),
                exit_time=datetime.now(timezone.utc),
                pnl=Decimal("500"),
            )

    def test_negative_entry_price_raises(self) -> None:
        """Test that negative entry_price raises."""
        with pytest.raises(ValueError, match="entry_price cannot be negative"):
            Trade(
                symbol="AAPL",
                side="BUY",
                quantity=Decimal("100"),
                entry_price=Decimal("-150"),
                exit_price=Decimal("155"),
                entry_time=datetime.now(timezone.utc),
                exit_time=datetime.now(timezone.utc),
                pnl=Decimal("500"),
            )

    def test_negative_exit_price_raises(self) -> None:
        """Test that negative exit_price raises."""
        with pytest.raises(ValueError, match="exit_price cannot be negative"):
            Trade(
                symbol="AAPL",
                side="BUY",
                quantity=Decimal("100"),
                entry_price=Decimal("150"),
                exit_price=Decimal("-155"),
                entry_time=datetime.now(timezone.utc),
                exit_time=datetime.now(timezone.utc),
                pnl=Decimal("500"),
            )

    def test_naive_entry_time_raises(self) -> None:
        """Test that naive entry_time raises."""
        with pytest.raises(ValueError, match="timezone-aware"):
            Trade(
                symbol="AAPL",
                side="BUY",
                quantity=Decimal("100"),
                entry_price=Decimal("150"),
                exit_price=Decimal("155"),
                entry_time=datetime.now(),
                exit_time=datetime.now(timezone.utc),
                pnl=Decimal("500"),
            )

    def test_naive_exit_time_raises(self) -> None:
        """Test that naive exit_time raises."""
        with pytest.raises(ValueError, match="timezone-aware"):
            Trade(
                symbol="AAPL",
                side="BUY",
                quantity=Decimal("100"),
                entry_price=Decimal("150"),
                exit_price=Decimal("155"),
                entry_time=datetime.now(timezone.utc),
                exit_time=datetime.now(),
                pnl=Decimal("500"),
            )

    def test_exit_before_entry_raises(self) -> None:
        """Test that exit_time before entry_time raises."""
        entry_time = datetime.now(timezone.utc)
        exit_time = entry_time.replace(hour=entry_time.hour - 1)
        with pytest.raises(ValueError, match="exit_time must be >="):
            Trade(
                symbol="AAPL",
                side="BUY",
                quantity=Decimal("100"),
                entry_price=Decimal("150"),
                exit_price=Decimal("155"),
                entry_time=entry_time,
                exit_time=exit_time,
                pnl=Decimal("500"),
            )

    def test_optional_reasons(self) -> None:
        """Test that entry_reason and exit_reason are optional."""
        trade = Trade(
            symbol="AAPL",
            side="BUY",
            quantity=Decimal("100"),
            entry_price=Decimal("150"),
            exit_price=Decimal("155"),
            entry_time=datetime.now(timezone.utc),
            exit_time=datetime.now(timezone.utc),
            pnl=Decimal("500"),
        )
        assert trade.entry_reason is None
        assert trade.exit_reason is None

    def test_immutability(self) -> None:
        trade = Trade(
            symbol="AAPL",
            side="BUY",
            quantity=Decimal("100"),
            entry_price=Decimal("150"),
            exit_price=Decimal("155"),
            entry_time=datetime.now(timezone.utc),
            exit_time=datetime.now(timezone.utc),
            pnl=Decimal("500"),
        )
        with pytest.raises(Exception):
            trade.symbol = "GOOGL"