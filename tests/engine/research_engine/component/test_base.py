"""Tests for ResearchComponent base class."""

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit
from quantrex.engine.research_engine.component.base import ResearchComponent
from datetime import UTC, datetime
from decimal import Decimal


class TestResearchComponent:
    """Tests for ResearchComponent."""

    def test_on_candle_is_noop(self) -> None:
        component = ResearchComponent()
        candle = OHLCVCandle(
            symbol="RELIANCE",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=Decimal("1000"),
            timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        )
        # Should not raise
        component.on_candle(candle)
