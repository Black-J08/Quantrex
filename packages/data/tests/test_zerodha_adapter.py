"""Tests for ZerodhaDataAdapter."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from quantrex_data.adapters.zerodha_adapter import ZerodhaDataAdapter
from quantrex_data.providers.zerodha_provider import ZerodhaDataProvider
from quantrex_core.protocols import DataAdapter
from quantrex_test_support.zerodha import (
    MOCK_HISTORICAL_RESPONSE_MINUTE,
    MOCK_HISTORICAL_RESPONSE_DAY,
    MOCK_HISTORICAL_RESPONSE_WITH_OI,
)


class TestZerodhaDataAdapter:
    """Tests for ZerodhaDataAdapter."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock ZerodhaDataProvider."""
        provider = Mock(spec=ZerodhaDataProvider)
        provider.supported_timeframes_property = ["1M", "3M", "5M", "10M", "15M", "30M", "1H", "1D"]
        provider._map_timeframe_to_zerodha = Mock(side_effect=lambda tf: {
            "1M": "minute",
            "3M": "3minute",
            "5M": "5minute",
            "10M": "10minute",
            "15M": "15minute",
            "30M": "30minute",
            "1H": "60minute",
            "1D": "day",
        }[tf])
        
        # Make fetch return appropriate data based on interval
        # The provider's fetch() returns {"candles": [...]} format (merged response)
        def fetch_side_effect(*args, interval=None, from_date=None, to_date=None, **kwargs):
            if interval in ("minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute"):
                return {"candles": MOCK_HISTORICAL_RESPONSE_MINUTE["data"]["candles"]}
            return {"candles": MOCK_HISTORICAL_RESPONSE_DAY["data"]["candles"]}
        
        provider.fetch.side_effect = fetch_side_effect
        return provider

    def test_adapter_init_valid_provider(self, mock_provider):
        """Adapter should accept ZerodhaDataProvider instance."""
        adapter = ZerodhaDataAdapter(mock_provider)
        assert adapter._provider is mock_provider

    def test_adapter_init_invalid_provider_raises(self):
        """Adapter should reject non-ZerodhaDataProvider instances."""
        class FakeProvider:
            def fetch(self): return {}
            def close(self): pass

        with pytest.raises(TypeError, match="ZerodhaDataAdapter requires ZerodhaDataProvider"):
            ZerodhaDataAdapter(FakeProvider())

    def test_adapter_read_daily_data(self, mock_provider):
        """Adapter should normalize daily data correctly."""
        adapter = ZerodhaDataAdapter(mock_provider)
        result = adapter.read_timeframe("1D")

        assert len(result) == 5
        assert all(key in result[0] for key in ["datetime", "open", "high", "low", "close", "volume"])
        assert "oi" not in result[0]  # No OI in daily mock

        # Check first row
        assert result[0]["open"] == 2500.0
        assert result[0]["high"] == 2520.0
        assert result[0]["low"] == 2490.0
        assert result[0]["close"] == 2510.0
        assert result[0]["volume"] == 100000

        # Default output timezone is IST. The first mock timestamp is
        # 2024-01-01T00:00:00+0530 (IST midnight of trading day 2024-01-01).
        assert result[0]["datetime"] == "2024-01-01 00:00:00"

    def test_adapter_read_minute_data(self, mock_provider):
        """Adapter should normalize minute data correctly."""
        # The fixture's side_effect already returns minute data for minute intervals
        adapter = ZerodhaDataAdapter(mock_provider)
        result = adapter.read_timeframe("1M")

        assert len(result) == 5
        assert result[0]["open"] == 2500.0
        # First mock timestamp is 2024-01-01T09:15:00+0530 (market open).
        assert result[0]["datetime"] == "2024-01-01 09:15:00"

    def test_adapter_read_with_oi(self, mock_provider):
        """Adapter should handle open interest data."""
        # The fixture's side_effect returns minute data for minute intervals,
        # but we need OI data. Let's override fetch for this test.
        mock_provider.fetch.side_effect = None
        mock_provider.fetch.return_value = {"candles": MOCK_HISTORICAL_RESPONSE_WITH_OI["data"]["candles"]}

        adapter = ZerodhaDataAdapter(mock_provider)
        result = adapter.read_timeframe("1M")

        assert len(result) == 3
        assert "oi" in result[0]
        assert result[0]["oi"] == 50000

    def test_adapter_read_empty_data(self, mock_provider):
        """Adapter should return empty list for empty data."""
        mock_provider.fetch.side_effect = None
        mock_provider.fetch.return_value = {"candles": []}

        adapter = ZerodhaDataAdapter(mock_provider)
        result = adapter.read()

        assert result == []

    def test_adapter_custom_datetime_format(self, mock_provider):
        """Adapter should use custom datetime format."""
        adapter = ZerodhaDataAdapter(mock_provider, datetime_format="%Y/%m/%d %H:%M")
        result = adapter.read_timeframe("1D")

        assert result[0]["datetime"] == "2024/01/01 00:00"

    def test_adapter_explicit_ist_timezone(self, mock_provider):
        """Adapter should honour an explicit IST output timezone."""
        adapter = ZerodhaDataAdapter(mock_provider, timezone="Asia/Kolkata")
        result = adapter.read_timeframe("1D")

        # Mock timestamp 2024-01-01T00:00:00+0530 == 2024-01-01 00:00:00 IST.
        assert result[0]["datetime"] == "2024-01-01 00:00:00"

    def test_adapter_utc_output_timezone(self, mock_provider):
        """Adapter should project to UTC when explicitly requested."""
        adapter = ZerodhaDataAdapter(mock_provider, timezone="UTC")
        result = adapter.read_timeframe("1D")

        # Mock timestamp 2024-01-01T00:00:00+0530 is 2023-12-31 18:30:00 UTC
        assert result[0]["datetime"] == "2023-12-31 18:30:00"

    def test_adapter_invalid_timezone_raises(self, mock_provider):
        """Adapter should raise on invalid timezones instead of silently misprojecting."""
        with pytest.raises(ValueError, match="Invalid timezone"):
            ZerodhaDataAdapter(mock_provider, timezone="Invalid/Timezone")

    def test_adapter_close_delegates_to_provider(self, mock_provider):
        """Adapter close() should delegate to provider.close()."""
        adapter = ZerodhaDataAdapter(mock_provider)
        adapter.close()
        mock_provider.close.assert_called_once()

    def test_adapter_context_manager(self, mock_provider):
        """Adapter should work as context manager."""
        with ZerodhaDataAdapter(mock_provider) as adapter:
            assert adapter._provider is mock_provider

    def test_adapter_read_timeframe_validation(self, mock_provider):
        """Adapter should validate timeframe is supported."""
        adapter = ZerodhaDataAdapter(mock_provider)
        with pytest.raises(ValueError, match="Timeframe 'invalid' not supported"):
            adapter.read_timeframe("invalid")

    def test_adapter_read_timeframe_minute(self, mock_provider):
        """Adapter should fetch and normalize minute timeframe."""
        mock_provider.fetch.return_value = MOCK_HISTORICAL_RESPONSE_MINUTE

        adapter = ZerodhaDataAdapter(mock_provider)
        result = adapter.read_timeframe("1M")

        assert len(result) == 5
        assert result[0]["datetime"] == "2024-01-01 09:15:00"
        mock_provider.fetch.assert_called_once_with(interval="minute", from_date=None, to_date=None)

    def test_adapter_read_timeframe_day(self, mock_provider):
        """Adapter should fetch and normalize day timeframe."""
        mock_provider.fetch.return_value = MOCK_HISTORICAL_RESPONSE_DAY

        adapter = ZerodhaDataAdapter(mock_provider)
        result = adapter.read_timeframe("1D")

        assert len(result) == 5
        assert result[0]["datetime"] == "2024-01-01 00:00:00"
        mock_provider.fetch.assert_called_once_with(interval="day", from_date=None, to_date=None)