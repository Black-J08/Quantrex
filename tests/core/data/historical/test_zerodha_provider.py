"""Tests for the Zerodha historical data provider (data layer)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantrex.core.broker.zerodha.session.session import ZerodhaSession
from quantrex.core.data.exceptions.exceptions import (
    ProviderError,
    SymbolResolutionError,
    TimeframeNotSupportedError,
)
from quantrex.core.data.historical.zerodha_provider import ZerodhaHistoricalDataProvider
from quantrex.core.exceptions.exceptions import (
    AmbiguousSymbolError,
    SymbolNotFoundError,
)
from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit

RAW_RESPONSE = {
    "status": "success",
    "data": {
        "candles": [
            ["2024-01-15T09:15:00+05:30", 1500.0, 1510.0, 1495.0, 1505.0, 100000],
            ["2024-01-15T09:16:00+05:30", 1505.0, 1515.0, 1500.0, 1510.0, 80000],
        ],
    },
}

# The vendor reports bar times in IST; the request window is given as the
# matching instants so that the mocked bars fall inside the requested range.
# The window is half-open, so it ends after the last mocked bar.
FROM_DATE = datetime(2024, 1, 15, 3, 45, tzinfo=UTC)
TO_DATE = datetime(2024, 1, 15, 3, 47, tzinfo=UTC)
TIMEFRAME = Timeframe(value=1, unit=TimeframeUnit.MINUTE)


@pytest.fixture
def make_provider(tmp_path: Path):
    """Build a provider backed by an isolated temporary cache."""

    def _factory() -> tuple[ZerodhaHistoricalDataProvider, MagicMock]:
        mock_session = MagicMock(spec=ZerodhaSession)
        provider = ZerodhaHistoricalDataProvider(
            mock_session,
            cache_dir=tmp_path,
        )
        return provider, provider.client

    return _factory


class TestZerodhaHistoricalDataProvider:
    """Tests for the ZerodhaHistoricalDataProvider."""

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
    async def test_get_candles_preserves_bar_time(self, make_provider) -> None:
        """Test that the vendor bar time reaches the returned candle.

        Regression test: the normalizer dropped the vendor timestamp, so
        every bar was stamped with the time it was fetched.
        """
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        candles = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )

        assert candles[0].timestamp.isoformat() == "2024-01-15T09:15:00+05:30"
        assert candles[1].timestamp.isoformat() == "2024-01-15T09:16:00+05:30"

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
        """Test that a cached candle carries the same bar time as a fresh one.

        Regression test: the cache never read the timestamp column it wrote,
        so a cached bar carried the time of the read.
        """
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

        assert first[0].timestamp == second[0].timestamp
        assert second[0].timestamp.isoformat() == "2024-01-15T09:15:00+05:30"

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

    @pytest.mark.asyncio
    async def test_continuous_and_plain_use_separate_entries(self, make_provider) -> None:
        """Test that a continuous request is not served a plain cached entry."""
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
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
            continuous=True,
        )

        assert client.get_raw_candles.await_count == 2

    @pytest.mark.asyncio
    async def test_overlapping_request_fetches_only_the_gap(self, make_provider) -> None:
        """Test that an overlapping request downloads only what is missing.

        The first call covers 03:45-04:00; the second asks for a wider range
        and must fetch only the two uncovered stretches, not the whole range.
        """
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=datetime(2024, 1, 15, 4, 0, tzinfo=UTC),
        )
        assert client.get_raw_candles.await_count == 1

        await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=datetime(2024, 1, 15, 2, 0, tzinfo=UTC),
            to_date=datetime(2024, 1, 15, 6, 0, tzinfo=UTC),
        )

        # Two extra requests, one for each uncovered stretch.
        assert client.get_raw_candles.await_count == 3
        second_call = client.get_raw_candles.await_args_list[1]
        third_call = client.get_raw_candles.await_args_list[2]
        assert second_call.kwargs["from_date"] == datetime(2024, 1, 15, 2, 0, tzinfo=UTC)
        assert second_call.kwargs["to_date"] == datetime(2024, 1, 15, 3, 45, tzinfo=UTC)
        assert third_call.kwargs["from_date"] == datetime(2024, 1, 15, 4, 0, tzinfo=UTC)
        assert third_call.kwargs["to_date"] == datetime(2024, 1, 15, 6, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_request_spanning_months_is_split(self, make_provider) -> None:
        """Test that a long range is fetched one month at a time.

        Zerodha caps a request at 60 days for 1-minute candles, so a range
        wider than a month must be split.
        """
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(return_value=RAW_RESPONSE)

        await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=datetime(2024, 1, 15, 9, 15, tzinfo=UTC),
            to_date=datetime(2024, 3, 10, 9, 15, tzinfo=UTC),
        )

        assert client.get_raw_candles.await_count == 3
        requested = [
            (call.kwargs["from_date"], call.kwargs["to_date"])
            for call in client.get_raw_candles.await_args_list
        ]
        assert requested[0][0] == datetime(2024, 1, 15, 9, 15, tzinfo=UTC)
        assert requested[0][1] == datetime(2024, 2, 1, tzinfo=UTC)
        assert requested[1][0] == datetime(2024, 2, 1, tzinfo=UTC)
        assert requested[1][1] == datetime(2024, 3, 1, tzinfo=UTC)
        assert requested[2][0] == datetime(2024, 3, 1, tzinfo=UTC)
        assert requested[2][1] == datetime(2024, 3, 10, 9, 15, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_empty_vendor_response_is_covered(self, make_provider) -> None:
        """Test that a range with no bars is not requested again."""
        provider, client = make_provider()
        client.get_raw_candles = AsyncMock(
            return_value={"status": "success", "data": {"candles": []}}
        )

        first = await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )
        assert first == []

        await provider.get_candles(
            symbol="NSE:INFY",
            timeframe=TIMEFRAME,
            from_date=FROM_DATE,
            to_date=TO_DATE,
        )

        assert client.get_raw_candles.await_count == 1


def test_shared_exceptions_importable_from_neutral_location() -> None:
    """Regression test: SymbolNotFoundError and AmbiguousSymbolError are
    importable from quantrex.core.exceptions.exceptions (neutral shared location),
    not owned by broker or data.

    This preserves broker segregation — neither module owns these exceptions.
    """
    from quantrex.core.exceptions.exceptions import (
        AmbiguousSymbolError,
        SymbolNotFoundError,
    )

    assert SymbolNotFoundError("NSE:UNKNOWN").symbol == "NSE:UNKNOWN"
    assert AmbiguousSymbolError("INFY", []).tradingsymbol == "INFY"
