"""Tests for the Zerodha historical data provider (data layer)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantrex.core.broker.zerodha.exceptions.exceptions import (
    AmbiguousSymbolError,
    SymbolNotFoundError,
)
from quantrex.core.broker.zerodha.session.session import ZerodhaSession
from quantrex.core.data.cache import OHLCVCache
from quantrex.core.data.exceptions import (
    ProviderError,
    SymbolResolutionError,
    TimeframeNotSupportedError,
)
from quantrex.core.data.historical import ZerodhaHistoricalDataProvider
from quantrex.core.models import OHLCVCandle, Timeframe, TimeframeUnit

RAW_RESPONSE = {
    "status": "success",
    "data": {
        "candles": [
            ["2024-01-15T09:15:00+05:30", 1500.0, 1510.0, 1495.0, 1505.0, 100000],
            ["2024-01-15T09:16:00+05:30", 1505.0, 1515.0, 1500.0, 1510.0, 80000],
        ],
    },
}

FROM_DATE = datetime(2024, 1, 15, 9, 15, tzinfo=UTC)
TO_DATE = datetime(2024, 1, 15, 9, 16, tzinfo=UTC)
TIMEFRAME = Timeframe(value=1, unit=TimeframeUnit.MINUTE)


@pytest.fixture
def make_provider(tmp_path: Path):
    """Build a provider backed by an isolated temporary cache."""

    def _factory() -> tuple[ZerodhaHistoricalDataProvider, MagicMock]:
        mock_session = MagicMock(spec=ZerodhaSession)
        provider = ZerodhaHistoricalDataProvider(
            mock_session,
            cache=OHLCVCache(tmp_path),
        )
        return provider, provider._client

    return _factory


class TestZerodhaHistoricalDataProvider:
    """Tests for the consolidated ZerodhaHistoricalDataProvider."""

    def test_supported_timeframes(self, make_provider) -> None:
        """Test that supported timeframes are exposed."""
        provider, _ = make_provider()

        timeframes = provider.supported_timeframes()
        assert TIMEFRAME in timeframes
        assert Timeframe(value=1, unit=TimeframeUnit.DAY) in timeframes

    @pytest.mark.asyncio
    async def test_get_candles_normalizes_response(self, make_provider) -> None:
        """Test that raw vendor responses are normalized to canonical candles."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        candles = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )

        assert len(candles) == 2
        assert all(isinstance(c, OHLCVCandle) for c in candles)
        assert candles[0].symbol == "NSE:INFY"
        assert candles[0].open == Decimal("1500.0")
        assert candles[0].high == Decimal("1510.0")
        assert candles[0].low == Decimal("1495.0")
        assert candles[0].close == Decimal("1505.0")
        assert candles[0].volume == Decimal(100000)
        client.get_raw_candles.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unsupported_timeframe_raises(self, make_provider) -> None:
        """Test that an unsupported timeframe is rejected before any API call."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        with pytest.raises(TimeframeNotSupportedError):
            await provider.get_candles(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=2, unit=TimeframeUnit.HOUR),
                from_date=FROM_DATE,
                to_date=TO_DATE,
            )

        client.get_raw_candles.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_api_failure_raises_provider_error(self, make_provider) -> None:
        """Test that a client failure surfaces as ProviderError."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(ProviderError, match="API request failed"):
            await provider.get_candles(
                symbol="NSE:INFY",
                timeframe=TIMEFRAME,
                from_date=FROM_DATE,
                to_date=TO_DATE,
            )

    @pytest.mark.asyncio
    async def test_symbol_not_found_raises_resolution_error(self, make_provider) -> None:
        """Test that symbol resolution failures surface as SymbolResolutionError."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(side_effect=SymbolNotFoundError("NSE:UNKNOWN"))

        with pytest.raises(SymbolResolutionError):
            await provider.get_candles(
                symbol="NSE:UNKNOWN",
                timeframe=TIMEFRAME,
                from_date=FROM_DATE,
                to_date=TO_DATE,
            )

    @pytest.mark.asyncio
    async def test_ambiguous_symbol_raises_resolution_error(self, make_provider) -> None:
        """Test that ambiguous symbols surface as SymbolResolutionError."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(side_effect=AmbiguousSymbolError("INFY", []))

        with pytest.raises(SymbolResolutionError):
            await provider.get_candles(
                symbol="INFY",
                timeframe=TIMEFRAME,
                from_date=FROM_DATE,
                to_date=TO_DATE,
            )

    @pytest.mark.asyncio
    async def test_normalization_failure_raises_provider_error(self, make_provider) -> None:
        """Test that a malformed vendor response surfaces as ProviderError."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value={"status": "error", "message": "bad token"})

        with pytest.raises(ProviderError, match="Normalization failed"):
            await provider.get_candles(
                symbol="NSE:INFY",
                timeframe=TIMEFRAME,
                from_date=FROM_DATE,
                to_date=TO_DATE,
            )


class TestZerodhaHistoricalDataProviderCaching:
    """Tests for cache-aside behaviour inside the provider."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api_call(self, make_provider) -> None:
        """Test that a cache hit avoids the vendor API entirely."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        # First call populates the cache
        first = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )
        assert len(first) == 2
        assert client.get_raw_candles.await_count == 1

        # Second call is served from the cache
        second = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )
        assert len(second) == 2
        assert second[0].close == first[0].close
        assert client.get_raw_candles.await_count == 1  # No second API call

    @pytest.mark.asyncio
    async def test_cache_is_populated_on_miss(self, make_provider) -> None:
        """Test that a cache miss stores the fetched candles."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )

        cached = provider.cache.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=date(2024, 1, 15),
            to_date=date(2024, 1, 15),
        )
        assert cached is not None
        assert len(cached) == 2
        assert cached[0].open == Decimal("1500.0")

    @pytest.mark.asyncio
    async def test_different_symbols_use_separate_cache_entries(self, make_provider) -> None:
        """Test that cache entries are keyed per symbol."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )
        await provider.get_candles(
            symbol="NSE:RELIANCE",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )

        assert client.get_raw_candles.await_count == 2

    @pytest.mark.asyncio
    async def test_different_timeframes_use_separate_cache_entries(self, make_provider) -> None:
        """Test that cache entries are keyed per timeframe."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )
        await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=Timeframe(value=5, unit=TimeframeUnit.MINUTE),
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )

        assert client.get_raw_candles.await_count == 2
