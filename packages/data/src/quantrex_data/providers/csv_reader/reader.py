import csv
from typing import Literal
from loguru import logger


class CSVReader:
    REQUIRED_KEYS = ("datetime", "open", "high", "low", "close", "volume")

    def __init__(self, file_path: str, column_mapping: dict):
        self.file_path = file_path
        self.column_mapping = column_mapping
        self._mode: Literal["index", "header"] | None = None
        
        self.read()  # Automatically read the CSV file upon initialization

    def read(self) -> list[dict]:
        self._validate_mapping()
        self._mode = self._detect_mode()

        results = []
        with open(self.file_path, "r", newline="") as file:
            reader = csv.reader(file)
            rows = list(reader)

        if not rows:
            return results

        header_index = None
        start_row = 0

        if self._mode == "header":
            header_row = rows[0]
            header_index = self._build_header_index(header_row)
            start_row = 1

        for line_num, row in enumerate(rows[start_row:], start=start_row + 1):
            try:
                extracted = self._extract_row_values(row, header_index)
                results.append(extracted)
            except (IndexError, KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed row at line: {line_num}\n{e}")
                continue

        return results

    def _validate_mapping(self) -> None:
        if not self.column_mapping:
            raise ValueError("column_mapping is required")

        missing_keys = [key for key in self.REQUIRED_KEYS if key not in self.column_mapping]
        if missing_keys:
            raise ValueError(f"column_mapping missing required keys: {missing_keys}")

        has_str = any(
            isinstance(v, str) or (isinstance(v, list) and v and isinstance(v[0], str))
            for v in self.column_mapping.values()
        )
        has_int = any(
            isinstance(v, int) or (isinstance(v, list) and v and isinstance(v[0], int))
            for v in self.column_mapping.values()
        )

        if has_str and has_int:
            raise ValueError("column_mapping cannot mix str (header) and int (index) modes")

        dt_spec = self.column_mapping.get("datetime")
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
        for v in self.column_mapping.values():
            if isinstance(v, str):
                return "header"
            if isinstance(v, list) and v and isinstance(v[0], str):
                return "header"
        return "index"

    def _build_header_index(self, header_row: list[str]) -> dict[str, int]:
        header_index = {name: idx for idx, name in enumerate(header_row)}

        for key, spec in self.column_mapping.items():
            if isinstance(spec, str):
                if spec not in header_index:
                    raise ValueError(f"Header '{spec}' for field '{key}' not found in CSV header row")
            elif isinstance(spec, list) and spec and isinstance(spec[0], str):
                for name in spec:
                    if name not in header_index:
                        raise ValueError(f"Header '{name}' for field '{key}' not found in CSV header row")

        return header_index

    def _extract_row_values(self, row: list[str], header_index: dict[str, int] | None) -> dict:
        result = {}

        for key, spec in self.column_mapping.items():
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
                if header_index is None:
                    raise ValueError("header_index required for header mode")
                if spec not in header_index:
                    raise KeyError(f"Header '{spec}' not in header_index")
                result[key] = row[header_index[spec]]
            elif isinstance(spec, list) and spec and isinstance(spec[0], str):
                if header_index is None:
                    raise ValueError("header_index required for header mode")
                values = []
                for name in spec:
                    if name not in header_index:
                        raise KeyError(f"Header '{name}' not in header_index")
                    values.append(row[header_index[name]])
                result[key] = " ".join(values)
            else:
                raise ValueError(f"Invalid mapping spec for '{key}': {spec}")

        return result