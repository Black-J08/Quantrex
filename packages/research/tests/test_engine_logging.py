"""Regression tests for research candle-aware logging.

Verifies that ResearchEngine emits a per-bar audit line containing the
candle's backtest timestamp and full OHLCV values without requiring any
code changes from the researcher.

Lives in a separate module so it can be collected and run independently
of any pre-existing collection issues in sibling test files.
"""

import logging
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from quantrex_core.models import Candle
from quantrex_core.protocols import DataAdapter

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig
from quantrex_backtest import InstrumentSpec, BacktestConfig

# Logger name used by the research engine; the per-bar audit
# log line is emitted on this logger.
_ENGINE_LOGGER = "quantrex_research.core.engine"


class _LoggingProbeComponent(ForwardReturnComponent):
    """Minimal component: record candles for sanity, do nothing else."""

    def __init__(self, config):
        super().__init__(config)
        self.candles: list[Candle] = []

    def on_candle(self, candle: Candle) -> None:
        self.candles.append(candle)


def _mock_adapter(rows: list[dict]) -> Mock:
    adapter = Mock(spec=DataAdapter)
    adapter.read_timeframe.return_value = rows
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    return adapter


def test_engine_logs_ohlc_per_candle_to_logger(caplog: pytest.LogCaptureFixture) -> None:
    """Each candle must produce one log record on the engine logger
    containing the backtest/candle timestamp and full OHLCV values.
    """
    caplog.set_level(logging.INFO, logger=_ENGINE_LOGGER)

    adapter = _mock_adapter([
        {
            "datetime": "2023-06-20 09:15:00",
            "open": "100.5",
            "high": "101.25",
            "low": "99.75",
            "close": "100.75",
            "volume": "42",
        },
        {
            "datetime": "2023-06-20 09:16:00",
            "open": "100.75",
            "high": "102.0",
            "low": "100.5",
            "close": "101.5",
            "volume": "17",
        },
    ])

    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = _LoggingProbeComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="COPPER", adapter=adapter)],
        [component],
        data_start="2023-06-20",
        data_end="2023-06-21",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
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

    # Candle 1: 2023-06-20 09:15 — verify every OHLCV field appears
    # in a single record tagged with the symbol and candle timestamp.
    msg1 = audit_records[0].getMessage()
    assert "[COPPER 2023-06-20T09:15:00]" in msg1
    assert "O=100.5" in msg1
    assert "H=101.25" in msg1
    assert "L=99.75" in msg1
    assert "C=100.75" in msg1
    assert "V=42" in msg1

    # Candle 2: 2023-06-20 09:16 — distinct values prove the line is
    # emitted per bar.
    msg2 = audit_records[1].getMessage()
    assert "[COPPER 2023-06-20T09:16:00]" in msg2
    assert "O=100.75" in msg2
    assert "H=102.0" in msg2
    assert "L=100.5" in msg2
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
            "datetime": "2023-01-01 09:30:00",
            "open": "1",
            "high": "2",
            "low": "0.5",
            "close": "1.5",
            "volume": "7",
        },
    ])

    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = _LoggingProbeComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="COPPER", adapter=adapter)],
        [component],
        data_start="2023-01-01",
        data_end="2023-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
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


def test_engine_creates_execution_log_files(tmp_path: Path) -> None:
    """ResearchEngine should create execution_log directory with symbol-specific
    and portfolio log files.
    """
    adapter = _mock_adapter([
        {
            "datetime": "2023-06-20 09:15:00",
            "open": "100.5",
            "high": "101.25",
            "low": "99.75",
            "close": "100.75",
            "volume": "42",
        },
    ])

    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = _LoggingProbeComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="COPPER", adapter=adapter)],
        [component],
        data_start="2023-06-20",
        data_end="2023-06-21",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    engine.run()

    # Find the output directory
    output_base = Path("output/research")
    component_dirs = list(output_base.glob("_LoggingProbeComponent/*"))
    assert len(component_dirs) >= 1, "Expected at least one run directory"
    
    # Get the most recent run directory
    latest_run_dir = max(component_dirs, key=lambda d: d.stat().st_mtime)
    exec_log_dir = latest_run_dir / "execution_log"
    
    assert exec_log_dir.exists(), f"execution_log directory not found at {exec_log_dir}"
    
    # Check for symbol-specific log file
    symbol_log = exec_log_dir / "COPPER_execution.log"
    assert symbol_log.exists(), f"Symbol log file not found at {symbol_log}"
    
    # Check for portfolio log file
    portfolio_log = exec_log_dir / "portfolio_execution.log"
    assert portfolio_log.exists(), f"Portfolio log file not found at {portfolio_log}"
    
    # Verify content of symbol log
    symbol_log_content = symbol_log.read_text()
    assert "[COPPER 2023-06-20T09:15:00]" in symbol_log_content
    assert "O=100.5" in symbol_log_content
    assert "H=101.25" in symbol_log_content
    assert "L=99.75" in symbol_log_content
    assert "C=100.75" in symbol_log_content
    assert "V=42" in symbol_log_content
    
    # Verify content of portfolio log (should have general messages but NOT per-candle audit lines)
    portfolio_log_content = portfolio_log.read_text()
    assert "Loading data via DataOrchestrator" in portfolio_log_content
    assert "ResearchEngine completed" in portfolio_log_content
    # Per-candle audit lines go to symbol-specific logs only
    assert "[COPPER 2023-06-20T09:15:00]" not in portfolio_log_content


