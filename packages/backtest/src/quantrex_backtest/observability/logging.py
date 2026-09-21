"""Run logging for Quantrex Backtest."""

import logging
import os
from pathlib import Path
from typing import List, Optional

from quantrex_core.logging import get_logger

logger = get_logger(__name__)

_RUN_LOG_FILENAME = "execution.log"
_EXECUTION_LOG_DIR = "execution_log"

# Sentinel attribute on handlers we attach ourselves
_QUANTREX_RUN_HANDLER = "_quantrex_run_log_handler"


class _SymbolRoutingHandler(logging.Handler):
    """Custom logging handler that routes messages to symbol-specific log files.

    Messages containing a symbol in brackets (e.g., "[RELIANCE ...]") are routed
    to {SYMBOL}_execution.log. Messages without a symbol go to portfolio_execution.log.
    """

    def __init__(self, exec_log_dir: Path, symbols: List[str]):
        super().__init__()
        self._exec_log_dir = exec_log_dir
        self._symbols = symbols
        self._handlers: dict[str, logging.FileHandler] = {}
        self._portfolio_handler: Optional[logging.FileHandler] = None
        self._create_handlers()

    def _create_handlers(self) -> None:
        """Create file handlers for each symbol and portfolio."""
        # Create portfolio handler
        portfolio_path = self._exec_log_dir / "portfolio_execution.log"
        self._portfolio_handler = logging.FileHandler(portfolio_path, mode="a", encoding="utf-8")
        self._portfolio_handler.setLevel(logging.INFO)
        self._portfolio_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
        )

        # Create symbol-specific handlers
        for symbol in self._symbols:
            symbol_path = self._exec_log_dir / f"{symbol}_execution.log"
            handler = logging.FileHandler(symbol_path, mode="a", encoding="utf-8")
            handler.setLevel(logging.INFO)
            handler.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
            )
            self._handlers[symbol] = handler

    def rebind(self, exec_log_dir: Path, symbols: List[str]) -> None:
        """Rebind handlers to a new directory."""
        # Close existing handlers
        if self._portfolio_handler:
            self._portfolio_handler.close()
        for handler in self._handlers.values():
            handler.close()

        self._exec_log_dir = exec_log_dir
        self._symbols = symbols
        self._handlers = {}
        self._portfolio_handler = None
        self._create_handlers()

    def _get_symbol_from_message(self, message: str) -> Optional[str]:
        """Extract symbol from log message if present.

        Looks for pattern: [SYMBOL ...] at the start of the message.
        """
        if message.startswith('['):
            end_bracket = message.find(']')
            if end_bracket > 1:
                potential_symbol = message[1:end_bracket].strip()
                parts = potential_symbol.split()
                if parts and parts[0] in self._symbols:
                    return parts[0]
        return None

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a record to the appropriate symbol-specific log file."""
        try:
            raw_message = record.getMessage()
            symbol = self._get_symbol_from_message(raw_message)

            if symbol and symbol in self._handlers:
                self._handlers[symbol].emit(record)
            elif self._portfolio_handler:
                self._portfolio_handler.emit(record)
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """Close all handlers."""
        if self._portfolio_handler:
            self._portfolio_handler.close()
        for handler in self._handlers.values():
            handler.close()
        super().close()


class RunLogger:
    """Manages per-run logging for backtest execution.

    Handles log handler attachment, rebinding, and directory management.
    """

    def __init__(self):
        self._handler: Optional[_SymbolRoutingHandler] = None

    def ensure_run_log_file(self, run_dir: Path, symbols: List[str]) -> None:
        """Attach per-symbol execution log FileHandlers to the root logger.

        Creates an ``execution_log/`` subdirectory with ``{SYMBOL}_execution.log``
        files for each symbol. Also creates a ``portfolio_execution.log`` for
        general portfolio-level messages.

        Behaviour:
        * If a previous engine run already attached *our* handler, rebind
          it to the current ``run_dir`` so per-bar log lines land in the
          right ``execution.log`` (the staging-to-final promotion path
          relies on this).
        * If a researcher-installed ``FileHandler`` is present and we
          haven't attached one ourselves, leave the root logger untouched
          so the researcher's logging configuration wins.
        """
        root = logging.getLogger()

        # Create execution_log subdirectory
        exec_log_dir = run_dir / _EXECUTION_LOG_DIR
        exec_log_dir.mkdir(parents=True, exist_ok=True)

        # Case 1: we attached a handler in an earlier engine.run() — rebind
        # it to the current run directory and stop.
        for h in root.handlers:
            if getattr(h, _QUANTREX_RUN_HANDLER, False):
                if isinstance(h, _SymbolRoutingHandler):
                    h.rebind(exec_log_dir, symbols)
                    self._handler = h
                    return

        # Case 2: a researcher-installed FileHandler exists — respect it.
        # We ignore FileHandlers pointing at "/dev/null" (or any other
        # throwaway path) because those are test-infrastructure sentinels
        # (pytest's logging capture writes here), not the researcher's
        # actual log destination.
        if any(
            isinstance(h, logging.FileHandler)
            and getattr(h, "baseFilename", None) != os.devnull
            for h in root.handlers
        ):
            return

        # Case 3: first run in this process and no researcher handler.
        # Create a custom handler that routes messages to symbol-specific files
        handler = _SymbolRoutingHandler(exec_log_dir, symbols)
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
        )
        setattr(handler, _QUANTREX_RUN_HANDLER, True)

        # Python's logging filters records against the LOGGER's level
        # first (default WARNING). If the root logger stays at WARNING,
        # our ``logger.info(...)`` calls never reach this file handler
        # and ``execution.log`` is created but stays empty. Lower the
        # root level (and the handler) to INFO so per-bar audit lines
        # actually land in the file.
        if root.level == logging.NOTSET or root.level > logging.INFO:
            root.setLevel(logging.INFO)
        root.addHandler(handler)
        self._handler = handler

    def rebind_log_handlers(self, exec_log_dir: Path, symbols: List[str]) -> None:
        """Rebind existing Quantrex log handlers to a new directory."""
        root = logging.getLogger()

        # Find our custom handler and update its directory
        for h in root.handlers:
            if getattr(h, _QUANTREX_RUN_HANDLER, False) and isinstance(h, _SymbolRoutingHandler):
                h.rebind(exec_log_dir, symbols)
                return

        # Fallback: remove old handlers and create new ones
        handlers_to_remove = [h for h in root.handlers if getattr(h, _QUANTREX_RUN_HANDLER, False)]
        for h in handlers_to_remove:
            h.close()
            root.removeHandler(h)

        handler = _SymbolRoutingHandler(exec_log_dir, symbols)
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
        )
        setattr(handler, _QUANTREX_RUN_HANDLER, True)
        root.addHandler(handler)
        self._handler = handler