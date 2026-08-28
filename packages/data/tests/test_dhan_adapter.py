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

        # Default output timezone is IST. The first mock epoch represents
        # 2024-01-01 00:00:00 IST (the IST midnight of the trading day
        # 2024-01-01, matching Dhan's documented behaviour).
        assert result[0]["datetime"] == "2024-01-01 00:00:00"

    def test_adapter_read_intraday_data(self, mock_provider):
        """Adapter should normalize intraday data correctly."""
        mock_provider.fetch.return_value = MOCK_INTRADAY_HISTORICAL_RESPONSE

        adapter = DhanDataAdapter(mock_provider)
        result = adapter.read()

        assert len(result) == 5
        assert result[0]["open"] == 2500.0
        # First mock epoch represents 2024-01-01 09:15:00 IST.
        assert result[0]["datetime"] == "2024-01-01 09:15:00"

    def test_adapter_read_without_oi(self, mock_provider):
        """Adapter should handle missing open interest."""
        mock_provider.fetch.return_value = {
            "open": [2500.0],
            "high": [2520.0],
            "low": [2490.0],
            "close": [2510.0],
            "volume": [100000],
            "timestamp": [1704047400],  # 2024-01-01 00:00:00 IST
        }

        adapter = DhanDataAdapter(mock_provider)
        result = adapter.read()

        assert len(result) == 1
        assert "oi" not in result[0]
        assert result[0]["datetime"] == "2024-01-01 00:00:00"

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

    def test_adapter_explicit_ist_timezone(self, mock_provider):
        """Adapter should honour an explicit IST output timezone."""
        adapter = DhanDataAdapter(mock_provider, timezone="Asia/Kolkata")
        result = adapter.read()

        # Mock epoch 1704047400 == 2024-01-01 00:00:00 IST.
        assert result[0]["datetime"] == "2024-01-01 00:00:00"

    def test_adapter_utc_output_timezone(self, mock_provider):
        """Adapter should project to UTC when explicitly requested."""
        adapter = DhanDataAdapter(mock_provider, timezone="UTC")
        result = adapter.read()

        # Mock epoch 1704047400 is 2023-12-31 18:30:00 UTC
        # (= 2024-01-01 00:00:00 IST). Output wall clock in UTC is
        # therefore the previous calendar day at 18:30.
        assert result[0]["datetime"] == "2023-12-31 18:30:00"

    def test_adapter_invalid_timezone_raises(self, mock_provider):
        """Adapter should raise on invalid timezones instead of silently misprojecting."""
        with pytest.raises(ValueError, match="Invalid timezone"):
            DhanDataAdapter(mock_provider, timezone="Invalid/Timezone")

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
            "timestamp": [1704047400, 1704133800],  # 2024-01-01 and 2024-01-02 IST midnight
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
            "timestamp": [1704047400],  # 2024-01-01 IST midnight
            "open_interest": [50000, 55000],  # 2 elements vs 1
        }

        adapter = DhanDataAdapter(mock_provider)
        with pytest.raises(ValueError, match="Open interest array length mismatch"):
            adapter.read()


