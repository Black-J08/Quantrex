"""Tests for ZerodhaDataProvider."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import date, datetime

from quantrex_data.providers.zerodha_provider import ZerodhaDataProvider
from quantrex_data.providers.zerodha_provider.config import ZerodhaProviderConfig
from quantrex_data.providers.zerodha_provider.exceptions import (
    ZerodhaAuthenticationError,
    ZerodhaRateLimitError,
    ZerodhaDataNotFoundError,
    ZerodhaInvalidParameterError,
    ZerodhaSymbolNotFoundError,
    ZerodhaInstrumentMasterError,
)
from quantrex_test_support.zerodha import (
    MOCK_INSTRUMENT_MASTER_CSV,
    MOCK_HISTORICAL_RESPONSE_MINUTE,
    MOCK_HISTORICAL_RESPONSE_DAY,
    MOCK_HISTORICAL_RESPONSE_WITH_OI,
    MOCK_AUTH_SUCCESS_RESPONSE,
    MOCK_AUTH_ERROR_RESPONSE,
    MOCK_RATE_LIMIT_ERROR_RESPONSE,
    MOCK_INVALID_PARAM_ERROR_RESPONSE,
    MOCK_EMPTY_DATA_RESPONSE,
    MOCK_USER_PROFILE_RESPONSE,
)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Set required environment variables for all tests."""
    monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
    monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")


