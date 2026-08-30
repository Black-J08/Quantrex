"""Regression tests for the loguru-to-stdlib-logging migration.

These tests pin the log lines emitted by each migrated module so future
refactors don't silently drop or reword them. They use ``caplog`` to
capture records at the level set on the relevant logger (DEBUG/INFO/...).
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import pytest

from quantrex_data.providers.csv_provider import CSVDataProvider
from quantrex_data.adapters.csv_adapter import CSVDataAdapter
from quantrex_test_support.csv import csv_rows_to_string, create_temp_csv


# ---------------------------------------------------------------------------
# csv_provider
# ---------------------------------------------------------------------------


def test_csv_provider_warns_on_empty_file(caplog: pytest.LogCaptureFixture, tmp_path: Path):
    """``CSVDataProvider`` emits a ``warning`` when reading an empty file."""
    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("")

    provider = CSVDataProvider(str(empty_file), has_header=False)
    with caplog.at_level(logging.WARNING, logger="quantrex_data.providers.csv_provider.provider"):
        result = provider.fetch()
    assert result == []
    assert any(
        "CSV file is empty" in rec.getMessage() and rec.levelno == logging.WARNING
        for rec in caplog.records
    ), f"Expected 'CSV file is empty' warning, got {[r.getMessage() for r in caplog.records]}"


def test_csv_provider_debug_on_read(caplog: pytest.LogCaptureFixture, tmp_path: Path):
    """``CSVDataProvider`` emits a ``debug`` line on a successful read."""
    rows = [["20230620", "19:00", "100.00", "101.00", "99.00", "100.50", "1"]]
    csv_content = csv_rows_to_string(rows)
    with create_temp_csv(csv_content) as temp_path:
        provider = CSVDataProvider(temp_path, has_header=False)
        with caplog.at_level(logging.DEBUG, logger="quantrex_data.providers.csv_provider.provider"):
            provider.fetch()
    debug_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("Reading CSV file" in m for m in debug_messages), (
        f"Expected 'Reading CSV file' debug line, got {debug_messages}"
    )


# ---------------------------------------------------------------------------
# csv_adapter
# ---------------------------------------------------------------------------


def test_csv_adapter_warns_on_malformed_row(caplog: pytest.LogCaptureFixture, tmp_path: Path):
    """``CSVDataAdapter`` emits a ``warning`` per malformed row, then ``debug`` on completion."""
    # Write a CSV with one good row and one short row that will fail extraction.
    csv_content = "20230620,19:00,100.00,101.00,99.00,100.50,1\n20230621\n"
    with create_temp_csv(csv_content) as temp_path:
        provider = CSVDataProvider(temp_path, has_header=False)
        adapter = CSVDataAdapter(
            provider,
            column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            },
        )
        with caplog.at_level(logging.DEBUG, logger="quantrex_data.adapters.csv_adapter"):
            adapter.read()

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    debugs = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("Skipping malformed row" in m for m in warnings), (
        f"Expected 'Skipping malformed row' warning, got {warnings}"
    )
    assert any("normalized 1 rows" in m for m in debugs), (
        f"Expected 'normalized 1 rows' debug line, got {debugs}"
    )


# ---------------------------------------------------------------------------
# engine (in backtest package, but tested here for log-level coverage of
# the framework's most visible log line). Placed here to keep the
# regression suite in one place; we import the engine from the backtest
# package, which is a hard dependency of data via examples.
# ---------------------------------------------------------------------------


def test_csv_adapter_debug_line_format_includes_row_count(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
):
    """Pin the exact row-count message format so accidental rewording breaks loudly."""
    rows = [["20230620", "19:00", "100.00", "101.00", "99.00", "100.50", "1"]]
    csv_content = csv_rows_to_string(rows)
    with create_temp_csv(csv_content) as temp_path:
        provider = CSVDataProvider(temp_path, has_header=False)
        adapter = CSVDataAdapter(
            provider,
            column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            },
        )
        with caplog.at_level(logging.DEBUG, logger="quantrex_data.adapters.csv_adapter"):
            adapter.read()

    # The success-line format we committed to:
    # "CSVDataAdapter: normalized %d rows" -> "CSVDataAdapter: normalized 1 rows"
    debugs = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert "CSVDataAdapter: normalized 1 rows" in debugs, (
        f"Expected exact 'CSVDataAdapter: normalized 1 rows' line, got {debugs}"
    )
