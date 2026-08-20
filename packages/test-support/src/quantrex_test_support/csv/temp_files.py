"""Temporary file helpers for testing."""

import contextlib
import os
import tempfile
from typing import Generator


@contextlib.contextmanager
def create_temp_csv(content: str) -> Generator[str, None, None]:
    """Context manager to create a temporary CSV file with given content.

    Args:
        content: CSV content to write to the temporary file

    Yields:
        Path to the temporary CSV file

    Example:
        with create_temp_csv("date,time,open,high,low,close,volume\n20230620,19:00,737.20,737.20,737.20,737.20,1") as path:
            from quantrex_data.providers.csv_provider import CSVDataProvider
            from quantrex_data.adapters.csv_adapter import CSVDataAdapter
            provider = CSVDataProvider(path, has_header=True)
            adapter = CSVDataAdapter(provider, mapping={...})
            results = adapter.read()
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(content)
        temp_path = f.name
    try:
        yield temp_path
    finally:
        # File may have been deleted externally; ignore if missing
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass


__all__ = ["create_temp_csv"]