class TestZerodhaDataProvider:
    """Tests for ZerodhaDataProvider."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock ZerodhaAPIClient."""
        with patch("quantrex_data.providers.zerodha_provider.provider.ZerodhaAPIClient") as mock:
            client_instance = Mock()
            mock.return_value = client_instance
            yield client_instance

    @pytest.fixture
    def mock_instrument_master(self):
        """Create a mock InstrumentMaster."""
        with patch("quantrex_data.providers.zerodha_provider.provider.InstrumentMaster") as mock:
            master_instance = Mock()
            master_instance.resolve_symbol.return_value = "5633"
            mock.return_value = master_instance
            yield master_instance

    @pytest.fixture
    def mock_auth(self):
        """Create a mock ZerodhaAuth."""
        with patch("quantrex_data.providers.zerodha_provider.provider.ZerodhaAuth") as mock:
            auth_instance = Mock()
            auth_instance.ensure_valid_token.return_value = "test_access_token"
            mock.return_value = auth_instance
            yield auth_instance

    @pytest.fixture
    def mock_cache(self):
        """Create a mock ArrowCache."""
        with patch("quantrex_data.providers.zerodha_provider.provider.ArrowCache") as mock:
            cache_instance = Mock()
            cache_instance.load_partition.return_value = None
            cache_instance.get_last_timestamp.return_value = None
            cache_instance.load_current_partition.return_value = None
            cache_instance.list_available_partitions.return_value = []
            mock.return_value = cache_instance
            yield cache_instance

    def test_provider_init_with_symbol(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Provider should initialize with symbol and resolve to instrument_token lazily."""
        provider = ZerodhaDataProvider(
            symbol="RELIANCE",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        # Symbol resolution is now lazy - happens on first fetch
        assert provider.instrument_token is None
        assert provider._symbol_resolved is False
        
        # Trigger resolution by calling fetch (which calls _ensure_symbol_resolved)
        with patch.object(provider, '_fetch_from_api', return_value={"candles": []}):
            provider.fetch()
        
        # Manually trigger symbol resolution since _fetch_from_api is mocked
        provider._ensure_symbol_resolved()
        
        assert provider.instrument_token == "5633"
        assert provider._symbol_resolved is True
        mock_instrument_master.resolve_symbol.assert_called_once_with("RELIANCE", "NSE")

    def test_provider_init_with_instrument_token(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Provider should initialize with instrument_token directly."""
        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert provider.instrument_token == "5633"
        mock_instrument_master.resolve_symbol.assert_not_called()

    def test_provider_init_with_date_objects(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Provider should accept date and datetime objects."""
        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date=date(2024, 1, 1),
            to_date=datetime(2024, 1, 31, 15, 30),
        )
        assert provider.config.from_date == "2024-01-01"
        assert provider.config.to_date == "2024-01-31 15:30:00"

    def test_fetch_minute_data(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Provider should fetch minute historical data."""
        mock_client.get_historical_data.return_value = Mock(
            get_candles=lambda: MOCK_HISTORICAL_RESPONSE_MINUTE["data"]["candles"]
        )

        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-01",
            interval="minute",
        )
        data = provider.fetch()

        assert "candles" in data
        assert len(data["candles"]) == 5
        assert data["candles"][0][0] == "2024-01-01T09:15:00+0530"
        mock_client.get_historical_data.assert_called_once()

    def test_fetch_day_data(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Provider should fetch daily historical data."""
        mock_client.get_historical_data.return_value = Mock(
            get_candles=lambda: MOCK_HISTORICAL_RESPONSE_DAY["data"]["candles"]
        )

        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-05",
            interval="day",
        )
        data = provider.fetch()

        assert "candles" in data
        assert len(data["candles"]) == 5
        assert data["candles"][0][0] == "2024-01-01T00:00:00+0530"
        mock_client.get_historical_data.assert_called_once()

    def test_fetch_with_oi(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Provider should fetch data with open interest."""
        mock_client.get_historical_data.return_value = Mock(
            get_candles=lambda: MOCK_HISTORICAL_RESPONSE_WITH_OI["data"]["candles"]
        )

        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-01",
            interval="minute",
            oi=True,
        )
        data = provider.fetch()

        assert "candles" in data
        assert len(data["candles"]) == 3
        # Each candle should have 7 elements (with OI)
        assert len(data["candles"][0]) == 7
        assert data["candles"][0][6] == 50000  # OI value

    def test_fetch_chunked_data(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Provider should chunk large date ranges and merge responses."""
        # Create mock responses for multiple chunks
        chunk1_candles = MOCK_HISTORICAL_RESPONSE_DAY["data"]["candles"][:3]
        chunk2_candles = MOCK_HISTORICAL_RESPONSE_DAY["data"]["candles"][3:]

        mock_client.get_historical_data.side_effect = [
            Mock(get_candles=lambda: chunk1_candles),
            Mock(get_candles=lambda: chunk2_candles),
        ]

        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-06-30",  # Large range (~180 days) to trigger chunking (day chunk=500, but we can test with smaller)
            interval="day",
        )
        # Override chunk size to force chunking
        provider._config.chunk_size_days["day"] = 90
        data = provider.fetch()

        assert "candles" in data
        assert len(data["candles"]) == 5
        assert mock_client.get_historical_data.call_count == 2

    def test_fetch_minute_data_uses_minute_chunk_size(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Provider should use minute chunk size (30 days) when fetching minute data,
        even if provider was initialized with default interval='day'.
        
        Regression test for: Zerodha API limits minute data to 60 days per request.
        The bug was that _chunk_date_range used config.interval instead of the
        effective interval being fetched.
        """
        # Create mock responses for 3 chunks (90 days / 30 days per chunk = 3 calls)
        chunk1_candles = MOCK_HISTORICAL_RESPONSE_MINUTE["data"]["candles"]
        chunk2_candles = MOCK_HISTORICAL_RESPONSE_MINUTE["data"]["candles"]
        chunk3_candles = MOCK_HISTORICAL_RESPONSE_MINUTE["data"]["candles"]

        mock_client.get_historical_data.side_effect = [
            Mock(get_candles=lambda: chunk1_candles),
            Mock(get_candles=lambda: chunk2_candles),
            Mock(get_candles=lambda: chunk3_candles),
        ]

        # Provider initialized with default interval="day" (chunk=500 days)
        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-03-31",  # 90 days - should trigger 3 chunks of 30 days each for minute data
            interval="day",  # Default interval is day
        )
        # Fetch minute data explicitly - should use minute chunk size (30 days)
        data = provider.fetch(interval="minute")

        assert "candles" in data
        assert len(data["candles"]) == 15  # 5 candles * 3 chunks
        # Should make 3 calls (90 days / 30 days per chunk for minute data)
        # NOT 1 call (which would happen if it used day chunk size of 500)
        assert mock_client.get_historical_data.call_count == 3
        
        # Verify the intervals passed to client were "minute"
        for call in mock_client.get_historical_data.call_args_list:
            assert call.kwargs["interval"] == "minute"

    def test_fetch_empty_data_raises(self, mock_client, mock_instrument_master, mock_auth):
        """Provider should raise ZerodhaDataNotFoundError for empty data."""
        from quantrex_data.providers.zerodha_provider.exceptions import ZerodhaDataNotFoundError
        mock_client.get_historical_data.side_effect = ZerodhaDataNotFoundError("No historical data returned")

        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        with pytest.raises(ZerodhaDataNotFoundError):
            provider.fetch()

    def test_supported_timeframes(self, mock_client, mock_instrument_master, mock_auth):
        """Provider should return correct supported timeframes."""
        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        timeframes = provider.supported_timeframes()
        assert timeframes == ["1M", "3M", "5M", "10M", "15M", "30M", "1H", "1D"]

    def test_get_origin_time(self, mock_client, mock_instrument_master, mock_auth):
        """Provider should return correct origin time (09:15 for NSE)."""
        from datetime import time
        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert provider.get_origin_time() == time(9, 15)

    def test_timeframe_mapping(self, mock_client, mock_instrument_master, mock_auth):
        """Provider should map Quantrex timeframes to Zerodha intervals correctly."""
        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert provider._map_timeframe_to_zerodha("1M") == "minute"
        assert provider._map_timeframe_to_zerodha("5M") == "5minute"
        assert provider._map_timeframe_to_zerodha("15M") == "15minute"
        assert provider._map_timeframe_to_zerodha("30M") == "30minute"
        assert provider._map_timeframe_to_zerodha("1H") == "60minute"
        assert provider._map_timeframe_to_zerodha("1D") == "day"

    def test_invalid_timeframe_raises(self, mock_client, mock_instrument_master, mock_auth):
        """Provider should raise ValueError for unsupported timeframe."""
        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            provider._map_timeframe_to_zerodha("invalid")

    def test_close_delegates_to_client(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Provider close() should delegate to client.close()."""
        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        provider.close()
        mock_client.close.assert_called_once()

    def test_context_manager(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Provider should work as context manager."""
        with ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        ) as provider:
            assert provider.instrument_token == "5633"


class TestZerodhaDataProviderCacheBehavior:
    """Tests for cache-first behavior and gap fetching."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock ZerodhaAPIClient."""
        with patch("quantrex_data.providers.zerodha_provider.provider.ZerodhaAPIClient") as mock:
            client_instance = Mock()
            mock.return_value = client_instance
            yield client_instance

    @pytest.fixture
    def mock_instrument_master(self):
        """Create a mock InstrumentMaster."""
        with patch("quantrex_data.providers.zerodha_provider.provider.InstrumentMaster") as mock:
            master_instance = Mock()
            master_instance.resolve_symbol.return_value = "5633"
            mock.return_value = master_instance
            yield master_instance

    @pytest.fixture
    def mock_auth(self):
        """Create a mock ZerodhaAuth."""
        with patch("quantrex_data.providers.zerodha_provider.provider.ZerodhaAuth") as mock:
            auth_instance = Mock()
            auth_instance.ensure_valid_token.return_value = "test_access_token"
            mock.return_value = auth_instance
            yield auth_instance

    @pytest.fixture
    def mock_cache(self):
        """Create a mock ArrowCache."""
        with patch("quantrex_data.providers.zerodha_provider.provider.ArrowCache") as mock:
            cache_instance = Mock()
            cache_instance.load_partition.return_value = None
            cache_instance.get_last_timestamp.return_value = None
            cache_instance.load_current_partition.return_value = None
            cache_instance.list_available_partitions.return_value = []
            mock.return_value = cache_instance
            yield cache_instance

    def test_fetch_uses_cached_data_when_available(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Provider should return cached data without API call when exact partition exists."""
        from datetime import datetime
        
        # Setup cached data
        cached_rows = [
            {"datetime": "2024-01-01 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            {"datetime": "2024-01-01 09:16:00", "open": 100.5, "high": 101.5, "low": 100.0, "close": 101.0, "volume": 1500},
        ]
        mock_cache.load_partition.return_value = cached_rows
        
        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-01",
            interval="minute",
        )
        data = provider.fetch()
        
        assert "candles" in data
        assert len(data["candles"]) == 2
        # Should NOT call API when cache hit
        mock_client.get_historical_data.assert_not_called()
        # Should NOT refresh instrument master when cache hit
        mock_instrument_master.refresh.assert_not_called()

    def test_fetch_uses_cached_data_without_symbol_resolution(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Provider should return cached data directly without symbol resolution or API call."""
        from datetime import datetime
        
        # Setup cached data
        cached_rows = [
            {"datetime": "2024-01-01 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
        ]
        mock_cache.load_partition.return_value = cached_rows
        
        provider = ZerodhaDataProvider(
            symbol="RELIANCE",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-01",
            interval="minute",
        )
        data = provider.fetch()
        
        assert "candles" in data
        # Cache hit returns data directly - no symbol resolution needed
        mock_instrument_master.resolve_symbol.assert_not_called()
        # Should NOT refresh instrument master when cache hit
        mock_instrument_master.refresh.assert_not_called()
        # Should NOT call API when cache hit
        mock_client.get_historical_data.assert_not_called()

    def test_fetch_only_gaps_when_partial_cached_data(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Provider should fetch only missing gap partitions when partial cached data exists."""
        from datetime import datetime
        
        # Setup: cached partition for Jan 1-15, request Jan 1-31
        cached_rows = [
            {"datetime": "2024-01-01 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
        ]
        
        # Mock load_partition to return cached data only for the cached partition
        def mock_load_partition(provider, symbol, timeframe, start, end):
            if start == datetime(2024, 1, 1) and end == datetime(2024, 1, 15):
                return cached_rows
            return None
        
        mock_cache.load_partition.side_effect = mock_load_partition
        mock_cache.list_available_partitions.return_value = [
            (datetime(2024, 1, 1), datetime(2024, 1, 15)),
        ]
        
        # Mock API response for gap (Jan 16-31)
        gap_candles = [
            ["2024-01-16T09:15:00+0530", 102.0, 103.0, 101.0, 102.5, 2000],
            ["2024-01-17T09:15:00+0530", 102.5, 103.5, 102.0, 103.0, 2500],
        ]
        mock_client.get_historical_data.return_value = Mock(
            get_candles=lambda: gap_candles
        )
        
        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
            interval="minute",
        )
        data = provider.fetch()
        
        assert "candles" in data
        # Should have cached + gap data (1 + 2 = 3 candles)
        assert len(data["candles"]) == 3
        # Should call API only for gap
        assert mock_client.get_historical_data.call_count == 1
        # Should refresh instrument master once before gap fetch
        mock_instrument_master.refresh.assert_called_once()
        # Should save gap partition to cache
        mock_cache.save_partition.assert_called()

    def test_instrument_master_refreshed_once_per_session(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Instrument master should be refreshed only once per provider session."""
        from datetime import datetime
        
        # Setup: no cached data, full fetch needed
        mock_cache.list_available_partitions.return_value = []
        
        # Mock API response
        api_candles = [
            ["2024-01-01T09:15:00+0530", 100.0, 101.0, 99.0, 100.5, 1000],
            ["2024-01-02T09:15:00+0530", 100.5, 101.5, 100.0, 101.0, 1500],
        ]
        mock_client.get_historical_data.return_value = Mock(
            get_candles=lambda: api_candles
        )
        
        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-02",
            interval="minute",
        )
        
        # First fetch
        data1 = provider.fetch()
        assert len(data1["candles"]) == 2
        
        # Second fetch (same provider instance)
        data2 = provider.fetch()
        assert len(data2["candles"]) == 2
        
        # Instrument master should be refreshed only ONCE
        assert mock_instrument_master.refresh.call_count == 1
        # Auth is called multiple times (once per fetch + once per chunk in _fetch_from_api)
        # The key assertion is that instrument master refresh is only once
        assert mock_instrument_master.refresh.call_count == 1

    def test_auth_called_before_instrument_master_refresh(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Authentication should be validated before instrument master refresh."""
        from datetime import datetime
        
        mock_cache.list_available_partitions.return_value = []
        
        api_candles = [
            ["2024-01-01T09:15:00+0530", 100.0, 101.0, 99.0, 100.5, 1000],
        ]
        mock_client.get_historical_data.return_value = Mock(
            get_candles=lambda: api_candles
        )
        
        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-01",
            interval="minute",
        )
        
        # Track call order using side_effect with list
        call_order = []
        
        def track_auth(*args, **kwargs):
            call_order.append("auth")
            return "test_access_token"
        
        def track_refresh(*args, **kwargs):
            call_order.append("refresh")
        
        mock_auth.ensure_valid_token.side_effect = track_auth
        mock_instrument_master.refresh.side_effect = track_refresh
        
        provider.fetch()
        
        # First auth call should be before first refresh call
        auth_index = call_order.index("auth")
        refresh_index = call_order.index("refresh")
        assert auth_index < refresh_index, "Auth should be called before refresh"

    def test_gap_fetch_handles_empty_api_response(self, mock_client, mock_instrument_master, mock_auth, mock_cache):
        """Provider should handle empty API response for gap gracefully."""
        from datetime import datetime
        
        cached_rows = [
            {"datetime": "2024-01-01 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
        ]
        mock_cache.load_partition.return_value = cached_rows
        mock_cache.list_available_partitions.return_value = [
            (datetime(2024, 1, 1), datetime(2024, 1, 15)),
        ]
        
        # Mock empty API response for gap
        mock_client.get_historical_data.return_value = Mock(
            get_candles=lambda: []
        )
        
        provider = ZerodhaDataProvider(
            instrument_token="5633",
            exchange_segment="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
            interval="minute",
        )
        data = provider.fetch()
        
        # Should return only cached data when gap fetch returns empty
        assert "candles" in data
        assert len(data["candles"]) == 1
        # Should still save empty gap partition (or not save)
        # The important thing is it doesn't crash