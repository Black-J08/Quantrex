"""Tests for data validations."""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from quantrex_core import InstrumentSpec
from quantrex_backtest import BacktestConfig
from quantrex_backtest.data import DataOrchestrator, DataOrchestratorConfig
from quantrex_data.operations import (
    validate_data_format,
    validate_completeness,
    check_timestamp_alignment,
    align_to_exchange_calendar,
    resample_to_timeframe,
    synchronize_symbols,
)
from quantrex_data.adapters.csv_adapter import CSVDataAdapter
from quantrex_data.providers.csv_provider import CSVDataProvider


class TestCalendarAwareValidation:
    """Tests for calendar-aware gap detection using exchange_calendars (XBOM for NSE/BSE)."""

    def _make_full_day_rows(self, date_str: str, count: int = 375) -> list[dict]:
        """Generate a full trading day of 1-minute bars (09:15-15:29)."""
        rows = []
        for minute in range(count):
            hour = 9 + (15 + minute) // 60
            min_val = (15 + minute) % 60
            rows.append({
                "datetime": f"{date_str} {hour:02d}:{min_val:02d}",
                "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"
            })
        return rows

    def test_validate_completeness_calendar_aware_no_gaps(self):
        """Calendar-aware validation: full trading day with no gaps should pass."""
        rows = self._make_full_day_rows("20260101")
        is_valid, warnings = validate_completeness(
            rows,
            expected_start=datetime(2026, 1, 1, 9, 15),
            expected_end=datetime(2026, 1, 1, 15, 29),
            expected_freq="1M",
            min_bars=100,
            exchange_calendar="NSE",
        )
        assert is_valid is True
        assert warnings == []

    def test_validate_completeness_calendar_aware_gap_during_market_hours(self):
        """Calendar-aware validation: gap during market hours should be flagged."""
        rows = self._make_full_day_rows("20260101")
        rows_with_gap = rows[:100] + rows[102:]  # Remove 2 bars
        is_valid, warnings = validate_completeness(
            rows_with_gap,
            expected_start=datetime(2026, 1, 1, 9, 15),
            expected_end=datetime(2026, 1, 1, 15, 29),
            expected_freq="1M",
            min_bars=100,
            exchange_calendar="NSE",
        )
        assert is_valid is True
        assert any("Missing bars" in w and "market hours" in w for w in warnings)

    def test_validate_completeness_calendar_aware_overnight_gap_ignored(self):
        """Calendar-aware validation: overnight gap should NOT be flagged."""
        rows_day1 = self._make_full_day_rows("20260101")
        rows_day2 = self._make_full_day_rows("20260102")
        rows_both = rows_day1 + rows_day2
        is_valid, warnings = validate_completeness(
            rows_both,
            expected_start=datetime(2026, 1, 1, 9, 15),
            expected_end=datetime(2026, 1, 2, 15, 29),
            expected_freq="1M",
            min_bars=100,
            exchange_calendar="NSE",
        )
        assert is_valid is True
        # Should not flag overnight gap
        assert not any("Missing bars" in w for w in warnings)

    def test_validate_completeness_calendar_aware_weekend_gap_ignored(self):
        """Calendar-aware validation: weekend gap should NOT be flagged."""
        rows_fri = self._make_full_day_rows("20260102")  # Friday
        rows_mon = self._make_full_day_rows("20260105")  # Monday
        rows_both = rows_fri + rows_mon
        is_valid, warnings = validate_completeness(
            rows_both,
            expected_start=datetime(2026, 1, 2, 9, 15),
            expected_end=datetime(2026, 1, 5, 15, 29),
            expected_freq="1M",
            min_bars=100,
            exchange_calendar="NSE",
        )
        assert is_valid is True
        assert not any("Missing bars" in w for w in warnings)

    def test_validate_completeness_calendar_aware_multi_day_with_gap(self):
        """Calendar-aware validation: multi-day with gap on middle day should flag only the gap."""
        rows_day1 = self._make_full_day_rows("20260101")
        rows_day2 = self._make_full_day_rows("20260102")
        rows_day2_with_gap = rows_day2[:100] + rows_day2[102:]
        rows_day3 = self._make_full_day_rows("20260105")
        rows_all = rows_day1 + rows_day2_with_gap + rows_day3
        is_valid, warnings = validate_completeness(
            rows_all,
            expected_start=datetime(2026, 1, 1, 9, 15),
            expected_end=datetime(2026, 1, 5, 15, 29),
            expected_freq="1M",
            min_bars=100,
            exchange_calendar="NSE",
        )
        assert is_valid is True
        assert any("Missing bars" in w and "market hours" in w for w in warnings)
        # Should only have one gap warning (for day 2)
        gap_warnings = [w for w in warnings if "Missing bars" in w]
        assert len(gap_warnings) == 1

    def test_validate_completeness_calendar_aware_bse_same_as_nse(self):
        """Calendar-aware validation: BSE should use same XBOM calendar as NSE."""
        rows = self._make_full_day_rows("20260101")
        rows_with_gap = rows[:100] + rows[102:]
        is_valid, warnings = validate_completeness(
            rows_with_gap,
            expected_start=datetime(2026, 1, 1, 9, 15),
            expected_end=datetime(2026, 1, 1, 15, 29),
            expected_freq="1M",
            min_bars=100,
            exchange_calendar="BSE",
        )
        assert is_valid is True
        assert any("Missing bars" in w and "market hours" in w for w in warnings)

    def test_validate_completeness_fallback_frequency_based(self):
        """Without exchange_calendar, falls back to frequency-based validation."""
        rows = self._make_full_day_rows("20260101")
        rows_with_gap = rows[:100] + rows[102:]
        is_valid, warnings = validate_completeness(
            rows_with_gap,
            expected_start=datetime(2026, 1, 1, 9, 15),
            expected_end=datetime(2026, 1, 1, 15, 29),
            expected_freq="1M",
            min_bars=100,
            exchange_calendar=None,
        )
        assert is_valid is True
        assert any("Possible gap" in w for w in warnings)

    def test_validate_completeness_fallback_flags_overnight_gap(self):
        """Frequency-based validation flags overnight gaps."""
        rows_day1 = self._make_full_day_rows("20260101")
        rows_day2 = self._make_full_day_rows("20260102")
        rows_both = rows_day1 + rows_day2
        is_valid, warnings = validate_completeness(
            rows_both,
            expected_start=datetime(2026, 1, 1, 9, 15),
            expected_end=datetime(2026, 1, 2, 15, 29),
            expected_freq="1M",
            min_bars=100,
            exchange_calendar=None,
        )
        assert is_valid is True
        assert any("Possible gap" in w for w in warnings)


