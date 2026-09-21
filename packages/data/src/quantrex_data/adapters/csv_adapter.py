"""CSV Data Adapter for Quantrex framework.

Normalizes raw CSV data from CSVDataProvider into standardized OHLCV format
for the Backtest Engine.
"""

from datetime import time
from typing import Literal

from quantrex_core.logging import get_logger
from quantrex_core.protocols import DataProvider, DataAdapter
from quantrex_data.providers.csv_provider import CSVDataProvider

logger = get_logger(__name__)


class CSVDataAdapter:
    """Data adapter for normalizing CSV data to engine format.
    
    Consumes a CSVDataProvider and applies column mapping, validation,
    and type conversion to produce standardized OHLCV dictionaries.
    """
    
    REQUIRED_KEYS = ("datetime", "open", "high", "low", "close", "volume")
    
    def __init__(
        self,
        provider: DataProvider,
        column_mapping: dict,
        datetime_format: str = "%Y%m%d %H:%M",
    ) -> None:
        """Initialize CSV data adapter.
        
        Args:
            provider: CSVDataProvider instance to consume data from
            column_mapping: Mapping from standard keys to CSV columns.
                Supports index mode (int) or header mode (str).
                For datetime, supports single column or list of columns to join.
            datetime_format: Format string for parsing datetime (default: "%Y%m%d %H:%M")
        """
        if not isinstance(provider, CSVDataProvider):
            raise TypeError(f"CSVDataAdapter requires CSVDataProvider, got {type(provider).__name__}")
        
        self._provider = provider
        self._column_mapping = column_mapping
        self._datetime_format = datetime_format
        self._mode: Literal["index", "header"] | None = None
        self._header_index: dict[str, int] | None = None
    
    @property
    def datetime_format(self) -> str:
        """Format string used for datetime parsing (single source of truth)."""
        return self._datetime_format
    
    @property
    def supported_timeframes(self) -> list[str]:
        """Return list of supported timeframe intervals.
        
        CSV adapter supports the same timeframes as its provider.
        """
        # Handle both real providers and mocks
        supported = getattr(self._provider, 'supported_timeframes_property', None)
        if supported is None:
            supported = getattr(self._provider, 'supported_timeframes', None)
        if callable(supported):
            try:
                return supported()
            except Exception:
                return ["1M"]
        elif isinstance(supported, list):
            return supported
        return ["1M"]
    
    def get_origin_time(self) -> time:
        """Return the origin time for this adapter's market.
        
        CSV adapter delegates to its underlying provider for origin time.
        
        Returns:
            Origin time as datetime.time (09:15 for NSE).
        """
        from datetime import time
        return self._provider.get_origin_time()
    
    def read(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        """Read normalized OHLCV data from the CSV provider (base timeframe).
        
        Args:
            from_date: Optional start date for data filtering (ISO format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS").
                      If provided, overrides any date range configured in the underlying provider.
            to_date: Optional end date for data filtering (ISO format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS").
                    If provided, overrides any date range configured in the underlying provider.
        
        Returns:
            List of dictionaries with standardized keys:
            'datetime', 'open', 'high', 'low', 'close', 'volume'
            (and any additional mapped fields)
        """
        timeframes = self.supported_timeframes
        return self.read_timeframe(timeframes[0] if timeframes else "1M", from_date, to_date)
    
    def read_timeframe(
        self,
        timeframe: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        """Read normalized OHLCV data for a specific timeframe.
        
        If the timeframe is natively supported by the provider, returns
        the provider's native data. Otherwise, aggregates from 1-minute
        data (if available) to produce the requested timeframe.
        
        Args:
            timeframe: Timeframe interval (e.g., "1M", "1H", "1D").
            from_date: Optional start date for data filtering (ISO format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS").
                      If provided, overrides any date range configured in the underlying provider.
            to_date: Optional end date for data filtering (ISO format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS").
                    If provided, overrides any date range configured in the underlying provider.
            
        Returns:
            List of dictionaries with standardized keys for the given timeframe.
            
        Raises:
            ValueError: If the timeframe is not natively supported and
                1-minute data is unavailable for aggregation.
        """
        # Check if timeframe is natively supported
        native_timeframes = self.supported_timeframes
        
        if timeframe in native_timeframes:
            # Native support - use provider directly
            return self._read_native_timeframe(timeframe, from_date, to_date)
        
        # Not natively supported - try to aggregate from 1M
        if "1M" not in native_timeframes:
            raise ValueError(
                f"Timeframe '{timeframe}' not natively supported and 1-minute data "
                f"is unavailable for aggregation. Supported native timeframes: {native_timeframes}"
            )
        
        # Fetch 1M data and aggregate
        logger.debug("Aggregating timeframe %s from 1M data", timeframe)
        raw_1m = self._read_native_timeframe("1M", from_date, to_date)
        if not raw_1m:
            return []
        
        aggregated = self._aggregate_timeframe(raw_1m, timeframe)
        logger.debug("CSVDataAdapter: aggregated %d rows for timeframe %s from 1M", len(aggregated), timeframe)
        return aggregated
    
    def _read_native_timeframe(
        self,
        timeframe: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        """Read normalized data for a natively supported timeframe."""
        self._validate_mapping()
        
        # Fetch raw data from provider with timeframe
        raw_data = self._provider.fetch(timeframe=timeframe, from_date=from_date, to_date=to_date)
        
        if not raw_data:
            return []
        
        # Handle provider return format (with or without header)
        if self._provider.header is not None:
            # Provider has header - raw_data is (header, data_rows)
            header_row, data_rows = raw_data
            self._mode = "header"
            self._header_index = self._build_header_index(header_row)
        else:
            # Provider has no header - raw_data is list of rows
            data_rows = raw_data
            self._mode = self._detect_mode()
        
        results = []
        for line_num, row in enumerate(data_rows, start=1):
            try:
                extracted = self._extract_row_values(row)
                results.append(extracted)
            except (IndexError, KeyError, ValueError) as e:
                logger.warning("Skipping malformed row at line %d: %s", line_num, e)
                continue

        logger.debug("CSVDataAdapter: normalized %d rows for timeframe %s", len(results), timeframe)
        return results
    
    def _aggregate_timeframe(self, raw_1m: list[dict], target_timeframe: str) -> list[dict]:
        """Aggregate 1-minute OHLCV data to target timeframe.
        
        Args:
            raw_1m: List of normalized 1-minute OHLCV dicts (sorted by datetime).
            target_timeframe: Target timeframe string (e.g., "1H", "4H", "1D").
            
        Returns:
            List of aggregated OHLCV dicts for the target timeframe.
        """
        if not raw_1m:
            return []
        
        # Parse target timeframe to minutes
        interval_minutes = self._parse_timeframe_to_minutes(target_timeframe)
        if interval_minutes is None:
            raise ValueError(f"Invalid timeframe format: {target_timeframe}. Expected format like '1H', '4H', '1D'")
        
        if interval_minutes <= 1:
            # Target is 1M or smaller - return as-is (shouldn't happen since we check native first)
            return raw_1m
        
        # Group 1M candles into target timeframe buckets
        from datetime import datetime
        from collections import defaultdict
        
        buckets: dict[int, list[dict]] = defaultdict(list)
        
        for row in raw_1m:
            dt_str = row.get("datetime", "")
            try:
                dt = datetime.strptime(dt_str, self._datetime_format)
            except ValueError:
                logger.warning("Skipping row with invalid datetime: %s", dt_str)
                continue
            
            # Calculate bucket key (minutes since epoch, floored to interval)
            total_minutes = dt.hour * 60 + dt.minute + dt.day * 24 * 60
            # Add months/years approximately using day of year
            # For more accurate handling, use full timestamp
            bucket_key = (total_minutes // interval_minutes) * interval_minutes
            buckets[bucket_key].append(row)
        
        # Build aggregated candles
        aggregated = []
        for bucket_key in sorted(buckets.keys()):
            bucket_rows = buckets[bucket_key]
            if not bucket_rows:
                continue
            
            # OHLCV aggregation
            opens = [float(r["open"]) for r in bucket_rows]
            highs = [float(r["high"]) for r in bucket_rows]
            lows = [float(r["low"]) for r in bucket_rows]
            closes = [float(r["close"]) for r in bucket_rows]
            volumes = [float(r["volume"]) for r in bucket_rows]
            
            # Use first row's datetime as bucket start (open time)
            first_row = bucket_rows[0]
            
            aggregated.append({
                "datetime": first_row["datetime"],
                "open": opens[0],
                "high": max(highs),
                "low": min(lows),
                "close": closes[-1],
                "volume": sum(volumes),
            })
        
        return aggregated
    
    def _parse_timeframe_to_minutes(self, timeframe: str) -> int | None:
        """Parse timeframe string to minutes.
        
        Args:
            timeframe: Timeframe string like "1M", "5M", "1H", "4H", "1D", "1W".
            
        Returns:
            Number of minutes, or None if invalid format.
        """
        import re
        match = re.match(r'^(\d+)([MHDW])$', timeframe.upper())
        if not match:
            return None
        
        value = int(match.group(1))
        unit = match.group(2)
        
        if unit == 'M':
            return value
        elif unit == 'H':
            return value * 60
        elif unit == 'D':
            return value * 60 * 24
        elif unit == 'W':
            return value * 60 * 24 * 7
        return None
    
    def close(self) -> None:
        """Close the underlying provider."""
        self._provider.close()
    
    def _validate_mapping(self) -> None:
        """Validate column mapping configuration."""
        if not self._column_mapping:
            raise ValueError("column_mapping is required")
        
        missing_keys = [key for key in self.REQUIRED_KEYS if key not in self._column_mapping]
        if missing_keys:
            raise ValueError(f"column_mapping missing required keys: {missing_keys}")
        
        has_str = any(
            isinstance(v, str) or (isinstance(v, list) and v and isinstance(v[0], str))
            for v in self._column_mapping.values()
        )
        has_int = any(
            isinstance(v, int) or (isinstance(v, list) and v and isinstance(v[0], int))
            for v in self._column_mapping.values()
        )
        
        if has_str and has_int:
            raise ValueError("column_mapping cannot mix str (header) and int (index) modes")
        
        dt_spec = self._column_mapping.get("datetime")
        if dt_spec is not None:
            valid = (
                isinstance(dt_spec, int)
                or (isinstance(dt_spec, list) and all(isinstance(x, int) for x in dt_spec))
                or isinstance(dt_spec, str)
                or (isinstance(dt_spec, list) and all(isinstance(x, str) for x in dt_spec))
            )
            if not valid:
                raise ValueError("datetime mapping must be int, list[int], str, or list[str]")
    
    def _detect_mode(self) -> Literal["index", "header"]:
        """Detect whether mapping uses index or header mode."""
        for v in self._column_mapping.values():
            if isinstance(v, str):
                return "header"
            if isinstance(v, list) and v and isinstance(v[0], str):
                return "header"
        return "index"
    
    def _build_header_index(self, header_row: list[str]) -> dict[str, int]:
        """Build index mapping from header names to column indices."""
        header_index = {name: idx for idx, name in enumerate(header_row)}
        
        for key, spec in self._column_mapping.items():
            if isinstance(spec, str):
                if spec not in header_index:
                    raise ValueError(f"Header '{spec}' for field '{key}' not found in CSV header row")
            elif isinstance(spec, list) and spec and isinstance(spec[0], str):
                for name in spec:
                    if name not in header_index:
                        raise ValueError(f"Header '{name}' for field '{key}' not found in CSV header row")
        
        return header_index
    
    def _extract_row_values(self, row: list[str]) -> dict:
        """Extract and normalize values from a CSV row."""
        result = {}
        
        for key, spec in self._column_mapping.items():
            if isinstance(spec, int):
                if spec >= len(row):
                    raise IndexError(f"Column index {spec} out of bounds for row with {len(row)} columns")
                result[key] = row[spec]
            elif isinstance(spec, list) and spec and isinstance(spec[0], int):
                values = []
                for idx in spec:
                    if idx >= len(row):
                        raise IndexError(f"Column index {idx} out of bounds for row with {len(row)} columns")
                    values.append(row[idx])
                result[key] = " ".join(values)
            elif isinstance(spec, str):
                if self._header_index is None:
                    raise ValueError("header_index required for header mode")
                if spec not in self._header_index:
                    raise KeyError(f"Header '{spec}' not in header_index")
                result[key] = row[self._header_index[spec]]
            elif isinstance(spec, list) and spec and isinstance(spec[0], str):
                if self._header_index is None:
                    raise ValueError("header_index required for header mode")
                values = []
                for name in spec:
                    if name not in self._header_index:
                        raise KeyError(f"Header '{name}' not in header_index")
                    values.append(row[self._header_index[name]])
                result[key] = " ".join(values)
            else:
                raise ValueError(f"Invalid mapping spec for '{key}': {spec}")
        
        return result