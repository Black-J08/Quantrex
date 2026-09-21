"""Data Orchestrator for Quantrex Backtest.

Coordinates data preparation for backtesting using quantrex-data primitives.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from quantrex_core import InstrumentSpec, PortfolioConfig
from quantrex_core.logging import get_logger
from quantrex_data.operations import (
    validate_data_format,
    validate_completeness,
    check_timestamp_alignment,
    synchronize_symbols,
)

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DataOrchestratorConfig:
    """Configuration for DataOrchestrator."""
    exchange_calendar: str = "NSE"
    auto_download: bool = True
    validate_completeness: bool = True
    min_bars_required: int = 100
    alignment_tolerance_seconds: int = 60


class DataOrchestrator:
    """Orchestrates data preparation for backtesting.

    Uses quantrex-data operations for validation and alignment.
    Caching is handled transparently by DataProviders.
    """

    def __init__(self, config: Optional[DataOrchestratorConfig] = None):
        self.config = config or DataOrchestratorConfig()

    def validate_and_prepare(
        self,
        instruments: List[InstrumentSpec],
        config: PortfolioConfig,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Validate and prepare data for all instruments.

        Args:
            instruments: List of instrument specifications.
            config: Portfolio configuration with date range and download settings.

        Returns:
            Dictionary mapping symbol to synchronized data rows.

        Raises:
            ValueError: If data validation fails critically.
        """
        logger.info("Starting data preparation for %d instruments", len(instruments))

        # Parse date range for validation
        start = self._parse_date(config.data_start) if config.data_start else None
        end = self._parse_date(config.data_end) if config.data_end else None

        # Step 1: Load/Download data for each instrument
        symbol_data = {}
        for spec in instruments:
            data = self._prepare_instrument_data(spec, config)
            symbol_data[spec.symbol] = data

        # Step 2: Validate each instrument's data
        if self.config.validate_completeness:
            self._validate_all_data(symbol_data, start, end)

        # Step 3: Align timestamps across symbols (only for multi-symbol)
        if len(symbol_data) > 1:
            synchronized = synchronize_symbols(
                symbol_data,
                exchange=self.config.exchange_calendar,
                timeframe="1M",  # Base timeframe
            )
        else:
            # Single symbol: no synchronization needed, use data as-is
            synchronized = symbol_data

        # Step 4: Final validation of alignment (only for multi-symbol)
        if len(synchronized) > 1:
            is_aligned, warnings = check_timestamp_alignment(
                synchronized,
                tolerance_seconds=self.config.alignment_tolerance_seconds,
            )
            for warning in warnings:
                logger.warning("Alignment warning: %s", warning)

            if not is_aligned:
                logger.warning("Timestamp alignment issues detected but continuing")

        logger.info("Data preparation complete for %d instruments", len(synchronized))
        return synchronized

    def _prepare_instrument_data(
        self,
        spec: InstrumentSpec,
        config: PortfolioConfig,
    ) -> List[Dict[str, Any]]:
        """Prepare data for a single instrument.

        Caching is handled transparently by the DataProvider.
        """
        symbol = spec.symbol
        adapter = spec.adapter

        # Read from adapter (provider handles caching internally)
        # Pass date range to adapter for provider-level filtering
        logger.info("Reading data from adapter for %s", symbol)
        try:
            data = adapter.read_timeframe("1M", from_date=config.data_start, to_date=config.data_end)
        except Exception as e:
            logger.exception("Failed to read data from adapter for %s: %s", symbol, e)
            raise ValueError(f"Failed to read data for {symbol}: {e}")

        if not data:
            logger.warning("No data returned from adapter for %s", symbol)
            return []

        # Validate format
        is_valid, errors = validate_data_format(data)
        if not is_valid:
            for error in errors:
                logger.error("Data format error for %s: %s", symbol, error)
            raise ValueError(f"Invalid data format for {symbol}: {errors[:5]}")

        return data

    def _validate_all_data(
        self,
        symbol_data: Dict[str, List[Dict[str, Any]]],
        start: Optional[datetime],
        end: Optional[datetime],
    ) -> None:
        """Validate completeness for all symbols."""
        for symbol, data in symbol_data.items():
            _, warnings = validate_completeness(
                data,
                expected_start=start,
                expected_end=end,
                expected_freq="1M",
                min_bars=self.config.min_bars_required,
            )
            for warning in warnings:
                logger.warning("Completeness check for %s: %s", symbol, warning)

    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime."""
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"Invalid date format: {date_str}")