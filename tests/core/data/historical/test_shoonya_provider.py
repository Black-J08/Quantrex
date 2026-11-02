"""Tests for the Shoonya historical data provider (data layer)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantrex.core.broker.exceptions.exceptions import (
    AmbiguousSymbolError,
    SymbolNotFoundError,
)
from quantrex.core.broker.shoonya.session.session import ShoonyaSession
from quantrex.core.data.exceptions.exceptions import (
    ProviderError,
    SymbolResolutionError,
    TimeframeNotSupportedError,
)
from quantrex.core.data.historical.shoonya_provider import ShoonyaHistoricalDataProvider
from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit

# Shoonya TPSeries intraday response: flat list of candle dicts.
RAW_RESPONSE = [
    {
        "time": "07-12-2022 09:15:00",
        "into": "255.00",
        "inth": "255.65",
        "intl": "254.65",
        "intc": "255.65",
        "intv": "146",
        "v": "146",
        "oi": "0",
    },
    {
        "time": "07-12-2022 09:16:00",
        "into": "255.65",
        "inth": "256.00",
        "intl": "255.50",
        "intc": "255.90",
        "intv": "200",
        "v": "200",
        "oi": "0",
    },
]

# The vendor reports bar times in IST; the request window is given as the
# matching instants so that the mocked bars fall inside the requested range.
# The window is half-open, so it ends after the last mocked bar.
FROM_DATE = datetime(2022, 12, 7, 3, 45, tzinfo=UTC)
TO_DATE = datetime(2022, 12, 7, 3, 47, tzinfo=UTC)
TIMEFRAME = Timeframe(value=1, unit=TimeframeUnit.MINUTE)


@pytest.fixture
def make_provider(tmp_path: Path):
    """Build a provider backed by an isolated temporary cache."""

    def _factory() -> tuple[ShoonyaHistoricalDataProvider, MagicMock]:
        mock_session = MagicMock(spec=ShoonyaSession)
        provider = ShoonyaHistoricalDataProvider(
            mock_session,
            cache_dir=tmp_path,
        )
        return provider, provider.client

    return _factory


class TestShoonyaHistoricalDataProvider:
    """Tests for the ShoonyaHistoricalDataProvider."""

    def test_supported_timeframes(self, make_provider) -> None:
        """Test that only canonical source timeframes are exposed."""
        provider, _ = make_provider()

        timeframes = provider.supported_timeframes()
        assert timeframes == [
            Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            Timeframe(value=1, unit=TimeframeUnit.DAY),
        ]

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
        assert candles[0].open == Decimal("255.00")
        assert candles[0].high == Decimal("255.65")
        assert candles[0].low == Decimal("254.65")
        assert candles[0].close == Decimal("255.65")
        assert candles[0].volume == Decimal(146)
        client.get_raw_candles.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_candles_preserves_bar_time(self, make_provider) -> None:
        """Test that the vendor bar time reaches the returned candle."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        candles = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )

        assert candles[0].timestamp.isoformat() == "2022-12-07T09:15:00+05:30"
        assert candles[1].timestamp.isoformat() == "2022-12-07T09:16:00+05:30"

    @pytest.mark.asyncio
    async def test_unsupported_timeframe_raises(self, make_provider) -> None:
        """Test that a non-derivable timeframe is rejected before any API call."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        with pytest.raises(TimeframeNotSupportedError):
            await provider.get_candles(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=30, unit=TimeframeUnit.SECOND),
                from_date=FROM_DATE,
                to_date=TO_DATE,
            )

        client.get_raw_candles.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inverted_range_raises(self, make_provider) -> None:
        """Test that an inverted range is rejected before any API call."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        with pytest.raises(ProviderError, match="from_date must be before to_date"):
            await provider.get_candles(
                symbol="NSE:INFY",
                timeframe=TIMEFRAME,
                from_date=TO_DATE,
                to_date=FROM_DATE,
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
        client.get_raw_candles = AsyncMock(return_value="not a list")

        with pytest.raises(ProviderError, match="Normalization failed"):
            await provider.get_candles(
                symbol="NSE:INFY",
                timeframe=TIMEFRAME,
                from_date=FROM_DATE,
                to_date=TO_DATE,
            )

    @pytest.mark.asyncio
    async def test_derived_timeframe_fetches_1m_and_resamples(self, make_provider) -> None:
        """Test that a derived timeframe (e.g., 45m) fetches 1m and resamples."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        target = Timeframe(value=45, unit=TimeframeUnit.MINUTE)
        candles = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=target,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )

        # 1m source was fetched from vendor
        client.get_raw_candles.assert_awaited_once()
        # Resampled to 45m: two 1m candles collapse into one 45m candle
        assert len(candles) == 1
        assert candles[0].timeframe == target
        assert candles[0].open == Decimal("255.00")
        assert candles[0].high == Decimal("256.00")
        assert candles[0].low == Decimal("254.65")
        assert candles[0].close == Decimal("255.90")
        assert candles[0].volume == Decimal(346)

    @pytest.mark.asyncio
    async def test_canonical_timeframe_fetches_directly(self, make_provider) -> None:
        """Test that a canonical timeframe (1m) fetches directly without resampling."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        candles = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )

        assert len(candles) == 2
        client.get_raw_candles.assert_awaited_once()
        # No resampling: bar times preserved exactly
        assert candles[0].timestamp.isoformat() == "2022-12-07T09:15:00+05:30"
        assert candles[1].timestamp.isoformat() == "2022-12-07T09:16:00+05:30"


class TestShoonyaHistoricalDataProviderCaching:
    """Tests for cache-aside behaviour inside the provider."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api_call(self, make_provider) -> None:
        """Test that a cache hit avoids the vendor API entirely."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        first = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )
        assert len(first) == 2
        assert client.get_raw_candles.await_count == 1

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
    async def test_cached_candles_keep_their_bar_time(self, make_provider) -> None:
        """Test that a cached candle carries the same bar time as a fresh one."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        first = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )
        second = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )
        assert second[0].timestamp == first[0].timestamp
        assert second[1].timestamp == first[1].timestamp
