"""CSV Data Adapter for Quantrex framework.

Normalizes raw CSV data from CSVDataProvider into standardized OHLCV format
for the Backtest Engine.
"""

from typing import Literal
from loguru import logger

from quantrex_core.protocols import DataProvider, DataAdapter
from quantrex_data.providers.csv_provider import CSVDataProvider


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
    
    def read(self) -> list[dict]:
        """Read normalized OHLCV data from the CSV provider.
        
        Returns:
            List of dictionaries with standardized keys:
            'datetime', 'open', 'high', 'low', 'close', 'volume'
            (and any additional mapped fields)
        """
        self._validate_mapping()
        
        # Fetch raw data from provider
        raw_data = self._provider.fetch()
        
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
                logger.warning("Skipping malformed row at line {}: {}", line_num, e)
                continue
        
        logger.debug("CSVDataAdapter: normalized {} rows", len(results))
        return results
    
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