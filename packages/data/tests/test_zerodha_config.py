"""Tests for ZerodhaProviderConfig validation."""

import pytest
from datetime import date, datetime

from quantrex_data.providers.zerodha_provider.config import ZerodhaProviderConfig
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