def test_engine_log_format_matches_standard(caplog: pytest.LogCaptureFixture) -> None:
    """Log format should match the standard format: timestamp | level | name | message"""
    caplog.set_level(logging.INFO, logger=_ENGINE_LOGGER)

    adapter = _mock_adapter([
        {
            "datetime": "2023-06-20 09:15:00",
            "open": "100.5",
            "high": "101.25",
            "low": "99.75",
            "close": "100.75",
            "volume": "42",
        },
    ])

    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = _LoggingProbeComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="COPPER", adapter=adapter)],
        [component],
        data_start="2023-06-20",
        data_end="2023-06-21",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    engine.run()

    audit_records = [
        r for r in caplog.records
        if r.name == _ENGINE_LOGGER
        and "[COPPER " in r.getMessage()
        and " O=" in r.getMessage()
    ]
    assert len(audit_records) == 1
    
    record = audit_records[0]
    # Check that the log record has the expected format components
    # The format is: %(asctime)s | %(levelname)-8s | %(name)s | %(message)s
    formatted = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s").format(record)
    
    # Verify format structure
    assert " | INFO     | quantrex_research.core.engine | " in formatted
    assert "[COPPER 2023-06-20T09:15:00]" in formatted


def test_engine_multi_symbol_log_routing(caplog: pytest.LogCaptureFixture) -> None:
    """Messages with [SYMBOL ...] should route to symbol-specific log files."""
    caplog.set_level(logging.INFO, logger=_ENGINE_LOGGER)

    adapter1 = _mock_adapter([
        {
            "datetime": "2023-06-20 09:15:00",
            "open": "100.5",
            "high": "101.25",
            "low": "99.75",
            "close": "100.75",
            "volume": "42",
        },
    ])
    adapter2 = _mock_adapter([
        {
            "datetime": "2023-06-20 09:15:00",
            "open": "200.0",
            "high": "201.0",
            "low": "199.0",
            "close": "200.5",
            "volume": "100",
        },
    ])

    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = _LoggingProbeComponent(config)
    engine = ResearchEngine(
        [
            InstrumentSpec(symbol="COPPER", adapter=adapter1),
            InstrumentSpec(symbol="SILVER", adapter=adapter2),
        ],
        [component],
        data_start="2023-06-20",
        data_end="2023-06-21",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    engine.run()

    # Find the output directory
    output_base = Path("output/research")
    component_dirs = list(output_base.glob("_LoggingProbeComponent/*"))
    assert len(component_dirs) >= 1
    
    latest_run_dir = max(component_dirs, key=lambda d: d.stat().st_mtime)
    exec_log_dir = latest_run_dir / "execution_log"
    
    # Check both symbol log files exist
    copper_log = exec_log_dir / "COPPER_execution.log"
    silver_log = exec_log_dir / "SILVER_execution.log"
    portfolio_log = exec_log_dir / "portfolio_execution.log"
    
    assert copper_log.exists(), "COPPER log file not found"
    assert silver_log.exists(), "SILVER log file not found"
    assert portfolio_log.exists(), "Portfolio log file not found"
    
    # Verify COPPER log has COPPER messages
    copper_content = copper_log.read_text()
    assert "[COPPER 2023-06-20T09:15:00]" in copper_content
    assert "[SILVER" not in copper_content  # SILVER messages should not be in COPPER log
    
    # Verify SILVER log has SILVER messages
    silver_content = silver_log.read_text()
    assert "[SILVER 2023-06-20T09:15:00]" in silver_content
    assert "[COPPER" not in silver_content  # COPPER messages should not be in SILVER log
    
    # Verify portfolio log has general messages but NOT per-candle audit lines
    portfolio_content = portfolio_log.read_text()
    assert "Loading data via DataOrchestrator" in portfolio_content
    assert "ResearchEngine completed" in portfolio_content
    # Per-candle audit lines go to symbol-specific logs only
    assert "[COPPER 2023-06-20T09:15:00]" not in portfolio_content
    assert "[SILVER 2023-06-20T09:15:00]" not in portfolio_content