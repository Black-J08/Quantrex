"""Tests for CandleReplay data feed."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit

from quantrex.engine.backtest_engine.data_feed.replay import CandleReplay


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


class TestCandleReplay:
    """Tests for CandleReplay."""

    def test_iterates_candles_in_order(self) -> None:
        ts1 = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        ts2 = datetime(2024, 1, 1, 10, 1, tzinfo=UTC)
        ts3 = datetime(2024, 1, 1, 10, 2, tzinfo=UTC)

        candles = [
            _make_candle(ts3, Decimal("103")),
            _make_candle(ts1, Decimal("101")),
            _make_candle(ts2, Decimal("102")),
        ]

        replay = CandleReplay(candles)
        result = list(replay)

        assert len(result) == 3
        assert result[0].timestamp == ts3
        assert result[1].timestamp == ts1
        assert result[2].timestamp == ts2

    def test_len(self) -> None:
        replay = CandleReplay([_make_candle(datetime(2024, 1, 1, 10, 0, tzinfo=UTC), Decimal("100"))])
        assert len(replay) == 1

    def test_empty(self) -> None:
        replay = CandleReplay([])
        assert len(replay) == 0
        assert list(replay) == []
