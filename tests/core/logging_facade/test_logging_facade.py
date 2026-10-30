"""Tests for the logging facade."""

from __future__ import annotations

import io
import logging

import pytest

from quantrex.core.logging import configure, get_logger


@pytest.fixture(autouse=True)
def reset_logging() -> None:
    """Reset logging state before each test for isolation."""
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)
    from quantrex.core.logging import _config

    _config.configured = False
    yield


class TestLoggingConfigure:
    """Tests for logging.configure()."""

    def test_configure_is_idempotent(self) -> None:
        """Calling configure() multiple times should only configure once."""
        stream = io.StringIO()
        configure(level=logging.DEBUG, format_string="%(levelname)s:%(name)s:%(message)s", stream=stream)
        logger1 = logging.getLogger("quantrex.test.idempotent")
        logger1.debug("first configure")

        stream2 = io.StringIO()
        configure(level=logging.WARNING, format_string="%(message)s", stream=stream2)
        # Second configure should be a no-op - first stream still gets output
        logger1.debug("second configure should not appear on first stream")
        output = stream.getvalue()
        assert "first configure" in output
        assert "second configure should not appear" in output

    def test_configure_sets_level(self) -> None:
        """configure() sets the root logger level."""
        stream = io.StringIO()
        configure(level=logging.DEBUG, stream=stream)
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_configure_sets_format(self) -> None:
        """configure() sets the formatter on the handler."""
        stream = io.StringIO()
        configure(level=logging.DEBUG, format_string="CUSTOM:%(message)s", stream=stream)
        logger = logging.getLogger("quantrex.test.format")
        logger.info("hello")
        output = stream.getvalue()
        assert "CUSTOM:hello" in output


class TestLoggingGetLogger:
    """Tests for logging.get_logger()."""

    def test_get_logger_returns_logger(self) -> None:
        """get_logger() returns a logging.Logger instance."""
        logger = get_logger("quantrex.test.get_logger")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "quantrex.test.get_logger"

    def test_get_logger_uses_lazy_formatting(self) -> None:
        """get_logger() returns a logger that supports lazy %-formatting."""
        stream = io.StringIO()
        configure(level=logging.DEBUG, stream=stream)
        logger = get_logger("quantrex.test.lazy")
        logger.info("value %s", 42)
        output = stream.getvalue()
        assert "value 42" in output

    def test_get_logger_exception_logs_traceback(self) -> None:
        """get_logger() logger.exception() logs the full traceback."""
        stream = io.StringIO()
        configure(level=logging.DEBUG, stream=stream)
        logger = get_logger("quantrex.test.exception")
        try:
            raise ValueError("test error")
        except ValueError:
            logger.exception("failed with %s", "error")
        output = stream.getvalue()
        assert "ValueError" in output
        assert "test error" in output
