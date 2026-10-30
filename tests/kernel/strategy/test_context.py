"""Tests for StrategyContext helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit

from quantrex.kernel.context import KernelContext
from quantrex.kernel.strategy.context import StrategyContext


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


class TestStrategyContext:
    """Tests for StrategyContext."""

    def test_current_time_delegates(self) -> None:
        ctx = KernelContext()
        ts = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        ctx.current_time = ts
        strategy_ctx = StrategyContext(ctx)
        assert strategy_ctx.current_time == ts

    def test_history_delegates(self) -> None:
        ctx = KernelContext()
        candle = _make_candle()
        ctx.append_history(candle)
        strategy_ctx = StrategyContext(ctx)
        hist = strategy_ctx.history
        assert isinstance(hist, tuple)
        assert len(hist) == 1
        assert hist[0] is candle
