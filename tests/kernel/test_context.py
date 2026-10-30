"""Tests for KernelContext."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.orders import Order, OrderSide, OrderType
from quantrex.core.models.positions import Position, PositionSide
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit

from quantrex.kernel.context import KernelContext


def _make_candle() -> OHLCVCandle:
    return OHLCVCandle(
        symbol="RELIANCE",
        timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("99"),
        close=Decimal("104"),
        volume=Decimal("1000"),
        timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
    )


class TestKernelContext:
    """Tests for KernelContext."""

    def test_current_time_not_set_raises(self) -> None:
        ctx = KernelContext()
        with pytest.raises(RuntimeError, match="current_time has not been set yet"):
            _ = ctx.current_time

    def test_current_time_set_and_get(self) -> None:
        ctx = KernelContext()
        ts = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        ctx.current_time = ts
        assert ctx.current_time == ts

    def test_history_is_read_only_snapshot(self) -> None:
        ctx = KernelContext()
        candle = _make_candle()
        ctx.append_history(candle)
        hist = ctx.history
        assert isinstance(hist, tuple)
        assert len(hist) == 1
        # Mutating the returned tuple should not affect internal state
        hist_list = list(hist)
        hist_list.append(candle)
        assert len(ctx.history) == 1

    def test_submit_order_without_callback_raises(self) -> None:
        ctx = KernelContext()
        order = Order(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("1"),
        )
        with pytest.raises(NotImplementedError, match="submit_order is not available"):
            ctx.submit_order(order)

    def test_get_position_without_callback_raises(self) -> None:
        ctx = KernelContext()
        with pytest.raises(NotImplementedError, match="get_position is not available"):
            ctx.get_position("RELIANCE")

    def test_submit_order_delegates_to_callback(self) -> None:
        def cb(order: Order) -> Order:
            return order

        ctx = KernelContext(submit_order_cb=cb)
        order = Order(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("1"),
        )
        result = ctx.submit_order(order)
        assert result is order

    def test_get_position_delegates_to_callback(self) -> None:
        pos = Position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            current_price=Decimal("105"),
            unrealized_pnl=Decimal("50"),
            entry_time=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        )

        def cb(symbol: str) -> Position | None:
            return pos

        ctx = KernelContext(get_position_cb=cb)
        result = ctx.get_position("RELIANCE")
        assert result is pos

    def test_get_position_returns_none(self) -> None:
        def cb(symbol: str) -> Position | None:
            return None

        ctx = KernelContext(get_position_cb=cb)
        assert ctx.get_position("RELIANCE") is None
