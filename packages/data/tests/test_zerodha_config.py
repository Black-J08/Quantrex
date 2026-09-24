"""Tests for ZerodhaProviderConfig validation."""

import pytest
from datetime import date, datetime

# Disable .env loading BEFORE importing config
from quantrex_data.providers.zerodha_provider.client import set_load_dotenv_enabled
set_load_dotenv_enabled(False)

from quantrex_data.providers.zerodha_provider.config import ZerodhaProviderConfig, _parse_redirect_url
from quantrex_data.providers.zerodha_provider.exceptions import (
    ZerodhaInstrumentMasterError,
    ZerodhaSymbolNotFoundError,
)


class TestZerodhaProviderConfig:
    """Tests for ZerodhaProviderConfig validation."""

    def test_valid_config_with_symbol(self, monkeypatch):
        """Config should accept valid parameters with symbol."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

        config = ZerodhaProviderConfig(
            symbol="RELIANCE",
            exchange="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.symbol == "RELIANCE"
        assert config.instrument_token is None

    def test_valid_config_with_instrument_token(self, monkeypatch):
        """Config should accept valid parameters with instrument_token."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

        config = ZerodhaProviderConfig(
            instrument_token="5633",
            exchange="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.instrument_token == "5633"
        assert config.symbol is None

    def test_invalid_both_symbol_and_instrument_token(self, monkeypatch):
        """Config should reject both symbol and instrument_token."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

        with pytest.raises(ValueError, match="Provide either 'symbol' or 'instrument_token'"):
            ZerodhaProviderConfig(
                symbol="RELIANCE",
                instrument_token="5633",
                exchange="NSE",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

    def test_invalid_neither_symbol_nor_instrument_token(self, monkeypatch):
        """Config should reject neither symbol nor instrument_token."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

        with pytest.raises(ValueError, match="Must provide either 'symbol' or 'instrument_token'"):
            ZerodhaProviderConfig(
                exchange="NSE",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

    def test_missing_api_key(self, monkeypatch):
        """Config should reject missing api_key."""
        monkeypatch.delenv("ZERODHA_API_KEY", raising=False)
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

        with pytest.raises(ValueError, match="api_key is required"):
            ZerodhaProviderConfig(
                symbol="RELIANCE",
                exchange="NSE",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

    def test_missing_api_secret(self, monkeypatch):
        """Config should reject missing api_secret."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.delenv("ZERODHA_API_SECRET", raising=False)

        with pytest.raises(ValueError, match="api_secret is required"):
            ZerodhaProviderConfig(
                symbol="RELIANCE",
                exchange="NSE",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

    def test_invalid_exchange(self, monkeypatch):
        """Config should reject invalid exchange."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

        with pytest.raises(ValueError, match="Invalid exchange"):
            ZerodhaProviderConfig(
                symbol="RELIANCE",
                exchange="INVALID",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

    def test_invalid_interval(self, monkeypatch):
        """Config should reject invalid interval."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

        with pytest.raises(ValueError, match="Invalid interval"):
            ZerodhaProviderConfig(
                symbol="RELIANCE",
                exchange="NSE",
                from_date="2024-01-01",
                to_date="2024-01-31",
                interval="invalid",
            )

    def test_missing_chunk_size(self, monkeypatch):
        """Config should reject missing chunk_size_days for interval."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

        with pytest.raises(ValueError, match="chunk_size_days missing required interval"):
            ZerodhaProviderConfig(
                symbol="RELIANCE",
                exchange="NSE",
                from_date="2024-01-01",
                to_date="2024-01-31",
                chunk_size_days={"day": 2000},  # Missing other intervals
            )

    def test_explicit_api_key_wins_over_env(self, monkeypatch):
        """Explicit api_key should override env var."""
        monkeypatch.setenv("ZERODHA_API_KEY", "env_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

        config = ZerodhaProviderConfig(
            api_key="explicit_key",
            symbol="RELIANCE",
            exchange="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.api_key == "explicit_key"

    def test_date_normalization(self, monkeypatch):
        """Config should normalize date/datetime/str inputs."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

        config = ZerodhaProviderConfig(
            symbol="RELIANCE",
            exchange="NSE",
            from_date=date(2024, 1, 1),
            to_date=datetime(2024, 1, 31, 15, 30),
        )
        assert config.from_date == "2024-01-01"
        assert config.to_date == "2024-01-31 15:30:00"

    def test_default_base_url(self, monkeypatch):
        """Config should default to https://api.kite.trade."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

        config = ZerodhaProviderConfig(
            symbol="RELIANCE",
            exchange="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.base_url == "https://api.kite.trade"

    def test_default_token_file(self, monkeypatch):
        """Config should default token file to ~/.quantrex/zerodha/access_token."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

        config = ZerodhaProviderConfig(
            symbol="RELIANCE",
            exchange="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert str(config.token_file).endswith(".quantrex/zerodha/access_token")

    def test_default_cache_dir(self, monkeypatch):
        """Config should default cache dir to ~/.quantrex/cache/zerodha."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

        config = ZerodhaProviderConfig(
            symbol="RELIANCE",
            exchange="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert str(config.cache_dir).endswith(".quantrex/cache/zerodha")


class TestParseRedirectUrl:
    """Tests for _parse_redirect_url function."""

    def test_parse_standard_url(self):
        """Should parse standard HTTP URL with port."""
        host, port, path = _parse_redirect_url("http://localhost:8765/callback")
        assert host == "localhost"
        assert port == 8765
        assert path == "/callback"

    def test_parse_https_url(self):
        """Should parse HTTPS URL with default port."""
        host, port, path = _parse_redirect_url("https://example.com/callback")
        assert host == "example.com"
        assert port == 443
        assert path == "/callback"

    def test_parse_http_url_default_port(self):
        """Should parse HTTP URL with default port."""
        host, port, path = _parse_redirect_url("http://example.com/callback")
        assert host == "example.com"
        assert port == 80
        assert path == "/callback"

    def test_parse_url_with_custom_path(self):
        """Should parse URL with custom path."""
        host, port, path = _parse_redirect_url("http://localhost:9999/auth/zerodha/callback")
        assert host == "localhost"
        assert port == 9999
        assert path == "/auth/zerodha/callback"

    def test_parse_url_with_ip(self):
        """Should parse URL with IP address."""
        host, port, path = _parse_redirect_url("http://127.0.0.1:61035/callback")
        assert host == "127.0.0.1"
        assert port == 61035
        assert path == "/callback"

    def test_parse_invalid_url_no_scheme(self):
        """Should raise ValueError for URL without scheme."""
        with pytest.raises(ValueError, match="Invalid redirect URL"):
            _parse_redirect_url("localhost:8765/callback")

    def test_parse_invalid_url_no_host(self):
        """Should raise ValueError for URL without host."""
        with pytest.raises(ValueError, match="Invalid redirect URL"):
            _parse_redirect_url("http:///callback")


class TestCallbackConfig:
    """Tests for callback configuration in ZerodhaProviderConfig."""

    def test_default_redirect_url(self, monkeypatch):
        """Config should use default redirect URL."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")
        monkeypatch.setenv("ZERODHA_REDIRECT_URL", "http://localhost:8765/callback")

        config = ZerodhaProviderConfig(
            symbol="RELIANCE",
            exchange="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.redirect_url == "http://localhost:8765/callback"
        assert config.callback_host == "localhost"
        assert config.callback_port == 8765
        assert config.callback_path == "/callback"

    def test_custom_redirect_url_from_env(self, monkeypatch):
        """Config should parse custom redirect URL from env var."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")
        monkeypatch.setenv("ZERODHA_REDIRECT_URL", "http://127.0.0.1:61035/callback")

        config = ZerodhaProviderConfig(
            symbol="RELIANCE",
            exchange="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.redirect_url == "http://127.0.0.1:61035/callback"
        assert config.callback_host == "127.0.0.1"
        assert config.callback_port == 61035
        assert config.callback_path == "/callback"

    def test_custom_redirect_url_with_custom_path(self, monkeypatch):
        """Config should parse custom redirect URL with custom path."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")
        monkeypatch.setenv("ZERODHA_REDIRECT_URL", "http://localhost:9999/auth/zerodha/callback")

        config = ZerodhaProviderConfig(
            symbol="RELIANCE",
            exchange="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.redirect_url == "http://localhost:9999/auth/zerodha/callback"
        assert config.callback_host == "localhost"
        assert config.callback_port == 9999
        assert config.callback_path == "/auth/zerodha/callback"

    def test_invalid_redirect_url_raises(self, monkeypatch):
        """Config should raise ValueError for invalid redirect URL."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")
        monkeypatch.setenv("ZERODHA_REDIRECT_URL", "invalid-url")

        with pytest.raises(ValueError, match="Invalid ZERODHA_REDIRECT_URL"):
            ZerodhaProviderConfig(
                symbol="RELIANCE",
                exchange="NSE",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

    def test_callback_timeout_from_env(self, monkeypatch):
        """Config should load callback timeout from env var."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")
        monkeypatch.setenv("ZERODHA_CALLBACK_TIMEOUT", "300")

        config = ZerodhaProviderConfig(
            symbol="RELIANCE",
            exchange="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        assert config.callback_timeout == 300.0

    def test_invalid_callback_timeout_raises(self, monkeypatch):
        """Config should raise ValueError for invalid callback timeout."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")
        monkeypatch.setenv("ZERODHA_CALLBACK_TIMEOUT", "invalid")

        with pytest.raises(ValueError, match="ZERODHA_CALLBACK_TIMEOUT must be a number"):
            ZerodhaProviderConfig(
                symbol="RELIANCE",
                exchange="NSE",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

    def test_negative_callback_timeout_raises(self, monkeypatch):
        """Config should raise ValueError for negative callback timeout."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")
        monkeypatch.setenv("ZERODHA_CALLBACK_TIMEOUT", "-10")

        with pytest.raises(ValueError, match="callback_timeout must be positive"):
            ZerodhaProviderConfig(
                symbol="RELIANCE",
                exchange="NSE",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )