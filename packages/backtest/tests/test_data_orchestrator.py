"""Tests for DataOrchestrator and data operations."""

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


class TestDataValidation:
    """Tests for data validation operations."""

    def test_validate_data_format_valid(self):
        """Test validation of valid data format."""
        rows = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            {"datetime": "20260101 09:16", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]
        is_valid, errors = validate_data_format(rows)
        assert is_valid is True
        assert errors == []

    def test_validate_data_format_missing_columns(self):
        """Test validation fails with missing columns."""
        rows = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101"},
        ]
        is_valid, errors = validate_data_format(rows)
        assert is_valid is False
        assert any("Missing required columns" in e for e in errors)

    def test_validate_data_format_invalid_values(self):
        """Test validation fails with invalid values."""
        rows = [
            {"datetime": "20260101 09:15", "open": "abc", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]
        is_valid, errors = validate_data_format(rows)
        assert is_valid is False
        assert any("must be numeric" in e for e in errors)

    def test_validate_data_format_ohlc_relationships(self):
        """Test validation checks OHLC relationships."""
        rows = [
            {"datetime": "20260101 09:15", "open": "100", "high": "99", "low": "101", "close": "100", "volume": "1000"},
        ]
        is_valid, errors = validate_data_format(rows)
        assert is_valid is False
        assert any("high" in e and "max" in e for e in errors)

    def test_validate_completeness_sufficient_data(self):
        """Test completeness check with sufficient data."""
        rows = [{"datetime": f"20260101 {9+i//60:02d}:{i%60:02d}", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"} for i in range(200)]
        is_valid, warnings = validate_completeness(rows, min_bars=100)
        assert is_valid is True

    def test_validate_completeness_insufficient_data(self):
        """Test completeness check with insufficient data."""
        rows = [{"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"}]
        is_valid, warnings = validate_completeness(rows, min_bars=100)
        assert is_valid is True  # Returns True but with warnings
        assert any("Insufficient data" in w for w in warnings)


class TestTimestampAlignment:
    """Tests for timestamp alignment operations."""

    def test_check_timestamp_alignment_aligned(self):
        """Test alignment check with aligned timestamps."""
        symbol_data = {
            "RELIANCE": [
                {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
                {"datetime": "20260101 09:16", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            ],
            "TCS": [
                {"datetime": "20260101 09:15", "open": "3000", "high": "3001", "low": "2999", "close": "3000", "volume": "1000"},
                {"datetime": "20260101 09:16", "open": "3000", "high": "3001", "low": "2999", "close": "3000", "volume": "1000"},
            ],
        }
        is_aligned, warnings = check_timestamp_alignment(symbol_data)
        assert is_aligned is True
        assert warnings == []

    def test_check_timestamp_alignment_misaligned(self):
        """Test alignment check with misaligned timestamps."""
        symbol_data = {
            "RELIANCE": [
                {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            ],
            "TCS": [
                {"datetime": "20260101 09:16", "open": "3000", "high": "3001", "low": "2999", "close": "3000", "volume": "1000"},
            ],
        }
        is_aligned, warnings = check_timestamp_alignment(symbol_data, tolerance_seconds=10)
        assert is_aligned is False
        assert any("misalignment" in w for w in warnings)


class TestAlignment:
    """Tests for timestamp alignment operations."""

    def test_align_to_exchange_calendar(self):
        """Test aligning data to exchange calendar."""
        data = [
            {"datetime": "20260101 09:14", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},  # Before market open
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},  # Market open
            {"datetime": "20260101 15:30", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},  # Market close
            {"datetime": "20260101 15:31", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},  # After market close
        ]
        aligned = align_to_exchange_calendar(data, exchange="NSE")
        assert len(aligned) == 2  # Only market hours
        assert aligned[0]["datetime"] == "20260101 09:15"
        assert aligned[1]["datetime"] == "20260101 15:30"

    def test_synchronize_symbols(self):
        """Test synchronizing multiple symbols."""
        symbol_data = {
            "RELIANCE": [
                {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
                {"datetime": "20260101 09:16", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
            ],
            "TCS": [
                {"datetime": "20260101 09:15", "open": "3000", "high": "3001", "low": "2999", "close": "3000", "volume": "1000"},
                {"datetime": "20260101 09:16", "open": "3000", "high": "3001", "low": "2999", "close": "3000", "volume": "1000"},
            ],
        }
        synchronized = synchronize_symbols(symbol_data)
        assert "RELIANCE" in synchronized
        assert "TCS" in synchronized
        assert len(synchronized["RELIANCE"]) == 2
        assert len(synchronized["TCS"]) == 2


class TestDataOrchestrator:
    """Tests for DataOrchestrator."""

    def test_orchestrator_initialization(self):
        """Test DataOrchestrator initialization."""
        config = DataOrchestratorConfig(
            exchange_calendar="NSE",
            auto_download=False,
            validate_completeness=True,
            min_bars_required=100,
        )
        orchestrator = DataOrchestrator(config)
        assert orchestrator.config == config

    def test_orchestrator_default_config(self):
        """Test DataOrchestrator with default config."""
        orchestrator = DataOrchestrator()
        assert orchestrator.config.exchange_calendar == "NSE"
        assert orchestrator.config.auto_download is True

    def test_validate_and_prepare_no_instruments(self):
        """Test validate_and_prepare with no instruments."""
        orchestrator = DataOrchestrator()
        result = orchestrator.validate_and_prepare([], BacktestConfig())
        assert result == {}

    def test_validate_and_prepare_with_mock_adapter(self):
        """Test validate_and_prepare with mock adapter."""
        from quantrex_core import InstrumentSpec
        from quantrex_backtest import BacktestConfig
        from quantrex_core.protocols import DataAdapter

        mock_adapter = Mock(spec=DataAdapter)
        mock_adapter.read_timeframe.return_value = [
            {"datetime": "20260101 09:15", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1000"},
        ]
        mock_adapter.datetime_format = "%Y%m%d %H:%M"
        mock_adapter.supported_timeframes = ["1M"]
        mock_adapter.get_origin_time.return_value = None

        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=mock_adapter)]
        config = BacktestConfig(auto_download=False)

        orchestrator = DataOrchestrator(DataOrchestratorConfig(
            auto_download=False,
            validate_completeness=False,
            min_bars_required=1,
        ))

        result = orchestrator.validate_and_prepare(instruments, config)

        assert "RELIANCE" in result
        assert len(result["RELIANCE"]) == 1

