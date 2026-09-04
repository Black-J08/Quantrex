"""Tests for DhanDataProvider."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import date, datetime

from quantrex_data.providers.dhan_provider import DhanDataProvider
from quantrex_data.providers.dhan_provider.config import DhanProviderConfig
from quantrex_data.providers.dhan_provider.exceptions import (
    DhanAuthenticationError,
    DhanRateLimitError,
    DhanDataNotFoundError,
    DhanInvalidParameterError,
    DhanSymbolNotFoundError,
    DhanInstrumentMasterError,
)
from quantrex_test_support.dhan import (
    MOCK_INSTRUMENT_MASTER_CSV,
    MOCK_DAILY_HISTORICAL_RESPONSE,
    MOCK_INTRADAY_HISTORICAL_RESPONSE,
    MOCK_AUTH_ERROR_RESPONSE,
    MOCK_RATE_LIMIT_ERROR_RESPONSE,
    MOCK_INVALID_PARAM_ERROR_RESPONSE,
    MOCK_EMPTY_DATA_RESPONSE,
)


class TestDhanProviderConfig:
    """Tests for DhanProviderConfig validation."""

    def test_valid_config_with_symbol(self):
        """Config should accept valid parameters with symbol."""
        config = DhanProviderConfig(
            symbol="RELIANCE",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.symbol == "RELIANCE"
        assert config.security_id is None

    def test_valid_config_with_security_id(self):
        """Config should accept valid parameters with security_id."""
        config = DhanProviderConfig(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.security_id == "1333"
        assert config.symbol is None

    def test_invalid_both_symbol_and_security_id(self):
        """Config should reject both symbol and security_id."""
        with pytest.raises(ValueError, match="Provide either 'symbol' or 'security_id'"):
            DhanProviderConfig(
                symbol="RELIANCE",
                security_id="1333",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

    def test_invalid_neither_symbol_nor_security_id(self):
        """Config should reject neither symbol nor security_id."""
        with pytest.raises(ValueError, match="Must provide either 'symbol' or 'security_id'"):
            DhanProviderConfig(
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

    def test_invalid_exchange_segment(self):
        """Config should reject invalid exchange_segment."""
        with pytest.raises(ValueError, match="Invalid exchange_segment"):
            DhanProviderConfig(
                symbol="RELIANCE",
                exchange_segment="INVALID",
                instrument="EQUITY",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

    def test_invalid_instrument(self):
        """Config should reject invalid instrument."""
        with pytest.raises(ValueError, match="Invalid instrument"):
            DhanProviderConfig(
                symbol="RELIANCE",
                exchange_segment="NSE_EQ",
                instrument="INVALID",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

    def test_invalid_timeframe(self):
        """Config should reject invalid timeframe."""
        with pytest.raises(ValueError, match="Invalid timeframe"):
            DhanProviderConfig(
                symbol="RELIANCE",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date="2024-01-01",
                to_date="2024-01-31",
                timeframe="invalid",
            )

    def test_missing_chunk_size(self):
        """Config should reject missing chunk_size_days for timeframe."""
        with pytest.raises(ValueError, match="chunk_size_days missing required timeframe"):
            DhanProviderConfig(
                symbol="RELIANCE",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date="2024-01-01",
                to_date="2024-01-31",
                chunk_size_days={"day": 2000},  # Missing other timeframes
            )

    def test_client_id_explicit(self):
        """Config should accept an explicit client_id."""
        config = DhanProviderConfig(
            security_id="1333",
            client_id="1112625384",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.client_id == "1112625384"

    def test_client_id_from_env(self, monkeypatch):
        """Config should fall back to DHAN_CLIENT_ID env var."""
        monkeypatch.setenv("DHAN_CLIENT_ID", "9999999999")
        config = DhanProviderConfig(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.client_id == "9999999999"

    def test_client_id_extracted_from_jwt(self, monkeypatch):
        """Config should extract client_id from the access-token JWT.

        Reproduces the user's .env scenario: only DHAN_ACCESS_TOKEN is set;
        the framework should pull the dhanClientId claim out of the JWT
        rather than require a second env var.
        """
        # JWT with payload {"dhanClientId": "1112625384"} (base64url, padded).
        import base64
        import json

        payload = base64.urlsafe_b64encode(
            json.dumps({"dhanClientId": "1112625384"}).encode()
        ).decode().rstrip("=")
        token = f"header.{payload}.signature"
        monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)

        config = DhanProviderConfig(
            access_token=token,
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.client_id == "1112625384"

    def test_client_id_explicit_wins_over_env(self, monkeypatch):
        """Explicit client_id should override env var."""
        monkeypatch.setenv("DHAN_CLIENT_ID", "9999999999")
        config = DhanProviderConfig(
            security_id="1333",
            client_id="1112625384",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.client_id == "1112625384"

    def test_default_base_url_uses_v2_prefix(self):
        """The default base_url must include /v2.

        Dhan's CloudFront permanently redirects requests to the legacy base
        (``https://api.dhan.co``) back to ``https://api.dhan.co/v2/`` with a
        301/HTML body. The framework must default to the v2 base so live
        requests work out of the box.
        """
        config = DhanProviderConfig(
            security_id="1333",
            client_id="1112625384",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.base_url == "https://api.dhan.co/v2"

    def test_provider_default_base_url_uses_v2_prefix(self):
        """DhanDataProvider should also default to /v2 (for sandbox overrides)."""
        provider = DhanDataProvider(
            security_id="1333",
            client_id="1112625384",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert provider.config.base_url == "https://api.dhan.co/v2"
        # The httpx client's base URL should also reflect the /v2 suffix
        # (httpx normalizes URLs with a trailing slash).
        assert str(provider._client._client.base_url).rstrip("/") == "https://api.dhan.co/v2"


class TestDhanDataProvider:
    """Tests for DhanDataProvider."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock DhanAPIClient."""
        with patch("quantrex_data.providers.dhan_provider.provider.DhanAPIClient") as mock:
            client_instance = Mock()
            mock.return_value = client_instance
            yield client_instance

    @pytest.fixture
    def mock_instrument_master(self):
        """Create a mock InstrumentMaster."""
        with patch("quantrex_data.providers.dhan_provider.provider.InstrumentMaster") as mock:
            master_instance = Mock()
            master_instance.resolve_symbol.return_value = "1333"
            mock.return_value = master_instance
            yield master_instance

    def test_provider_init_with_symbol(self, mock_client, mock_instrument_master):
        """Provider should initialize with symbol and resolve to security_id."""
        provider = DhanDataProvider(
            symbol="RELIANCE",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert provider.security_id == "1333"
        mock_instrument_master.resolve_symbol.assert_called_once_with("RELIANCE", "NSE_EQ")

    def test_provider_init_with_security_id(self, mock_client, mock_instrument_master):
        """Provider should initialize with security_id directly."""
        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert provider.security_id == "1333"
        mock_instrument_master.resolve_symbol.assert_not_called()

    def test_provider_init_with_date_objects(self, mock_client, mock_instrument_master):
        """Provider should accept date and datetime objects."""
        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date=date(2024, 1, 1),
            to_date=datetime(2024, 1, 31, 15, 30),
        )
        assert provider.config.from_date == "2024-01-01"
        assert provider.config.to_date == "2024-01-31 15:30:00"

    def test_fetch_daily_data(self, mock_client, mock_instrument_master):
        """Provider should fetch daily historical data."""
        mock_client.get_daily_historical.return_value = Mock(
            model_dump=lambda **kwargs: MOCK_DAILY_HISTORICAL_RESPONSE
        )

        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-05",
            timeframe="day",
        )
        data = provider.fetch()

        assert "timestamp" in data
        assert len(data["timestamp"]) == 5
        assert data["open"] == MOCK_DAILY_HISTORICAL_RESPONSE["open"]
        mock_client.get_daily_historical.assert_called_once()

    def test_fetch_intraday_data(self, mock_client, mock_instrument_master):
        """Provider should fetch intraday historical data."""
        mock_client.get_intraday_historical.return_value = Mock(
            model_dump=lambda **kwargs: MOCK_INTRADAY_HISTORICAL_RESPONSE
        )

        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01 09:15:00",
            to_date="2024-01-01 09:20:00",
            timeframe="1minute",
        )
        data = provider.fetch()

        assert "timestamp" in data
        assert len(data["timestamp"]) == 5
        mock_client.get_intraday_historical.assert_called_once()

    def test_fetch_with_chunking(self, mock_client, mock_instrument_master):
        """Provider should chunk large date ranges."""
        # Create proper mock response objects with attributes
        from quantrex_data.providers.dhan_provider.models import HistoricalDataResponse

        chunk1 = HistoricalDataResponse(
            open=[2500.0, 2510.0, 2520.0],
            high=[2520.0, 2525.0, 2535.0],
            low=[2490.0, 2505.0, 2510.0],
            close=[2510.0, 2520.0, 2515.0],
            volume=[100000, 150000, 120000],
            timestamp=[1704067200, 1704153600, 1704240000],
            open_interest=[50000, 55000, 52000],
        )
        chunk2 = HistoricalDataResponse(
            open=[2515.0, 2530.0, 2525.0],
            high=[2525.0, 2540.0, 2535.0],
            low=[2500.0, 2520.0, 2515.0],
            close=[2530.0, 2535.0, 2530.0],
            volume=[180000, 200000, 190000],
            timestamp=[1704326400, 1704412800, 1704499200],
            open_interest=[58000, 60000, 59000],
        )
        chunk3 = HistoricalDataResponse(
            open=[2535.0],
            high=[2545.0],
            low=[2525.0],
            close=[2540.0],
            volume=[210000],
            timestamp=[1704585600],
            open_interest=[61000],
        )
        mock_client.get_daily_historical.side_effect = [chunk1, chunk2, chunk3]

        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-10",  # Large range to trigger chunking
            timeframe="day",
            chunk_size_days={"day": 3},  # Small chunk size for testing
        )
        data = provider.fetch()

        assert len(data["timestamp"]) == 7  # 3 + 3 + 1 = 7 candles
        assert mock_client.get_daily_historical.call_count == 3

    def test_fetch_symbol_resolution_error(self, mock_client, mock_instrument_master):
        """Provider should raise DhanSymbolNotFoundError for unknown symbol."""
        mock_instrument_master.resolve_symbol.side_effect = DhanSymbolNotFoundError(
            symbol="UNKNOWN", exchange_segment="NSE_EQ"
        )

        with pytest.raises(DhanSymbolNotFoundError):
            DhanDataProvider(
                symbol="UNKNOWN",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

    def test_fetch_auth_error(self, mock_client, mock_instrument_master):
        """Provider should propagate authentication errors."""
        mock_client.get_daily_historical.side_effect = DhanAuthenticationError("Invalid token")

        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        with pytest.raises(DhanAuthenticationError):
            provider.fetch()

    def test_fetch_rate_limit_error(self, mock_client, mock_instrument_master):
        """Provider should propagate rate limit errors."""
        mock_client.get_daily_historical.side_effect = DhanRateLimitError("Rate limited")

        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        with pytest.raises(DhanRateLimitError):
            provider.fetch()

    def test_fetch_data_not_found(self, mock_client, mock_instrument_master):
        """Provider should raise DhanDataNotFoundError for empty response."""
        mock_client.get_daily_historical.side_effect = DhanDataNotFoundError("No data")

        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        with pytest.raises(DhanDataNotFoundError):
            provider.fetch()

    def test_fetch_invalid_parameter_error(self, mock_client, mock_instrument_master):
        """Provider should propagate invalid parameter errors."""
        mock_client.get_daily_historical.side_effect = DhanInvalidParameterError(
            "Invalid SecurityId", error_code=813
        )

        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        with pytest.raises(DhanInvalidParameterError) as exc_info:
            provider.fetch()
        assert exc_info.value.error_code == 813

    def test_close_delegates_to_client(self, mock_client, mock_instrument_master):
        """Provider close() should delegate to client.close()."""
        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        provider.close()
        mock_client.close.assert_called_once()

    def test_context_manager(self, mock_client, mock_instrument_master):
        """Provider should work as context manager."""
        with DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        ) as provider:
            assert provider.security_id == "1333"
        mock_client.close.assert_called_once()

    def test_credential_loading_from_env(self):
        """Provider should load access token from environment when not provided."""
        with patch.dict("os.environ", {"DHAN_ACCESS_TOKEN": "test_token_from_env"}):
            with patch("quantrex_data.providers.dhan_provider.provider.DhanAPIClient") as mock_client_class, \
                 patch("quantrex_data.providers.dhan_provider.provider.InstrumentMaster"):
                mock_client = Mock()
                mock_client_class.return_value = mock_client
                mock_client.get_daily_historical.return_value = Mock(
                    model_dump=lambda **kwargs: MOCK_DAILY_HISTORICAL_RESPONSE
                )

                provider = DhanDataProvider(
                    security_id="1333",
                    exchange_segment="NSE_EQ",
                    instrument="EQUITY",
                    from_date="2024-01-01",
                    to_date="2024-01-31",
                )
                # Verify provider was created successfully with env token
                # The actual token loading happens in DhanAPIClient._get_access_token()
                # which is called during fetch()
                assert provider is not None
                assert provider._config.access_token is None  # Config stores None, client loads from env

    def test_credential_loading_missing_raises(self):
        """Provider should raise DhanAuthenticationError when no token available."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("quantrex_data.providers.dhan_provider.provider.DhanAPIClient") as mock_client_class, \
                 patch("quantrex_data.providers.dhan_provider.provider.InstrumentMaster"):
                mock_client = Mock()
                mock_client_class.return_value = mock_client
                mock_client.get_daily_historical.side_effect = DhanAuthenticationError("No token")

                provider = DhanDataProvider(
                    security_id="1333",
                    exchange_segment="NSE_EQ",
                    instrument="EQUITY",
                    from_date="2024-01-01",
                    to_date="2024-01-31",
                )
                with pytest.raises(DhanAuthenticationError):
                    provider.fetch()  # Error raised on fetch, not init

    def test_date_normalization_daily(self, mock_client, mock_instrument_master):
        """Provider should normalize dates for daily API (YYYY-MM-DD)."""
        mock_client.get_daily_historical.return_value = Mock(
            model_dump=lambda **kwargs: MOCK_DAILY_HISTORICAL_RESPONSE
        )

        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01 10:30:00",  # Has time component
            to_date="2024-01-31 15:30:00",    # Has time component
            timeframe="day",
        )
        provider.fetch()

        # Check that the request was made with date-only format
        call_args = mock_client.get_daily_historical.call_args[0][0]
        assert call_args.from_date == "2024-01-01"
        assert call_args.to_date == "2024-01-31"

    def test_date_normalization_intraday(self, mock_client, mock_instrument_master):
        """Provider should normalize dates for intraday API (YYYY-MM-DD HH:MM:SS)."""
        mock_client.get_intraday_historical.return_value = Mock(
            model_dump=lambda **kwargs: MOCK_INTRADAY_HISTORICAL_RESPONSE
        )

        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date=date(2024, 1, 1),
            to_date=date(2024, 1, 1),
            timeframe="1minute",
        )
        provider.fetch()

        # Check that the request was made with time component for intraday
        call_args = mock_client.get_intraday_historical.call_args[0][0]
        assert " " in call_args.from_date
        assert " " in call_args.to_date

    def test_custom_chunk_sizes(self, mock_client, mock_instrument_master):
        """Provider should use custom chunk sizes when provided.

        With ``chunk_size_days["day"]=1`` and a 2-day range
        (``2024-01-01`` to ``2024-01-03``), the chunker must NOT emit
        a same-day request (Dhan rejects ``fromDate == toDate`` with
        ``errorCode DH-907``). The single-day residue after the first
        stride is absorbed into the first chunk, producing a single
        request covering the full range.
        """
        from quantrex_data.providers.dhan_provider.models import HistoricalDataResponse

        chunk1 = HistoricalDataResponse(
            open=[2500.0], high=[2520.0], low=[2490.0],
            close=[2510.0], volume=[100000], timestamp=[1704067200],
            open_interest=[50000],
        )
        mock_client.get_daily_historical.side_effect = [chunk1]

        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-03",
            timeframe="day",
            chunk_size_days={"day": 1, "1minute": 30, "5minute": 60, "15minute": 180, "30minute": 360, "60minute": 720},
        )
        provider.fetch()

        # One request covers the whole range; the single-day residue
        # was absorbed instead of being emitted as a same-day chunk.
        assert mock_client.get_daily_historical.call_count == 1
        request = mock_client.get_daily_historical.call_args[0][0]
        assert request.from_date == "2024-01-01"
        assert request.to_date == "2024-01-03"


class TestDhanDataProviderIntegration:
    """Integration-style tests for DhanDataProvider."""

    def test_provider_implements_data_provider_protocol(self):
        """DhanDataProvider should satisfy DataProvider protocol."""
        from quantrex_core.protocols import DataProvider

        # Check protocol compliance via duck typing
        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert hasattr(provider, "fetch")
        assert callable(provider.fetch)
        assert hasattr(provider, "close")
        assert callable(provider.close)

        # Should be usable where DataProvider is expected
        provider_instance: DataProvider = provider
        assert provider_instance is not None


class TestDhanDailyChunkingRegression:
    """Regression: default daily chunk size must respect Dhan's 90-day per-request limit.

    Original defect: the default ``chunk_size_days["day"]`` was 2000, which
    allowed a 365-day request (``2023-02-01`` to ``2024-02-01``) to be sent
    in a single HTTP call. Dhan's historical data API enforces a hard
    limit of 90 days per request and rejects longer ranges with
    ``errorCode`` 812/813/814 ("Invalid request parameters"). The
    framework now defaults to 90 days and chunks longer ranges into
    compliant sub-requests, merging the responses transparently.

    These tests pin:
      1. The default daily chunk size is exactly 90 days.
      2. A 365-day range produces the expected number of sub-requests.
      3. No sub-request exceeds the 90-day limit.
      4. The full range still produces a single merged dataset.
    """

    @pytest.fixture
    def mock_client(self):
        with patch("quantrex_data.providers.dhan_provider.provider.DhanAPIClient") as mock:
            client_instance = Mock()
            mock.return_value = client_instance
            yield client_instance

    @pytest.fixture
    def mock_instrument_master(self):
        with patch("quantrex_data.providers.dhan_provider.provider.InstrumentMaster") as mock:
            master_instance = Mock()
            master_instance.resolve_symbol.return_value = "1333"
            mock.return_value = master_instance
            yield master_instance

    def test_default_daily_chunk_size_is_dhan_limit(self, mock_client, mock_instrument_master):
        """Default daily chunk size must be 89 (stride producing <=90-day inclusive chunks).

        Dhan's API enforces a 90-day hard limit per request. Since the
        chunker uses inclusive end dates, the stride is 89 days so that
        the first chunk spans exactly 90 days inclusive (e.g. 2024-01-01
        through 2024-03-30).
        """
        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert provider.config.chunk_size_days["day"] == 89

    def test_year_long_range_chunks_into_90_day_requests(
        self, mock_client, mock_instrument_master
    ):
        """A 365-day range must be split into <=90-day sub-requests.

        Reproduces the user-reported scenario from
        ``sma_crossover_dhan_strategy.py`` (``2023-02-01`` to ``2024-02-01``).
        With the previous default of 2000 days, this would have been sent
        as a single request and rejected with ``errorCode`` 812/813/814.
        """
        from quantrex_data.providers.dhan_provider.models import HistoricalDataResponse

        # Five chunks of <=90 days each cover Feb 2023 -> Feb 2024.
        # Provide enough side effects to satisfy any reasonable chunking
        # behaviour around the 90-day boundary.
        chunk_response = HistoricalDataResponse(
            open=[2500.0], high=[2520.0], low=[2490.0], close=[2510.0],
            volume=[100000], timestamp=[1704047400], open_interest=[50000],
        )
        mock_client.get_daily_historical.side_effect = [chunk_response] * 6

        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2023-02-01",
            to_date="2024-02-01",
            timeframe="day",
        )
        provider.fetch()

        # No sub-request may exceed 90 days (Dhan's hard limit).
        for call in mock_client.get_daily_historical.call_args_list:
            request = call[0][0]
            from_dt = datetime.strptime(request.from_date, "%Y-%m-%d")
            to_dt = datetime.strptime(request.to_date, "%Y-%m-%d")
            span_days = (to_dt - from_dt).days + 1  # inclusive
            assert span_days <= 90, (
                f"Sub-request spans {span_days} days "
                f"({request.from_date} -> {request.to_date}), exceeding "
                f"Dhan's 90-day per-request limit. This would fail with "
                f"errorCode 812/813/814."
            )

    def test_year_long_range_is_chunked_into_multiple_requests(
        self, mock_client, mock_instrument_master
    ):
        """A 365-day range must produce more than one HTTP request.

        Before the fix (default chunk = 2000 days), a 365-day request
        collapsed into a single HTTP call and was rejected by Dhan.
        """
        from quantrex_data.providers.dhan_provider.models import HistoricalDataResponse

        chunk_response = HistoricalDataResponse(
            open=[2500.0], high=[2520.0], low=[2490.0], close=[2510.0],
            volume=[100000], timestamp=[1704047400], open_interest=[50000],
        )
        # Provide enough side effects for the chunker to consume.
        mock_client.get_daily_historical.side_effect = [chunk_response] * 6

        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2023-02-01",
            to_date="2024-02-01",
            timeframe="day",
        )
        provider.fetch()

        assert mock_client.get_daily_historical.call_count >= 5, (
            f"Expected >=5 chunked requests for a 365-day range, got "
            f"{mock_client.get_daily_historical.call_count}. The chunker "
            f"is not splitting at the 90-day boundary, so the request will "
            f"hit Dhan's per-request limit and fail with errorCode 812/813/814."
        )


class TestDhanDailyChunkingResidueRegression:
    """Regression: chunker must absorb single-day tail residue into the previous chunk.

    Original defect: ``DhanDataProvider._chunk_date_range`` walked the
    range in 89-day strides and incremented ``current_start`` by 1 day
    after each chunk. When the user's range wasn't an exact multiple of
    89 days, the tail left a 1-day chunk whose ``fromDate == toDate``.
    Dhan v2's ``/charts/historical`` endpoint rejects such requests
    with HTTP 400 / ``errorCode: DH-907`` ("System is unable to fetch
    data due to incorrect parameters or no data present"). Verified
    directly against Dhan v2: ``fromDate == toDate`` returns ``DH-907``
    while ``toDate = fromDate + 1 day`` succeeds.

    Reproducer (user-reported): ``examples/rsi_example_strategy.py``
    with ``from_date="2026-01-01"``, ``to_date="2026-06-30"`` produced
    the chunks ``(2026-01-01, 2026-03-31)``, ``(2026-04-01, 2026-06-29)``,
    and the failing ``(2026-06-30, 2026-06-30)``. The fix absorbs the
    single-day residue into the previous chunk so the last chunk is
    ``(2026-04-01, 2026-06-30)``.

    These tests pin:
      1. No chunk has ``to_date == from_date`` (the regression symptom).
      2. The residue tail is absorbed into the previous chunk instead
         of being dropped or emitted as a same-day request.
      3. The merged dataset covers the full requested window.
    """

    @pytest.fixture
    def mock_client(self):
        with patch("quantrex_data.providers.dhan_provider.provider.DhanAPIClient") as mock:
            client_instance = Mock()
            mock.return_value = client_instance
            yield client_instance

    @pytest.fixture
    def mock_instrument_master(self):
        with patch("quantrex_data.providers.dhan_provider.provider.InstrumentMaster") as mock:
            master_instance = Mock()
            master_instance.resolve_symbol.return_value = "1333"
            mock.return_value = master_instance
            yield master_instance

    def test_rsi_range_does_not_emit_same_day_chunk(
        self, mock_client, mock_instrument_master
    ):
        """The user-reported 180-day range must not produce a same-day chunk.

        ``examples/rsi_example_strategy.py`` uses
        ``from_date="2026-01-01"``, ``to_date="2026-06-30"``. Before the
        fix, the chunker produced a final ``(2026-06-30, 2026-06-30)``
        chunk that Dhan rejected with ``errorCode DH-907``.
        """
        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2026-01-01",
            to_date="2026-06-30",
            timeframe="day",
        )
        chunks = provider._chunk_date_range("2026-01-01", "2026-06-30", is_intraday=False)

        assert len(chunks) == 2, (
            f"Expected 2 chunks (residue absorbed into the previous), "
            f"got {len(chunks)}: {chunks}. A trailing single-day chunk "
            f"will be rejected by Dhan with errorCode DH-907."
        )
        assert chunks[-1] == ("2026-04-01", "2026-06-30"), (
            f"Expected the residue to be absorbed into the second chunk "
            f"so its end-date equals the user's requested end-date, got "
            f"{chunks[-1]}."
        )
        for chunk_from, chunk_to in chunks:
            assert chunk_from != chunk_to, (
                f"Chunk {chunk_from} -> {chunk_to} has a zero-day span; "
                f"Dhan rejects such requests with errorCode DH-907."
            )

    def test_no_chunk_ever_has_zero_day_span_for_any_range(
        self, mock_client, mock_instrument_master
    ):
        """For a variety of range lengths, no chunk may have ``from == to``.

        Sweeps ranges of 1..200 days starting from a fixed date and
        asserts the chunker never emits a same-day request.
        """
        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-02",
            timeframe="day",
        )
        for span_days in (1, 2, 30, 88, 89, 90, 91, 120, 178, 179, 180, 181, 365):
            from_d = "2024-01-01"
            to_d = (
                datetime.strptime(from_d, "%Y-%m-%d")
                + __import__("datetime").timedelta(days=span_days)
            ).strftime("%Y-%m-%d")
            chunks = provider._chunk_date_range(from_d, to_d, is_intraday=False)
            for chunk_from, chunk_to in chunks:
                assert chunk_from != chunk_to, (
                    f"Range {from_d} -> {to_d} ({span_days} days) produced "
                    f"a same-day chunk {chunk_from} -> {chunk_to}; Dhan "
                    f"rejects such requests with errorCode DH-907."
                )

    def test_merged_window_covers_full_requested_range(
        self, mock_client, mock_instrument_master
    ):
        """After chunking, the union of chunk windows covers [from, to] end-to-end.

        Guards against a buggy "absorb the residue" implementation that
        drops the last day of the user's window.
        """
        from quantrex_data.providers.dhan_provider.models import HistoricalDataResponse

        chunk_response = HistoricalDataResponse(
            open=[2500.0], high=[2520.0], low=[2490.0], close=[2510.0],
            volume=[100000], timestamp=[1704047400], open_interest=[50000],
        )
        mock_client.get_daily_historical.side_effect = [chunk_response] * 4

        provider = DhanDataProvider(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2026-01-01",
            to_date="2026-06-30",
            timeframe="day",
        )
        chunks = provider._chunk_date_range("2026-01-01", "2026-06-30", is_intraday=False)

        # The first chunk starts at the user's from_date and the last
        # chunk's to_date is the user's to_date; the windows are
        # contiguous (next.from = prev.to + 1 day).
        assert chunks[0][0] == "2026-01-01"
        assert chunks[-1][1] == "2026-06-30"
        for prev, nxt in zip(chunks, chunks[1:]):
            prev_end = datetime.strptime(prev[1], "%Y-%m-%d")
            nxt_start = datetime.strptime(nxt[0], "%Y-%m-%d")
            assert nxt_start == prev_end + __import__("datetime").timedelta(days=1), (
                f"Chunk windows are not contiguous: {prev[1]} -> {nxt[0]}"
            )