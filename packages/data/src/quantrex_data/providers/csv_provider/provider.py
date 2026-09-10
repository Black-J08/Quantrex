"""CSV Data Provider for Quantrex framework.

Fetches raw CSV data from files without any column mapping or validation.
Returns raw rows as lists of strings.
"""

import csv
from pathlib import Path
from typing import Any

from quantrex_core.logging import get_logger

logger = get_logger(__name__)


class CSVDataProvider:
    """Data provider for reading raw CSV files.
    
    Handles file I/O and basic CSV parsing only.
    Does NOT perform column mapping, validation, or normalization.
    """
    
    def __init__(
        self,
        file_path: str,
        has_header: bool = False,
        encoding: str = "utf-8",
        minute_data_available: bool = True,
    ) -> None:
        """Initialize CSV data provider.
        
        Args:
            file_path: Path to the CSV file
            has_header: Whether the CSV has a header row
            encoding: File encoding (default: utf-8)
            minute_data_available: Whether 1-minute data is available in the file.
                If False, the provider cannot supply 1M data and aggregation
                to higher timeframes is impossible. Default: True.
        """
        self._file_path = Path(file_path)
        self._has_header = has_header
        self._encoding = encoding
        self._minute_data_available = minute_data_available
        self._file_handle = None
        self._header = None
    
    def fetch(self, timeframe: str | None = None) -> Any:
        """Fetch raw CSV data from the file.
        
        Args:
            timeframe: Timeframe interval (e.g., "1M", "1H", "1D").
                      None returns the provider's default/base timeframe.
                      CSV provider only supports a single timeframe (the file's native resolution).
        
        Returns:
            If has_header=True: tuple of (header_row: list[str], data_rows: list[list[str]])
            If has_header=False: list[list[str]] (all rows including first)
        """
        if timeframe is not None:
            # CSV provider only supports its native timeframe
            logger.debug("CSVDataProvider.fetch called with timeframe=%s (ignored, using file's native resolution)", timeframe)
        
        if not self._file_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self._file_path}")
        
        logger.debug("Reading CSV file: %s", self._file_path)
        
        with open(self._file_path, "r", newline="", encoding=self._encoding) as file:
            reader = csv.reader(file)
            rows = list(reader)
        
        if not rows:
            logger.warning("CSV file is empty: %s", self._file_path)
            return [] if not self._has_header else ([], [])
        
        if self._has_header:
            self._header = rows[0]
            data_rows = rows[1:]
            logger.debug("CSV header: %s, %d data rows", self._header, len(data_rows))
            return (self._header, data_rows)
        else:
            logger.debug("CSV has no header, %d rows", len(rows))
            return rows
    
    def supported_timeframes(self) -> list[str]:
        """Return list of supported timeframe intervals.
        
        CSV provider only supports its native file resolution.
        Returns ["1M"] as a convention for minute-level data when available.
        Returns empty list when minute_data_available=False.
        """
        if self._minute_data_available:
            return ["1M"]
        return []
    
    @property
    def supported_timeframes_property(self) -> list[str]:
        """Property accessor for supported_timeframes."""
        return self.supported_timeframes()
    
    def close(self) -> None:
        """Close any open resources.
        
        For file-based provider, this is a no-op since we use context managers.
        Included for protocol compliance.
        """
        # File handles are managed via context managers in fetch()
        # This method exists for protocol compliance and future extensibility
        pass
    
    @property
    def header(self) -> list[str] | None:
        """Get the header row if available."""
        return self._header
    
    @property
    def file_path(self) -> Path:
        """Get the file path."""
        return self._file_path