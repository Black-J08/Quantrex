"""Tests for market data models."""

from __future__ import annotations

import pytest
from decimal import Decimal
from datetime import datetime, timezone

from quantrex.core.models import (
    OHLCVCandle,
    Tick,
    Timeframe,
    TimeframeUnit,
)


class TestTimeframe:
    """Tests for Timeframe."""

    def test_creation(self) -> None:
        tf = Timeframe(value=1, unit=TimeframeUnit.MINUTE)
        assert tf.value == 1
        assert tf.unit == TimeframeUnit.MINUTE

    def test_str_representation(self) -> None:
        assert str(Timeframe(value=1, unit=TimeframeUnit.MINUTE)) == "1m"
        assert str(Timeframe(value=5, unit=TimeframeUnit.MINUTE)) == "5m"
        assert str(Timeframe(value=1, unit=TimeframeUnit.HOUR)) == "1h"
        assert str(Timeframe(value=1, unit=TimeframeUnit.DAY)) == "1d"

    def test_from_string(self) -> None:
        tf = Timeframe.from_string("15m")
        assert tf.value == 15
        assert tf.unit == TimeframeUnit.MINUTE

        tf = Timeframe.from_string("1h")
        assert tf.value == 1
        assert tf.unit == TimeframeUnit.HOUR

        tf = Timeframe.from_string("1d")
        assert tf.value == 1
        assert tf.unit == TimeframeUnit.DAY

    def test_from_string_invalid(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            Timeframe.from_string("")

        with pytest.raises(ValueError, match="invalid timeframe format"):
            Timeframe.from_string("abc")

        with pytest.raises(ValueError, match="invalid timeframe unit"):
            Timeframe.from_string("1x")

    def test_comparison(self) -> None:
        tf1m = Timeframe(value=1, unit=TimeframeUnit.MINUTE)
        tf5m = Timeframe(value=5, unit=TimeframeUnit.MINUTE)
        tf1h = Timeframe(value=1, unit=TimeframeUnit.HOUR)

        assert tf1m < tf5m
        assert tf5m > tf1m
        assert tf1h > tf5m
        assert tf1m <= tf1m
        assert tf5m >= tf1m

    def test_to_timedelta(self) -> None:
        tf1m = Timeframe(value=1, unit=TimeframeUnit.MINUTE)
        tf1h = Timeframe(value=1, unit=TimeframeUnit.HOUR)
        tf1d = Timeframe(value=1, unit=TimeframeUnit.DAY)

        assert tf1m.to_timedelta().total_seconds() == 60
        assert tf1h.to_timedelta().total_seconds() == 3600
        assert tf1d.to_timedelta().total_seconds() == 86400

    def test_zero_value_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            Timeframe(value=0, unit=TimeframeUnit.MINUTE)

    def test_negative_value_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            Timeframe(value=-1, unit=TimeframeUnit.MINUTE)

    def test_immutability(self) -> None:
        tf = Timeframe(value=1, unit=TimeframeUnit.MINUTE)
        with pytest.raises(Exception):
            tf.value = 5


class TestOHLCVCandle:
    """Tests for OHLCVCandle."""

    def test_valid_creation(self) -> None:
        bar = OHLCVCandle(
            symbol="AAPL",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            open=Decimal("150.0"),
            high=Decimal("151.0"),
            low=Decimal("149.0"),
            close=Decimal("150.5"),
            volume=Decimal("1000"),
        )
        assert bar.symbol == "AAPL"
        assert bar.timeframe.value == 1
        assert bar.timeframe.unit == TimeframeUnit.MINUTE
        assert bar.open == Decimal("150.0")
        assert bar.high == Decimal("151.0")
        assert bar.low == Decimal("149.0")
        assert bar.close == Decimal("150.5")
        assert bar.volume == Decimal("1000")

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ValueError, match="symbol cannot be empty"):
            OHLCVCandle(
                symbol="",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                open=Decimal("150"),
                high=Decimal("151"),
                low=Decimal("149"),
                close=Decimal("150"),
                volume=Decimal("1000"),
            )

    def test_negative_open_raises(self) -> None:
        with pytest.raises(ValueError, match="open price cannot be negative"):
            OHLCVCandle(
                symbol="AAPL",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                open=Decimal("-150"),
                high=Decimal("151"),
                low=Decimal("149"),
                close=Decimal("150"),
                volume=Decimal("1000"),
            )

    def test_negative_high_raises(self) -> None:
        with pytest.raises(ValueError, match="high price cannot be negative"):
            OHLCVCandle(
                symbol="AAPL",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                open=Decimal("150"),
                high=Decimal("-151"),
                low=Decimal("149"),
                close=Decimal("150"),
                volume=Decimal("1000"),
            )

    def test_negative_low_raises(self) -> None:
        with pytest.raises(ValueError, match="low price cannot be negative"):
            OHLCVCandle(
                symbol="AAPL",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                open=Decimal("150"),
                high=Decimal("151"),
                low=Decimal("-149"),
                close=Decimal("150"),
                volume=Decimal("1000"),
            )

    def test_negative_close_raises(self) -> None:
        with pytest.raises(ValueError, match="close price cannot be negative"):
            OHLCVCandle(
                symbol="AAPL",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                open=Decimal("150"),
                high=Decimal("151"),
                low=Decimal("149"),
                close=Decimal("-150"),
                volume=Decimal("1000"),
            )

    def test_negative_volume_raises(self) -> None:
        with pytest.raises(ValueError, match="volume cannot be negative"):
            OHLCVCandle(
                symbol="AAPL",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                open=Decimal("150"),
                high=Decimal("151"),
                low=Decimal("149"),
                close=Decimal("150"),
                volume=Decimal("-1000"),
            )

    def test_high_less_than_low_raises(self) -> None:
        with pytest.raises(ValueError, match="high must be >="):
            OHLCVCandle(
                symbol="AAPL",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                open=Decimal("150"),
                high=Decimal("149"),
                low=Decimal("151"),
                close=Decimal("150"),
                volume=Decimal("1000"),
            )

    def test_high_less_than_open_raises(self) -> None:
        with pytest.raises(ValueError, match="high must be >="):
            OHLCVCandle(
                symbol="AAPL",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                open=Decimal("152"),
                high=Decimal("151"),
                low=Decimal("149"),
                close=Decimal("150"),
                volume=Decimal("1000"),
            )

    def test_high_less_than_close_raises(self) -> None:
        with pytest.raises(ValueError, match="high must be >="):
            OHLCVCandle(
                symbol="AAPL",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                open=Decimal("150"),
                high=Decimal("151"),
                low=Decimal("149"),
                close=Decimal("152"),
                volume=Decimal("1000"),
            )

    def test_low_greater_than_open_raises(self) -> None:
        with pytest.raises(ValueError, match="low must be <="):
            OHLCVCandle(
                symbol="AAPL",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                open=Decimal("148"),
                high=Decimal("151"),
                low=Decimal("149"),
                close=Decimal("150"),
                volume=Decimal("1000"),
            )

    def test_low_greater_than_close_raises(self) -> None:
        with pytest.raises(ValueError, match="low must be <="):
            OHLCVCandle(
                symbol="AAPL",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                open=Decimal("150"),
                high=Decimal("151"),
                low=Decimal("149"),
                close=Decimal("148"),
                volume=Decimal("1000"),
            )

    def test_valid_ohlc_relationships(self) -> None:
        """Test valid OHLC relationships pass."""
        # High = Open = Close > Low
        OHLCVCandle(
            symbol="AAPL",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            open=Decimal("150"),
            high=Decimal("150"),
            low=Decimal("149"),
            close=Decimal("150"),
            volume=Decimal("1000"),
        )
        # Low = Open = Close < High
        OHLCVCandle(
            symbol="AAPL",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            open=Decimal("150"),
            high=Decimal("151"),
            low=Decimal("150"),
            close=Decimal("150"),
            volume=Decimal("1000"),
        )

    def test_immutability(self) -> None:
        bar = OHLCVCandle(
            symbol="AAPL",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            open=Decimal("150"),
            high=Decimal("151"),
            low=Decimal("149"),
            close=Decimal("150"),
            volume=Decimal("1000"),
        )
        with pytest.raises(Exception):
            bar.symbol = "GOOGL"


class TestTick:
    """Tests for Tick."""

    def test_valid_creation(self) -> None:
        tick = Tick(
            symbol="AAPL",
            price=Decimal("150.25"),
        )
        assert tick.symbol == "AAPL"
        assert tick.price == Decimal("150.25")

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ValueError, match="symbol cannot be empty"):
            Tick(symbol="", price=Decimal("150"))

    def test_negative_price_raises(self) -> None:
        with pytest.raises(ValueError, match="price cannot be negative"):
            Tick(symbol="AAPL", price=Decimal("-150"))

    def test_immutability(self) -> None:
        tick = Tick(symbol="AAPL", price=Decimal("150"))
        with pytest.raises(Exception):
            tick.symbol = "GOOGL"