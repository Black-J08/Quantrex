"""Tests for the abstract HistoricalDataProvider base class."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quantrex.core.data.historical.provider import HistoricalDataProvider
from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit


class ConcreteProvider(HistoricalDataProvider):
    """Concrete implementation for testing the abstract base class."""

    def __init__(self) -> None:
        self._closed = False

    async def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime,
        **kwargs: object,
    ) -> list[OHLCVCandle]:
        return []

    def supported_timeframes(self) -> list[Timeframe]:
        return [Timeframe(value=1, unit=TimeframeUnit.MINUTE)]

    async def close(self) -> None:
        self._closed = True


class TestHistoricalDataProvider:
    """Tests for HistoricalDataProvider abstract base class."""

    def test_cannot_instantiate_abstract(self) -> None:
        """Test that the abstract class cannot be instantiated directly."""
        with pytest.raises(TypeError):
            HistoricalDataProvider()  # type: ignore[abstract]

    def test_concrete_implementation(self) -> None:
        """Test that a concrete implementation can be instantiated."""
        provider = ConcreteProvider()
        assert isinstance(provider, HistoricalDataProvider)

    @pytest.mark.asyncio
    async def test_get_candles_returns_list(self) -> None:
        """Test that get_candles returns a list of candles."""
        provider = ConcreteProvider()
        candles = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            from_date=datetime(2024, 1, 1, tzinfo=UTC),
            to_date=datetime(2024, 1, 2, tzinfo=UTC),
        )
        assert isinstance(candles, list)

    def test_supported_timeframes(self) -> None:
        """Test supported_timeframes returns a list of Timeframe."""
        provider = ConcreteProvider()
        timeframes = provider.supported_timeframes()
        assert isinstance(timeframes, list)
        assert len(timeframes) == 1
        assert timeframes[0] == Timeframe(value=1, unit=TimeframeUnit.MINUTE)

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        """Test that close marks the provider as closed."""
        provider = ConcreteProvider()
        await provider.close()
        assert provider._closed is True

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        """Test async context manager protocol."""
        async with ConcreteProvider() as provider:
            assert isinstance(provider, HistoricalDataProvider)
        assert provider._closed is True

    @pytest.mark.asyncio
    async def test_async_context_manager_closes_on_exception(self) -> None:
        """Test that __aexit__ closes the provider even on exception."""
        provider = ConcreteProvider()
        try:
            async with provider:
                raise RuntimeError("test error")
        except RuntimeError:
            pass
        assert provider._closed is True