class TestDhanAdapterTimezoneRegression:
    """Regression tests for the IST/UTC misinterpretation bug.

    Original defect: ``DhanDataAdapter.read`` treated Dhan's epoch-seconds
    as if they were UTC (``datetime.fromtimestamp(epoch, tz=timezone.utc)``),
    even though the official ``dhanhq-py`` SDK and Dhan's own server
    semantics both treat the value as IST. The result was that every
    Indian-market daily candle in the exported ``closed_trades.csv``
    appeared at ``T18:30:00`` (one IST day ahead, after market hours) and
    intraday candles were shifted off-market. These tests pin the
    correct behaviour so the bug cannot regress.
    """

    @pytest.fixture
    def mock_provider(self):
        provider = Mock(spec=DhanDataProvider)
        provider.fetch.return_value = MOCK_DAILY_HISTORICAL_RESPONSE
        return provider

    def test_daily_candle_does_not_appear_post_market(self, mock_provider):
        """A daily candle for an IST trading day must not surface as 18:30.

        Before the fix, ``datetime.fromtimestamp(1704047400, tz=utc)`` was
        rendered as ``2024-01-01 00:00:00`` (wall-clock-only, UTC-labelled)
        and after the buggy ``astimezone('Asia/Kolkata')`` it became
        ``2024-01-01 05:30:00 IST``. The exported CSV's ``entry_timestamp``
        column therefore showed ``T18:30:00`` for every daily candle,
        which is the exact symptom reported in the bug.
        """
        adapter = DhanDataAdapter(mock_provider)
        rows = adapter.read()

        # Default output is IST. Mock epoch 1704047400 is the IST midnight
        # of the trading day 2024-01-01. The naive wall clock must match
        # that instant, not 18:30 of any surrounding day.
        first = rows[0]["datetime"]
        assert first == "2024-01-01 00:00:00", (
            f"Daily candle appeared as {first!r} (post-market/off-day); "
            f"expected 2024-01-01 00:00:00 IST. This is the regression "
            f"from the IST-as-UTC interpretation bug."
        )
        # Defensive: the timestamp must NOT contain the buggy 18:30 suffix.
        for row in rows:
            assert " 18:30:00" not in row["datetime"], (
                f"Daily candle at {row['datetime']!r} still shows 18:30 - "
                f"the IST-as-UTC bug has regressed."
            )

    def test_intraday_candle_lands_in_market_hours(self, mock_provider):
        """An IST 09:15 candle must surface as 09:15, not 04:45/12:45/etc.

        Mock intraday epoch ``1704080700`` is 2024-01-01 09:15:00 IST.
        The pre-fix path interpreted the epoch as UTC, producing a wall
        clock of 03:45 UTC (and after the false IST shift: 09:15 IST, but
        with the wrong day/offset chain). We pin the expected projection
        so the only correct interpretation wins.
        """
        mock_provider.fetch.return_value = MOCK_INTRADAY_HISTORICAL_RESPONSE
        adapter = DhanDataAdapter(mock_provider)
        rows = adapter.read()

        assert rows[0]["datetime"] == "2024-01-01 09:15:00"
        # Subsequent candles are one minute apart in IST.
        assert rows[1]["datetime"] == "2024-01-01 09:16:00"
        assert rows[2]["datetime"] == "2024-01-01 09:17:00"

    def test_default_output_timezone_is_ist(self, mock_provider):
        """The adapter must default to IST so naive ``Candle.timestamp`` matches the exchange clock."""
        adapter = DhanDataAdapter(mock_provider)
        assert adapter._timezone_name == "Asia/Kolkata"

    def test_dhan_epoch_is_interpreted_as_ist_not_utc(self, mock_provider):
        """The conversion from Dhan's epoch must use IST as the source zone.

        Concretely: epoch ``1704047400`` is 2024-01-01 00:00:00 IST. With
        the buggy code path (treat epoch as UTC, then astimezone to IST),
        the same epoch produced 2024-01-01 05:30:00 IST. The correct
        behaviour is to land on 00:00 IST.
        """
        # Source = IST, output = IST: identity projection.
        adapter = DhanDataAdapter(mock_provider, timezone="Asia/Kolkata")
        rows = adapter.read()
        assert rows[0]["datetime"] == "2024-01-01 00:00:00"

        # Source = IST, output = UTC: same instant, displayed in UTC
        # (i.e. 2023-12-31 18:30:00 UTC, the previous calendar day).
        adapter_utc = DhanDataAdapter(mock_provider, timezone="UTC")
        rows_utc = adapter_utc.read()
        assert rows_utc[0]["datetime"] == "2023-12-31 18:30:00"

    def test_invalid_timezone_is_a_construction_error(self, mock_provider):
        """The pre-fix implementation silently fell back to UTC for bad timezones.

        That silent fallback is what hid the original IST-as-UTC bug from
        callers. We now raise loudly at construction so misconfiguration
        is caught immediately.
        """
        with pytest.raises(ValueError, match="Invalid timezone"):
            DhanDataAdapter(mock_provider, timezone="Not/AZone")