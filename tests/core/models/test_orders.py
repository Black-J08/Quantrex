"""Tests for order models."""

from __future__ import annotations

import pytest
from decimal import Decimal
from datetime import datetime, timezone

from quantrex.core.models import (
    Order,
    OrderType,
    OrderSide,
    OrderStatus,
)


class TestOrderType:
    """Tests for OrderType enum."""

    def test_values(self) -> None:
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderType.STOP.value == "STOP"
        assert OrderType.STOP_LIMIT.value == "STOP_LIMIT"


class TestOrderSide:
    """Tests for OrderSide enum."""

    def test_values(self) -> None:
        assert OrderSide.BUY.value == "BUY"
        assert OrderSide.SELL.value == "SELL"


class TestOrderStatus:
    """Tests for OrderStatus enum."""

    def test_values(self) -> None:
        assert OrderStatus.PENDING.value == "PENDING"
        assert OrderStatus.FILLED.value == "FILLED"
        assert OrderStatus.CANCELLED.value == "CANCELLED"
        assert OrderStatus.REJECTED.value == "REJECTED"


class TestOrder:
    """Tests for Order."""

    def test_market_order_creation(self) -> None:
        """Test creating a market order."""
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("100"),
        )
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.MARKET
        assert order.quantity == Decimal("100")
        assert order.price is None
        assert order.status == OrderStatus.PENDING

    def test_limit_order_creation(self) -> None:
        """Test creating a limit order."""
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            quantity=Decimal("100"),
            price=Decimal("150.0"),
        )
        assert order.type == OrderType.LIMIT
        assert order.price == Decimal("150.0")

    def test_stop_order_creation(self) -> None:
        """Test creating a stop order."""
        order = Order(
            symbol="AAPL",
            side=OrderSide.SELL,
            type=OrderType.STOP,
            quantity=Decimal("100"),
            price=Decimal("145.0"),
        )
        assert order.type == OrderType.STOP
        assert order.price == Decimal("145.0")

    def test_stop_limit_order_creation(self) -> None:
        """Test creating a stop-limit order."""
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            type=OrderType.STOP_LIMIT,
            quantity=Decimal("100"),
            price=Decimal("155.0"),
        )
        assert order.type == OrderType.STOP_LIMIT
        assert order.price == Decimal("155.0")

    def test_limit_without_price_raises(self) -> None:
        """Test that limit order without price raises."""
        with pytest.raises(ValueError, match="price is required for LIMIT"):
            Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                quantity=Decimal("100"),
            )

    def test_stop_limit_without_price_raises(self) -> None:
        """Test that stop-limit order without price raises."""
        with pytest.raises(ValueError, match="price is required for STOP_LIMIT"):
            Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                type=OrderType.STOP_LIMIT,
                quantity=Decimal("100"),
            )

    def test_negative_price_raises(self) -> None:
        """Test that negative price raises."""
        with pytest.raises(ValueError, match="price cannot be negative"):
            Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                quantity=Decimal("100"),
                price=Decimal("-150"),
            )

    def test_zero_quantity_raises(self) -> None:
        """Test that zero quantity raises."""
        with pytest.raises(ValueError, match="quantity must be positive"):
            Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                quantity=Decimal("0"),
            )

    def test_negative_quantity_raises(self) -> None:
        """Test that negative quantity raises."""
        with pytest.raises(ValueError, match="quantity must be positive"):
            Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                quantity=Decimal("-100"),
            )

    def test_empty_symbol_raises(self) -> None:
        """Test that empty symbol raises."""
        with pytest.raises(ValueError, match="symbol cannot be empty"):
            Order(
                symbol="",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                quantity=Decimal("100"),
            )

    def test_naive_created_at_raises(self) -> None:
        """Test that naive created_at raises."""
        with pytest.raises(ValueError, match="timezone-aware"):
            Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                quantity=Decimal("100"),
                created_at=datetime.now(),
            )

    def test_naive_updated_at_raises(self) -> None:
        """Test that naive updated_at raises."""
        with pytest.raises(ValueError, match="timezone-aware"):
            Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                quantity=Decimal("100"),
                updated_at=datetime.now(),
            )

    def test_custom_timestamps(self) -> None:
        """Test custom timestamps."""
        ts = datetime.now(timezone.utc)
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("100"),
            created_at=ts,
            updated_at=ts,
        )
        assert order.created_at == ts
        assert order.updated_at == ts

    def test_immutability(self) -> None:
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("100"),
        )
        with pytest.raises(Exception):
            order.symbol = "GOOGL"