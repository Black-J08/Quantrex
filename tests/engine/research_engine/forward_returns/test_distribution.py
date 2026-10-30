"""Tests for ForwardReturnsDistribution."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit

from quantrex.engine.research_engine.forward_returns.distribution import (
    ForwardReturnsDistribution,
)


def _make_candle(ts: datetime, close: Decimal) -> OHLCVCandle:
    return OHLCVCandle(
        symbol="RELIANCE",
        timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        open=close - Decimal("1"),
        high=close + Decimal("2"),
        low=close - Decimal("2"),
        close=close,
        volume=Decimal("1000"),
        timestamp=ts,
    )


class TestForwardReturnsDistribution:
    """Tests for ForwardReturnsDistribution."""

    def test_compute_forward_returns(self) -> None:
        base = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        candles = [
            _make_candle(base, Decimal("100")),
            _make_candle(base.replace(minute=1), Decimal("102")),
            _make_candle(base.replace(minute=2), Decimal("101")),
            _make_candle(base.replace(minute=3), Decimal("105")),
        ]

        events = [
            {
                "symbol": "RELIANCE",
                "direction": "long",
                "timestamp": base,
                "metadata": {},
            }
        ]

        dist = ForwardReturnsDistribution(horizons=[1, 2])
        results = dist.compute(candles, events)

        assert "1" in results
        assert "2" in results
        assert len(results["1"]) == 1
        assert len(results["2"]) == 1
        # Horizon 1: close at bar 1 / close at bar 0 - 1 = 102/100 - 1 = 0.02
        assert abs(results["1"][0] - 0.02) < 1e-9
        # Horizon 2: close at bar 2 / close at bar 0 - 1 = 101/100 - 1 = 0.01
        assert abs(results["2"][0] - 0.01) < 1e-9

    def test_event_after_last_candle_returns_empty(self) -> None:
        base = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        candles = [
            _make_candle(base, Decimal("100")),
        ]

        events = [
            {
                "symbol": "RELIANCE",
                "direction": "long",
                "timestamp": base.replace(minute=5),
                "metadata": {},
            }
        ]

        dist = ForwardReturnsDistribution(horizons=[1])
        results = dist.compute(candles, events)

        assert results["1"] == []

    def test_unknown_symbol_returns_empty(self) -> None:
        base = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        candles = [
            _make_candle(base, Decimal("100")),
        ]

        events = [
            {
                "symbol": "UNKNOWN",
                "direction": "long",
                "timestamp": base,
                "metadata": {},
            }
        ]

        dist = ForwardReturnsDistribution(horizons=[1])
        results = dist.compute(candles, events)

        assert results["1"] == []
