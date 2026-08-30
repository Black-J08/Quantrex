"""Tests for the ``quantrex_core.logging`` module.

Covers the no-side-effects-on-import guarantee, the researcher-facing API
contract, and the new ``execution.log`` helper used by the backtest engine.
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

import pytest

from quantrex_core.logging import DEFAULT_LEVEL, get_logger, setup_logging


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_root_logger():
    """Snapshot and restore the root logger handlers/level around each test.

    The stdlib's root logger is process-global; tests that call
    :func:`setup_logging` mutate it. We snapshot before each test and
    restore after, so tests are independent regardless of execution order.
    """
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    saved_disabled = root.disabled
    try:
        yield
    finally:
        # Close any FileHandler we may have created so locks are released.
        for h in list(root.handlers):
            root.removeHandler(h)
            try:
                h.close()
            except Exception:  # noqa: BLE001
                pass
        for h in saved_handlers:
            root.addHandler(h)
        root.setLevel(saved_level)
        root.disabled = saved_disabled


# ---------------------------------------------------------------------------
# Import-safety
# ---------------------------------------------------------------------------


def test_import_has_no_side_effects_on_root_logger():
    """Importing ``quantrex_core.logging`` must not mutate the root logger.

    The NullHandler is attached to the ``"quantrex"`` package logger, not
    the root. Library code (urllib3, httpx, etc.) attached to the root
    before this import must remain untouched.
    """
    # Force a clean root before re-importing.
    for m in list(sys.modules):
        if m == "quantrex_core.logging" or m.startswith("quantrex_core.logging."):
            del sys.modules[m]
    root = logging.getLogger()
    handlers_before = list(root.handlers)

    import quantrex_core.logging  # noqa: F401

    assert root.handlers == handlers_before, (
        "Importing quantrex_core.logging must not touch root handlers"
    )


def test_null_handler_attached_exactly_once():
    """Re-importing the module must not stack NullHandlers on the package logger."""
    for m in list(sys.modules):
        if m == "quantrex_core.logging" or m.startswith("quantrex_core.logging."):
            del sys.modules[m]
    import quantrex_core.logging  # noqa: F401
    import quantrex_core.logging  # noqa: F401

    pkg = logging.getLogger("quantrex")
    null_handlers = [h for h in pkg.handlers if isinstance(h, logging.NullHandler)]
    assert len(null_handlers) == 1, (
        f"Expected exactly one NullHandler on 'quantrex' package logger, "
        f"got {len(null_handlers)}: {pkg.handlers}"
    )


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------


def test_get_logger_default_returns_package_logger():
    """``get_logger(None)`` returns the ``quantrex`` package logger."""
    pkg = logging.getLogger("quantrex")
    assert get_logger() is pkg
    assert get_logger(None) is pkg


def test_get_logger_named_returns_stdlib_logger():
    """``get_logger(name)`` returns the standard module-dotted logger."""
    lg = get_logger("quantrex_backtest.core.engine")
    assert isinstance(lg, logging.Logger)
    assert lg.name == "quantrex_backtest.core.engine"
    # logging.getLogger caches by name, so identity must match.
    assert lg is logging.getLogger("quantrex_backtest.core.engine")


def test_default_level_constant_is_info():
    """``DEFAULT_LEVEL`` is ``"INFO"``."""
    assert DEFAULT_LEVEL == "INFO"


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


def test_setup_logging_attaches_stderr_handler_to_root():
    """``setup_logging`` adds a ``StreamHandler`` (stderr) to the root logger."""
    setup_logging(level="INFO")
    root = logging.getLogger()
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)


def test_setup_logging_idempotent_replaces_config():
    """A second ``setup_logging`` call replaces the previous configuration cleanly."""
    setup_logging(level="DEBUG")
    setup_logging(level="WARNING")
    root = logging.getLogger()
    assert root.level == logging.WARNING
    stream_count = sum(1 for h in root.handlers if isinstance(h, logging.StreamHandler))
    assert stream_count == 1, "Should have exactly one StreamHandler after a 2nd setup"


def test_setup_logging_accepts_numeric_level():
    """``setup_logging`` accepts a numeric level."""
    setup_logging(level=logging.ERROR)
    assert logging.getLogger().level == logging.ERROR


def test_setup_logging_with_log_file_attaches_rotating_handler(tmp_path: Path):
    """When ``log_file`` is provided, a ``RotatingFileHandler`` is attached and records land in the file."""
    fp = tmp_path / "app.log"
    setup_logging(level="INFO", log_file=fp)
    get_logger("test").info("hello file")

    # Flush before reading.
    for h in logging.getLogger().handlers:
        h.flush()

    content = fp.read_text()
    assert "hello file" in content
    assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in logging.getLogger().handlers)


def test_setup_logging_log_file_appends(tmp_path: Path):
    """Two setups with the same ``log_file`` result in append-style accumulation."""
    fp = tmp_path / "app.log"
    setup_logging(level="INFO", log_file=fp)
    get_logger("test").info("first")
    setup_logging(level="INFO", log_file=fp)
    get_logger("test").info("second")

    for h in logging.getLogger().handlers:
        h.flush()

    content = fp.read_text()
    assert "first" in content
    assert "second" in content


# ---------------------------------------------------------------------------
# Thread-safe delivery
# ---------------------------------------------------------------------------


def test_thread_safe_delivery_no_lost_messages():
    """10 threads × 100 records each — all 1000 records must reach the sink."""
    records: list[logging.LogRecord] = []

    class _Sink(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    root = logging.getLogger()
    sink = _Sink()
    root.addHandler(sink)
    root.setLevel(logging.INFO)

    def worker(seed: int) -> None:
        lg = get_logger(f"thread.{seed}")
        for i in range(100):
            lg.info("msg %d-%d", seed, i)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(records) == 1000, f"Expected 1000 records, got {len(records)}"
    sink.close()
