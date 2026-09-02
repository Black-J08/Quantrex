"""Regression tests for backtest candle-aware logging.

Verifies that BacktestEngine emits a per-bar audit line containing the
candle's backtest timestamp and full OHLCV values without requiring any
code changes from the researcher.

Lives in a separate module so it can be collected and run independently
of any pre-existing collection issues in sibling test files.
"""

import logging
from unittest.mock import Mock

import pytest

from quantrex_core.models import Candle
from quantrex_core.protocols import DataAdapter
from quantrex_core.strategy.base import Strategy
from quantrex_backtest import BacktestEngine

# Logger name used by the backtest engine module; the per-bar audit
# log line is emitted on this logger.
_ENGINE_LOGGER = "quantrex_backtest.core.engine"


class _LoggingProbeStrategy(Strategy):
    """Minimal strategy: record candles for sanity, do nothing else."""

    def __init__(self) -> None:
        super().__init__()
        self.candles: list[Candle] = []

    def on_candle(self, candle: Candle) -> None:
        self.candles.append(candle)


def _mock_adapter(rows: list[dict]) -> Mock:
    adapter = Mock(spec=DataAdapter)
    adapter.read.return_value = rows
    adapter.datetime_format = "%Y%m%d %H:%M"
    return adapter


def test_engine_logs_ohlc_per_candle_to_logger(caplog: pytest.LogCaptureFixture) -> None:
    """Each candle must produce one log record on the engine logger
    containing the backtest/candle timestamp and full OHLCV values.
    """
    caplog.set_level(logging.INFO, logger=_ENGINE_LOGGER)

    adapter = _mock_adapter([
        {
            "datetime": "20230620 19:00",
            "open": "100.5",
            "high": "101.25",
            "low": "99.75",
            "close": "100.75",
            "volume": "42",
        },
        {
            "datetime": "20230620 19:01",
            "open": "100.75",
            "high": "102.0",
            "low": "100.5",
            "close": "101.5",
            "volume": "17",
        },
    ])

    strategy = _LoggingProbeStrategy()
    engine = BacktestEngine(adapter, strategy, symbol="COPPER")
    engine.run()

    # Pick the audit lines from the captured engine-logger records.
    audit_records = [
        r for r in caplog.records
        if r.name == _ENGINE_LOGGER
        and "[COPPER " in r.getMessage()
        and " O=" in r.getMessage()
    ]
    assert len(audit_records) == 2, (
        f"expected exactly 2 per-bar audit records, got {len(audit_records)}: "
        f"{[r.getMessage() for r in audit_records]!r}"
    )

    # Candle 1: 2023-06-20 19:00 — verify every OHLCV field appears
    # in a single record tagged with the symbol and candle timestamp.
    msg1 = audit_records[0].getMessage()
    assert "[COPPER 2023-06-20T19:00:00]" in msg1
    assert "O=100.5" in msg1
    assert "H=101.25" in msg1
    assert "L=99.75" in msg1
    assert "C=100.75" in msg1
    assert "V=42" in msg1

    # Candle 2: 2023-06-20 19:01 — distinct values prove the line is
    # emitted per bar.
    msg2 = audit_records[1].getMessage()
    assert "[COPPER 2023-06-20T19:01:00]" in msg2
    assert "O=100.75" in msg2
    assert "H=102.0" in msg2
    assert "C=101.5" in msg2
    assert "V=17" in msg2


def test_engine_log_uses_candle_timestamp_not_wall_clock(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The audit line must reference the candle's bar timestamp, not the
    wall-clock time of the backtest run.
    """
    caplog.set_level(logging.INFO, logger=_ENGINE_LOGGER)

    adapter = _mock_adapter([
        {
            "datetime": "20230101 09:30",
            "open": "1",
            "high": "2",
            "low": "0.5",
            "close": "1.5",
            "volume": "7",
        },
    ])

    strategy = _LoggingProbeStrategy()
    engine = BacktestEngine(adapter, strategy, symbol="COPPER")
    engine.run()

    audit_records = [
        r for r in caplog.records
        if r.name == _ENGINE_LOGGER
        and "[COPPER " in r.getMessage()
        and " O=" in r.getMessage()
    ]
    assert len(audit_records) == 1
    msg = audit_records[0].getMessage()

    # The candle timestamp (2023) must appear verbatim — confirms the
    # audit line uses the backtest/candle timestamp, not wall clock.
    assert "2023-01-01T09:30:00" in msg
    # Sanity: the OHLCV fields are present.
    assert "O=1.0" in msg
    assert "H=2.0" in msg
    assert "L=0.5" in msg
    assert "C=1.5" in msg
    assert "V=7.0" in msg