class TestOrchestratorCalendarIntegration:
    """Integration tests for DataOrchestrator with calendar-aware validation."""

    def _make_full_day_rows(self, date_str: str, count: int = 375) -> list[dict]:
        """Generate a full trading day of 1-minute bars (09:15-15:29)."""
        rows = []
        for minute in range(count):
            hour = 9 + (15 + minute) // 60
            min_val = (15 + minute) % 60
            rows.append({
                "datetime": f"{date_str} {hour:02d}:{min_val:02d}",
                "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"
            })
        return rows

    def _make_csv_provider(self, rows: list[dict]) -> CSVDataAdapter:
        """Create a CSV adapter from in-memory rows."""
        import tempfile
        import os

        csv_content = "\n".join(
            f"{r['datetime']},{r['open']},{r['high']},{r['low']},{r['close']},{r['volume']}"
            for r in rows
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        provider = CSVDataProvider(
            file_path=csv_path,
            datetime_format='%Y%m%d %H:%M',
            has_header=False,
        )
        adapter = CSVDataAdapter(
            provider,
            column_mapping={'datetime': 0, 'open': 1, 'high': 2, 'low': 3, 'close': 4, 'volume': 5}
        )
        # Store path for cleanup
        adapter._csv_path = csv_path
        return adapter

    def test_orchestrator_calendar_aware_validation_no_gaps(self):
        """Orchestrator with NSE calendar: full day no gaps passes."""
        rows = self._make_full_day_rows("20260101")
        adapter = self._make_csv_provider(rows)
        spec = InstrumentSpec(symbol="TEST", adapter=adapter)

        orchestrator = DataOrchestrator(DataOrchestratorConfig(exchange_calendar="NSE"))
        config = BacktestConfig(data_start="20260101", data_end="20260101")

        result = orchestrator.validate_and_prepare([spec], config)
        assert "TEST" in result
        assert len(result["TEST"]) == 375

    def test_orchestrator_calendar_aware_validation_gap_flagged(self):
        """Orchestrator with NSE calendar: gap during market hours is flagged."""
        rows = self._make_full_day_rows("20260101")
        rows_with_gap = rows[:100] + rows[102:]
        adapter = self._make_csv_provider(rows_with_gap)
        spec = InstrumentSpec(symbol="TEST", adapter=adapter)

        orchestrator = DataOrchestrator(DataOrchestratorConfig(exchange_calendar="NSE"))
        config = BacktestConfig(data_start="20260101", data_end="20260101")

        result = orchestrator.validate_and_prepare([spec], config)
        assert "TEST" in result
        assert len(result["TEST"]) == 373

    def test_orchestrator_calendar_aware_overnight_gap_ignored(self):
        """Orchestrator with NSE calendar: overnight gap is ignored."""
        rows_day1 = self._make_full_day_rows("20260101")
        rows_day2 = self._make_full_day_rows("20260102")
        rows_both = rows_day1 + rows_day2
        adapter = self._make_csv_provider(rows_both)
        spec = InstrumentSpec(symbol="TEST", adapter=adapter)

        orchestrator = DataOrchestrator(DataOrchestratorConfig(exchange_calendar="NSE"))
        config = BacktestConfig(data_start="20260101", data_end="20260102")

        result = orchestrator.validate_and_prepare([spec], config)
        assert "TEST" in result
        assert len(result["TEST"]) == 750  # 375 * 2

    def test_orchestrator_without_calendar_uses_frequency_based(self):
        """Orchestrator without calendar config uses frequency-based validation."""
        rows_day1 = self._make_full_day_rows("20260101")
        rows_day2 = self._make_full_day_rows("20260102")
        rows_both = rows_day1 + rows_day2
        adapter = self._make_csv_provider(rows_both)
        spec = InstrumentSpec(symbol="TEST", adapter=adapter)

        orchestrator = DataOrchestrator(DataOrchestratorConfig(exchange_calendar=None))
        config = BacktestConfig(data_start="20260101", data_end="20260102")

        result = orchestrator.validate_and_prepare([spec], config)
        assert "TEST" in result
        assert len(result["TEST"]) == 750