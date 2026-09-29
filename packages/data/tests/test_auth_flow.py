"""Integration tests for on-demand authentication flow."""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile

import pytest

from quantrex_data.providers.dhan_provider import DhanDataProvider
from quantrex_data.providers.zerodha_provider import ZerodhaDataProvider
from quantrex_data.exceptions import DataNotAvailableError
from quantrex_data.operations import ArrowCache


class TestDhanAuthFlow:
    """Tests for Dhan provider authentication flow."""

    def test_cache_hit_no_auth(self):
        """Cache hit should return data without triggering authentication."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            data = [
                {"datetime": "2026-01-15 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            ]
            start = datetime(2026, 1, 15)
            end = datetime(2026, 1, 15)
            cache.save_partition_sync("dhan", "RELIANCE", "1minute", start, end, data)

            # Create provider with cache
            provider = DhanDataProvider(
                access_token="test_token",
                client_id="test_client",
                symbol="RELIANCE",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date="2026-01-15",
                to_date="2026-01-15",
                timeframe="1minute",
            )
            # Inject our test cache
            provider._cache = cache

            # Mock _fetch_from_api to track if it's called
            with patch.object(provider, '_fetch_from_api') as mock_fetch:
                result = provider.fetch(timeframe="1minute", from_date="2026-01-15", to_date="2026-01-15")
                mock_fetch.assert_not_called()

            assert result is not None
            assert "timestamp" in result

    def test_cache_miss_triggers_auth(self):
        """Cache miss should trigger authentication and API fetch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))

            provider = DhanDataProvider(
                access_token="test_token",
                client_id="test_client",
                symbol="RELIANCE",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date="2026-01-15",
                to_date="2026-01-15",
                timeframe="1minute",
            )
            provider._cache = cache

            # Mock _fetch_from_api to return data
            mock_response = {
                "timestamp": [1705292100],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
                "volume": [1000],
            }
            with patch.object(provider, '_fetch_from_api', return_value=mock_response) as mock_fetch:
                result = provider.fetch(timeframe="1minute", from_date="2026-01-15", to_date="2026-01-15")
                mock_fetch.assert_called_once()

            assert result is not None
            assert result["timestamp"] == [1705292100]

    def test_keyboard_interrupt_during_auth_raises_data_not_available(self):
        """KeyboardInterrupt during auth should raise DataNotAvailableError with cached periods."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            # Add some cached data
            data = [
                {"datetime": "2026-01-15 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            ]
            start = datetime(2026, 1, 15)
            end = datetime(2026, 1, 15)
            cache.save_partition_sync("dhan", "RELIANCE", "1minute", start, end, data)

            provider = DhanDataProvider(
                access_token="test_token",
                client_id="test_client",
                symbol="RELIANCE",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date="2026-02-15",  # Different date - cache miss
                to_date="2026-02-15",
                timeframe="1minute",
            )
            provider._cache = cache

            # Mock _fetch_from_api to raise KeyboardInterrupt
            with patch.object(provider, '_fetch_from_api', side_effect=KeyboardInterrupt()):
                with pytest.raises(DataNotAvailableError) as exc_info:
                    provider.fetch(timeframe="1minute", from_date="2026-02-15", to_date="2026-02-15")

            assert exc_info.value.provider == "dhan"
            assert exc_info.value.symbol == "RELIANCE"
            assert exc_info.value.timeframe == "1minute"
            assert len(exc_info.value.cached_periods) == 1
            assert exc_info.value.cached_periods[0] == ("2026-01-15", "2026-01-15")

    def test_get_cached_periods_returns_formatted_dates(self):
        """get_cached_periods should return formatted date strings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            data = [
                {"datetime": "2026-01-15 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            ]
            start = datetime(2026, 1, 15)
            end = datetime(2026, 1, 15)
            cache.save_partition_sync("dhan", "RELIANCE", "1minute", start, end, data)

            provider = DhanDataProvider(
                access_token="test_token",
                client_id="test_client",
                symbol="RELIANCE",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date="2026-01-15",
                to_date="2026-01-15",
                timeframe="1minute",
            )
            provider._cache = cache

            periods = provider.get_cached_periods("1minute")
            assert periods == [("2026-01-15", "2026-01-15")]


class TestZerodhaAuthFlow:
    """Tests for Zerodha provider authentication flow."""

    def test_cache_hit_no_auth(self):
        """Cache hit should return data without triggering authentication."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            data = [
                {"datetime": "2026-01-15 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            ]
            start = datetime(2026, 1, 15)
            end = datetime(2026, 1, 15)
            cache.save_partition_sync("zerodha", "RELIANCE", "minute", start, end, data)

            provider = ZerodhaDataProvider(
                api_key="test_key",
                api_secret="test_secret",
                access_token="test_token",
                symbol="RELIANCE",
                exchange_segment="NSE",
                from_date="2026-01-15",
                to_date="2026-01-15",
                interval="minute",
            )
            provider._cache = cache

            with patch.object(provider, '_fetch_from_api') as mock_fetch:
                result = provider.fetch(interval="minute", from_date="2026-01-15", to_date="2026-01-15")
                mock_fetch.assert_not_called()

            assert result is not None
            assert "candles" in result

    def test_cache_miss_triggers_auth(self):
        """Cache miss should trigger authentication and API fetch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))

            provider = ZerodhaDataProvider(
                api_key="test_key",
                api_secret="test_secret",
                access_token="test_token",
                symbol="RELIANCE",
                exchange_segment="NSE",
                from_date="2026-01-15",
                to_date="2026-01-15",
                interval="minute",
            )
            provider._cache = cache

            mock_response = {
                "candles": [
                    ["2026-01-15T09:15:00+0530", 100.0, 101.0, 99.0, 100.5, 1000],
                ]
            }
            # Mock both authentication and API fetch
            with patch.object(provider, '_ensure_valid_token') as mock_auth, \
                 patch.object(provider, '_fetch_from_api', return_value=mock_response) as mock_fetch:
                result = provider.fetch(interval="minute", from_date="2026-01-15", to_date="2026-01-15")
                mock_auth.assert_called_once()
                mock_fetch.assert_called_once()

            assert result is not None
            assert len(result["candles"]) == 1

    def test_keyboard_interrupt_during_auth_raises_data_not_available(self):
        """KeyboardInterrupt during auth should raise DataNotAvailableError with cached periods."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            data = [
                {"datetime": "2026-01-15 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            ]
            start = datetime(2026, 1, 15)
            end = datetime(2026, 1, 15)
            cache.save_partition_sync("zerodha", "RELIANCE", "minute", start, end, data)

            provider = ZerodhaDataProvider(
                api_key="test_key",
                api_secret="test_secret",
                access_token="test_token",
                symbol="RELIANCE",
                exchange_segment="NSE",
                from_date="2026-02-15",  # Different date - cache miss
                to_date="2026-02-15",
                interval="minute",
            )
            provider._cache = cache

            # Mock authentication to raise KeyboardInterrupt (simulating user cancelling login)
            with patch.object(provider, '_ensure_valid_token', side_effect=KeyboardInterrupt()):
                with pytest.raises(DataNotAvailableError) as exc_info:
                    provider.fetch(interval="minute", from_date="2026-02-15", to_date="2026-02-15")

            assert exc_info.value.provider == "zerodha"
            assert exc_info.value.symbol == "RELIANCE"
            assert exc_info.value.timeframe == "minute"
            assert len(exc_info.value.cached_periods) == 1
            assert exc_info.value.cached_periods[0] == ("2026-01-15", "2026-01-15")

    def test_get_cached_periods_returns_formatted_dates(self):
        """get_cached_periods should return formatted date strings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ArrowCache(Path(tmpdir))
            data = [
                {"datetime": "2026-01-15 09:15:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
            ]
            start = datetime(2026, 1, 15)
            end = datetime(2026, 1, 15)
            cache.save_partition_sync("zerodha", "RELIANCE", "minute", start, end, data)

            provider = ZerodhaDataProvider(
                api_key="test_key",
                api_secret="test_secret",
                access_token="test_token",
                symbol="RELIANCE",
                exchange_segment="NSE",
                from_date="2026-01-15",
                to_date="2026-01-15",
                interval="minute",
            )
            provider._cache = cache

            periods = provider.get_cached_periods("minute")
            assert periods == [("2026-01-15", "2026-01-15")]


class TestDataNotAvailableError:
    """Tests for DataNotAvailableError exception."""

    def test_error_message_includes_cached_periods(self):
        """Error message should include available cached periods."""
        error = DataNotAvailableError(
            "Test message",
            provider="dhan",
            symbol="RELIANCE",
            timeframe="1M",
            cached_periods=[("2026-01-01", "2026-01-31"), ("2026-02-01", "2026-02-28")],
        )
        error_str = str(error)
        assert "2026-01-01 to 2026-01-31" in error_str
        assert "2026-02-01 to 2026-02-28" in error_str
        assert "Please rerun the backtest using one of these date ranges" in error_str

    def test_error_message_without_cached_periods(self):
        """Error message should work without cached periods."""
        error = DataNotAvailableError(
            "Test message",
            provider="dhan",
            symbol="RELIANCE",
            timeframe="1M",
            cached_periods=[],
        )
        error_str = str(error)
        assert "Test message" in error_str
        assert "Available cached periods" not in error_str