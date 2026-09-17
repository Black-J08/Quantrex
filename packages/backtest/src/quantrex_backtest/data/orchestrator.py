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
    ParquetCache,
    get_cache_dir,
    align_to_exchange_calendar,
    resample_to_timeframe,
    synchronize_symbols,
    download_dhan_data,
    download_zerodha_data,
)

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DataOrchestratorConfig:
    """Configuration for DataOrchestrator."""
    cache_dir: Path = Path("data/cache")
    exchange_calendar: str = "NSE"
    auto_download: bool = True
    validate_completeness: bool = True
    min_bars_required: int = 100
    alignment_tolerance_seconds: int = 60


class DataOrchestrator:
    """Orchestrates data preparation for backtesting.

    Uses quantrex-data operations for validation, download, caching, and alignment.
    """

    def __init__(self, config: Optional[DataOrchestratorConfig] = None):
        self.config = config or DataOrchestratorConfig()
        self.cache = ParquetCache(self.config.cache_dir)

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

        # Parse date range
        start = self._parse_date(config.data_start) if config.data_start else None
        end = self._parse_date(config.data_end) if config.data_end else None

        # Step 1: Load/Download data for each instrument
        symbol_data = {}
        for spec in instruments:
            data = self._prepare_instrument_data(spec, start, end, config.auto_download)
            symbol_data[spec.symbol] = data

        # Step 2: Validate each instrument's data
        if self.config.validate_completeness:
            self._validate_all_data(symbol_data, start, end)

        # Step 3: Align timestamps across symbols
        synchronized = synchronize_symbols(
            symbol_data,
            exchange=self.config.exchange_calendar,
            timeframe="1M",  # Base timeframe
        )

        # Step 4: Final validation of alignment
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
        start: Optional[datetime],
        end: Optional[datetime],
        auto_download: bool,
    ) -> List[Dict[str, Any]]:
        """Prepare data for a single instrument."""
        symbol = spec.symbol
        adapter = spec.adapter

        # Try cache first
        if start and end:
            cached = self.cache.load(symbol, "1M", start, end)
            if cached is not None:
                logger.info("Using cached data for %s (%d rows)", symbol, len(cached))
                return cached

        # Read from adapter
        logger.info("Reading data from adapter for %s", symbol)
        try:
            data = adapter.read_timeframe("1M")
        except Exception as e:
            logger.exception("Failed to read data from adapter for %s: %s", symbol, e)
            raise ValueError(f"Failed to read data for {symbol}: {e}")

        if not data:
            logger.warning("No data returned from adapter for %s", symbol)

        # Filter by date range if specified
        if start or end:
            data = self._filter_by_date_range(data, start, end)

        # Validate format
        is_valid, errors = validate_data_format(data)
        if not is_valid:
            for error in errors:
                logger.error("Data format error for %s: %s", symbol, error)
            raise ValueError(f"Invalid data format for {symbol}: {errors[:5]}")

        # Auto-download if enabled and data is insufficient
        if auto_download and (not data or len(data) < self.config.min_bars_required):
            logger.info("Attempting auto-download for %s", symbol)
            downloaded = self._attempt_download(spec, start, end)
            if downloaded:
                data = downloaded
                # Re-validate
                is_valid, errors = validate_data_format(data)
                if not is_valid:
                    logger.error("Downloaded data also invalid for %s", symbol)

        # Cache the data
        if start and end and data:
            self.cache.save(symbol, "1M", start, end, data)

        return data

    def _attempt_download(
        self,
        spec: InstrumentSpec,
        start: Optional[datetime],
        end: Optional[datetime],
    ) -> Optional[List[Dict[str, Any]]]:
        """Attempt to download data from provider."""
        adapter = spec.adapter

        # Check if adapter has a provider we can use for download
        provider = getattr(adapter, '_provider', None)
        if provider is None:
            logger.warning("No provider available for download on %s", spec.symbol)
            return None

        # Try Dhan
        if provider.__class__.__name__ == "DhanDataProvider":
            try:
                return download_dhan_data(
                    symbol=spec.symbol,
                    start=start or datetime(2020, 1, 1),
                    end=end or datetime.now(),
                    timeframe="1M",
                )
            except Exception as e:
                logger.warning("Dhan download failed for %s: %s", spec.symbol, e)

        # Try Zerodha
        if provider.__class__.__name__ == "ZerodhaDataProvider":
            try:
                return download_zerodha_data(
                    symbol=spec.symbol,
                    start=start or datetime(2020, 1, 1),
                    end=end or datetime.now(),
                    timeframe="1M",
                )
            except Exception as e:
                logger.warning("Zerodha download failed for %s: %s", spec.symbol, e)

        return None

    def _filter_by_date_range(
        self,
        data: List[Dict[str, Any]],
        start: Optional[datetime],
        end: Optional[datetime],
    ) -> List[Dict[str, Any]]:
        """Filter data by date range."""
        if not start and not end:
            return data

        filtered = []
        for row in data:
            dt_val = row.get("datetime")
            if isinstance(dt_val, str):
                for fmt in ("%Y%m%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        dt = datetime.strptime(dt_val, fmt)
                        break
                    except ValueError:
                        continue
            elif isinstance(dt_val, datetime):
                dt = dt_val
            else:
                continue

            if start and dt < start:
                continue
            if end and dt > end:
                continue
            filtered.append(row)

        return filtered

    def _validate_all_data(
        self,
        symbol_data: Dict[str, List[Dict[str, Any]]],
        start: Optional[datetime],
        end: Optional[datetime],
    ) -> None:
        """Validate completeness for all symbols."""
        for symbol, data in symbol_data.items():
            is_valid, warnings = validate_completeness(
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