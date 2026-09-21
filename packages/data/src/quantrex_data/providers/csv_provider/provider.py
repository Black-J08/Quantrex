"""CSV Data Provider for Quantrex framework.

Fetches raw CSV data from files without any column mapping or validation.
Returns raw rows as lists of strings.
"""

import csv
from datetime import datetime, time
from pathlib import Path
from typing import Any

from quantrex_core.logging import get_logger
from quantrex_core.timeframe.constants import TF_1M

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
        datetime_format: str = "%Y%m%d %H:%M",
        datetime_column: int | list[int] = 0,
    ) -> None:
        """Initialize CSV data provider.
        
        Args:
            file_path: Path to the CSV file
            has_header: Whether the CSV has a header row
            encoding: File encoding (default: utf-8)
            minute_data_available: Whether 1-minute data is available in the file.
                If False, the provider cannot supply 1M data and aggregation
                to higher timeframes is impossible. Default: True.
            datetime_format: Format string for parsing datetime column(s) (default: "%Y%m%d %H:%M").
            datetime_column: Column index or list of column indices for datetime.
                If list, columns will be joined with a space. Default: 0.
        """
        self._file_path = Path(file_path)
        self._has_header = has_header
        self._encoding = encoding
        self._minute_data_available = minute_data_available
        self._datetime_format = datetime_format
        self._datetime_column = datetime_column
        self._file_handle = None
        self._header = None
    
    def fetch(
        self,
        timeframe: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> Any:
        """Fetch raw CSV data from the file.
        
        Args:
            timeframe: Timeframe interval (e.g., "1M", "1H", "1D").
                      None returns the provider's default/base timeframe.
                      CSV provider only supports a single timeframe (the file's native resolution).
            from_date: Optional start date for filtering (ISO format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS").
            to_date: Optional end date for filtering (ISO format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS").
        
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
        
        # Filter by date range if provided
        if from_date is not None or to_date is not None:
            rows = self._filter_rows_by_date(rows, from_date, to_date)
        
        if self._has_header:
            self._header = rows[0]
            data_rows = rows[1:]
            logger.debug("CSV header: %s, %d data rows", self._header, len(data_rows))
            return (self._header, data_rows)
        else:
            logger.debug("CSV has no header, %d rows", len(rows))
            return rows
    
    def _filter_rows_by_date(
        self,
        rows: list[list[str]],
        from_date: str | None,
        to_date: str | None,
    ) -> list[list[str]]:
        """Filter rows by date range."""
        if not from_date and not to_date:
            return rows
        
        from datetime import datetime
        
        # Parse filter dates
        filter_start = None
        filter_end = None
        if from_date:
            for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
                try:
                    filter_start = datetime.strptime(from_date, fmt)
                    break
                except ValueError:
                    continue
        if to_date:
            for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
                try:
                    filter_end = datetime.strptime(to_date, fmt)
                    break
                except ValueError:
                    continue
        
        filtered = []
        for row in rows:
            # Extract datetime from row
            dt_val = self._extract_datetime_from_row(row)
            if dt_val is None:
                continue
            
            if filter_start and dt_val < filter_start:
                continue
            if filter_end and dt_val > filter_end:
                continue
            filtered.append(row)
        
        return filtered
    
    def _extract_datetime_from_row(self, row: list[str]) -> datetime | None:
        """Extract datetime from a row based on configured datetime column(s)."""
        from datetime import datetime
        
        if isinstance(self._datetime_column, list):
            # Join multiple columns
            parts = []
            for idx in self._datetime_column:
                if idx < len(row):
                    parts.append(row[idx])
            dt_str = " ".join(parts)
        else:
            # Single column
            if self._datetime_column < len(row):
                dt_str = row[self._datetime_column]
            else:
                return None
        
        try:
            return datetime.strptime(dt_str, self._datetime_format)
        except ValueError:
            return None
    
    def supported_timeframes(self) -> list[str]:
        """Return list of supported timeframe intervals.
        
        CSV provider only supports its native file resolution.
        Returns ["1M"] as a convention for minute-level data when available.
        Returns empty list when minute_data_available=False.
        """
        if self._minute_data_available:
            return [str(TF_1M)]
        return []
    
    def get_origin_time(self) -> time:
        """Return the origin time for this provider's market.
        
        CSV provider uses NSE (National Stock Exchange of India) origin time
        as the standard for Indian market data.
        
        Returns:
            Origin time as datetime.time (09:15 for NSE).
        """
        from datetime import time
        return time(9, 15)
    
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