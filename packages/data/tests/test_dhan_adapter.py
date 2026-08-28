"""Tests for DhanDataAdapter."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from quantrex_data.adapters.dhan_adapter import DhanDataAdapter
from quantrex_data.providers.dhan_provider import DhanDataProvider
from quantrex_core.protocols import DataAdapter
from quantrex_test_support.dhan import MOCK_DAILY_HISTORICAL_RESPONSE, MOCK_INTRADAY_HISTORICAL_RESPONSE


class TestDhanDataAdapter:
    """Tests for DhanDataAdapter."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock DhanDataProvider."""
        provider = Mock(spec=DhanDataProvider)
        provider.fetch.return_value = MOCK_DAILY_HISTORICAL_RESPONSE
        return provider

    def test_adapter_init_valid_provider(self, mock_provider):
        """Adapter should accept DhanDataProvider instance."""
        adapter = DhanDataAdapter(mock_provider)
        assert adapter._provider is mock_provider

    def test_adapter_init_invalid_provider_raises(self):
        """Adapter should reject non-DhanDataProvider instances."""
        class FakeProvider:
            def fetch(self): return {}
            def close(self): pass

        with pytest.raises(TypeError, match="DhanDataAdapter requires DhanDataProvider"):
            DhanDataAdapter(FakeProvider())

    def test_adapter_read_daily_data(self, mock_provider):
        """Adapter should normalize daily data correctly."""
        adapter = DhanDataAdapter(mock_provider)
        result = adapter.read()

        assert len(result) == 5
        assert all(key in result[0] for key in ["datetime", "open", "high", "low", "close", "volume"])
        assert "oi" in result[0]  # Open interest present

        # Check first row
        assert result[0]["open"] == 2500.0
        assert result[0]["high"] == 2520.0
        assert result[0]["low"] == 2490.0
        assert result[0]["close"] == 2510.0
        assert result[0]["volume"] == 100000
        assert result[0]["oi"] == 50000

        # Check datetime format (UTC by default)
        assert result[0]["datetime"] == "2024-01-01 00:00:00"  # 1704067200 = 2024-01-01 00:00:00 UTC

    def test_adapter_read_intraday_data(self, mock_provider):
        """Adapter should normalize intraday data correctly."""
        mock_provider.fetch.return_value = MOCK_INTRADAY_HISTORICAL_RESPONSE

        adapter = DhanDataAdapter(mock_provider)
        result = adapter.read()

        assert len(result) == 5
        assert result[0]["open"] == 2500.0
        # 1704093300 = 2024-01-01 07:15:00 UTC
        assert result[0]["datetime"] == "2024-01-01 07:15:00"

    def test_adapter_read_without_oi(self, mock_provider):
        """Adapter should handle missing open interest."""
        mock_provider.fetch.return_value = {
            "open": [2500.0],
            "high": [2520.0],
            "low": [2490.0],
            "close": [2510.0],
            "volume": [100000],
            "timestamp": [1704067200],
        }

        adapter = DhanDataAdapter(mock_provider)
        result = adapter.read()

        assert len(result) == 1
        assert "oi" not in result[0]

    def test_adapter_read_empty_data(self, mock_provider):
        """Adapter should return empty list for empty data."""
        mock_provider.fetch.return_value = {}

        adapter = DhanDataAdapter(mock_provider)
        result = adapter.read()

        assert result == []

    def test_adapter_read_empty_arrays(self, mock_provider):
        """Adapter should return empty list for empty arrays."""
        mock_provider.fetch.return_value = {
            "open": [], "high": [], "low": [], "close": [],
            "volume": [], "timestamp": [], "open_interest": [],
        }

        adapter = DhanDataAdapter(mock_provider)
        result = adapter.read()

        assert result == []

    def test_adapter_custom_datetime_format(self, mock_provider):
        """Adapter should use custom datetime format."""
        adapter = DhanDataAdapter(mock_provider, datetime_format="%Y/%m/%d %H:%M")
        result = adapter.read()

        assert result[0]["datetime"] == "2024/01/01 00:00"

    def test_adapter_custom_timezone(self, mock_provider):
        """Adapter should convert to custom timezone."""
        adapter = DhanDataAdapter(mock_provider, timezone="Asia/Kolkata")
        result = adapter.read()

        # 1704067200 UTC = 2024-01-01 05:30:00 IST
        assert result[0]["datetime"] == "2024-01-01 05:30:00"

    def test_adapter_invalid_timezone_fallback(self, mock_provider):
        """Adapter should fallback to UTC for invalid timezone."""
        adapter = DhanDataAdapter(mock_provider, timezone="Invalid/Timezone")
        result = adapter.read()

        # Should still work, using UTC
        assert result[0]["datetime"] == "2024-01-01 00:00:00"

    def test_adapter_close_delegates_to_provider(self, mock_provider):
        """Adapter close() should delegate to provider.close()."""
        adapter = DhanDataAdapter(mock_provider)
        adapter.close()
        mock_provider.close.assert_called_once()

    def test_adapter_context_manager(self, mock_provider):
        """Adapter should work as context manager."""
        with DhanDataAdapter(mock_provider) as adapter:
            assert adapter._provider is mock_provider
        mock_provider.close.assert_called_once()

    def test_adapter_implements_data_adapter_protocol(self, mock_provider):
        """DhanDataAdapter should satisfy DataAdapter protocol."""
        adapter = DhanDataAdapter(mock_provider)

        assert hasattr(adapter, "read")
        assert callable(adapter.read)
        assert hasattr(adapter, "close")
        assert callable(adapter.close)

        # Should be usable where DataAdapter is expected
        adapter_instance: DataAdapter = adapter
        assert adapter_instance is not None

    def test_adapter_array_length_mismatch_raises(self, mock_provider):
        """Adapter should raise ValueError for mismatched array lengths."""
        mock_provider.fetch.return_value = {
            "open": [2500.0, 2510.0],
            "high": [2520.0],  # Only 1 element
            "low": [2490.0, 2505.0],
            "close": [2510.0, 2520.0],
            "volume": [100000, 150000],
            "timestamp": [1704067200, 1704153600],
        }

        adapter = DhanDataAdapter(mock_provider)
        with pytest.raises(ValueError, match="Response array lengths mismatch"):
            adapter.read()

    def test_adapter_oi_length_mismatch_raises(self, mock_provider):
        """Adapter should raise ValueError for OI array length mismatch."""
        mock_provider.fetch.return_value = {
            "open": [2500.0],
            "high": [2520.0],
            "low": [2490.0],
            "close": [2510.0],
            "volume": [100000],
            "timestamp": [1704067200],
            "open_interest": [50000, 55000],  # 2 elements vs 1
        }

        adapter = DhanDataAdapter(mock_provider)
        with pytest.raises(ValueError, match="Open interest array length mismatch"):
            adapter.read()