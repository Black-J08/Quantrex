"""Backtest engine core orchestration."""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
import csv

from quantrex_core.logging import get_logger
from quantrex_core.models import Candle
from quantrex_core.protocols import DataAdapter
from quantrex_core.strategy.base import Strategy
from quantrex_core.position.manager import PositionManager
from .context import BacktestStrategyContext
from ..exceptions.backtest_error import ProviderError

logger = get_logger(__name__)

_RUN_LOG_FILENAME = "execution.log"


class BacktestEngine:
    """Deterministic event-driven backtest engine.

    Processes OHLCV candles sequentially in timestamp order,
    invoking a strategy's lifecycle methods for each candle.

    Example:
        >>> from quantrex_data.providers.csv_provider import CSVDataProvider
        >>> from quantrex_data.adapters.csv_adapter import CSVDataAdapter
        >>> from quantrex_backtest import BacktestEngine
        >>> from quantrex_core import Strategy, Candle
        >>>
        >>> class MyStrategy(Strategy):
        ...     def on_candle(self, candle: Candle) -> None:
        ...         print(candle.timestamp, candle.close)
        >>>
        >>> provider = CSVDataProvider("data.csv", has_header=False)
        >>> adapter = CSVDataAdapter(provider, mapping={...})
        >>> strategy = MyStrategy()
        >>> engine = BacktestEngine(adapter, strategy, symbol="COPPER")
        >>> engine.run()
    """

    def __init__(
        self,
        adapter: DataAdapter,
        strategy: Strategy,
        symbol: str = "",
    ) -> None:
        """Initialize the backtest engine.

        Args:
            adapter: DataAdapter instance providing normalized candle data via read()
            strategy: Strategy instance to execute
            symbol: Trading symbol for the candles

        Raises:
            ProviderError: If adapter is None or strategy is None.
        """
        if adapter is None:
            raise ProviderError("DataAdapter is required; received None")
        if strategy is None:
            raise ProviderError("Strategy is required; received None")

        self._adapter = adapter
        self._strategy = strategy
        self._symbol = symbol
        # Single source of truth: read datetime format directly from adapter
        self._datetime_format = adapter.datetime_format

        # Create PositionManager and StrategyContext
        self._position_manager = PositionManager()
        self._context = BacktestStrategyContext(self._position_manager, datetime.min)
        
        # Inject context into Strategy
        self._strategy.set_context(self._context)

    def run(self) -> None:
        """Run the backtest, invoking the strategy's lifecycle methods.

        Calls strategy.on_start(), then strategy.on_candle() for each candle
        in timestamp order, then strategy.on_stop().
        After completion, exports closed trades to CSV.

        Raises:
            ProviderError: If adapter.read() fails or returns invalid data.
        """
        backtest_start_utc = datetime.now(timezone.utc)

        # Build a staging run directory (named with just the backtest start
        # timestamp) and attach execution.log to the root logger so the very
        # first log line of the run is captured. No-op if the researcher
        # already attached a FileHandler via setup_logging(log_file=...).
        staging_dir = self._build_run_dir(backtest_start_utc, data_start=None, data_end=None)
        staging_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_run_log_file(staging_dir)

        logger.info("Starting backtest for symbol: %s", self._symbol)

        self._strategy.on_start()

        try:
            raw_data = self._adapter.read()
        except Exception as e:
            logger.exception("Adapter read() failed")
            raise ProviderError(f"Failed to read data from adapter: {e}") from e

        if not raw_data:
            logger.warning("No data returned from adapter; backtest completed with zero candles")
            self._strategy.on_stop()
            self._export_trades_csv(staging_dir)
            logger.info("Run log: %s", staging_dir / _RUN_LOG_FILENAME)
            return

        # Sort by datetime for deterministic ordering
        raw_data.sort(key=lambda row: row.get("datetime", ""))

        logger.info("Processing %d candles", len(raw_data))

        # Call the strategy's compute_indicators hook exactly once with the
        # full sorted row sequence, BEFORE any Candle is constructed. The
        # returned list must be aligned by index; the i-th element is
        # threaded into the i-th Candle via Candle.from_row(..., indicators=...).
        # The framework is indicator-implementation agnostic: the strategy
        # is free to use pandas / polars / numpy / ta-lib / hand-rolled
        # math inside the override.
        try:
            per_bar = self._strategy.compute_indicators(raw_data)
        except Exception as e:
            logger.exception("Strategy.compute_indicators raised")
            raise ProviderError(
                f"Strategy.compute_indicators failed: {e}"
            ) from e

        if len(per_bar) != len(raw_data):
            logger.exception(
                "compute_indicators returned %d entries for %d candles",
                len(per_bar), len(raw_data),
            )
            raise ProviderError(
                f"compute_indicators returned {len(per_bar)} entries "
                f"for {len(raw_data)} candles; length must match"
            )

        data_start: str | None = None
        data_end: str | None = None

        for idx, row in enumerate(raw_data):
            try:
                candle = Candle.from_row(
                    row,
                    self._symbol,
                    self._datetime_format,
                    indicators=per_bar[idx],
                )

                # Capture first and last candle timestamps for output path
                if data_start is None:
                    data_start = candle.timestamp.strftime("%Y%m%d_%H%M%S")
                data_end = candle.timestamp.strftime("%Y%m%d_%H%M%S")

                # Update context time and candle for order timestamps and pricing
                self._context.update_time(candle.timestamp)
                self._context.update_candle(candle)
                # Emit a per-bar audit line so execution.log records the
                # backtest/candle timestamp, OHLCV, and all precomputed
                # indicator values without researchers having to add logging
                # in their strategy.
                indicator_parts = [
                    f"{k}={v}" for k, v in sorted(candle.indicators.items()) if v is not None
                ]
                indicator_str = " " + " ".join(indicator_parts) if indicator_parts else ""
                logger.info(
                    "[%s %s] O=%s H=%s L=%s C=%s V=%s%s",
                    candle.symbol,
                    candle.timestamp.isoformat(),
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                    indicator_str,
                )
                self._strategy.on_candle(candle)
            except Exception as e:
                logger.exception("Failed to process candle at index %d", idx)
                raise ProviderError(f"Failed to process candle at index {idx}: {e}") from e

        self._strategy.on_stop()
        logger.info("Backtest completed: %d candles processed", len(raw_data))

        # Promote staging -> final run dir now that we know the data window.
        # We move individual files (closed_trades.csv and execution.log)
        # rather than renaming the directory, because Path.rename fails on
        # non-empty directories in some environments.
        final_run_dir = self._build_run_dir(backtest_start_utc, data_start, data_end)
        if final_run_dir != staging_dir:
            run_dir = self._promote_run_dir(staging_dir, final_run_dir)
        else:
            run_dir = staging_dir

        # Export closed trades into the final run dir.
        self._export_trades_csv(run_dir)
        logger.info("Run log: %s", run_dir / _RUN_LOG_FILENAME)

    def _promote_run_dir(self, staging_dir: Path, final_run_dir: Path) -> Path:
        """Move a staging run directory's files into the final location.

        Used when the data window only becomes known after the first
        candle is processed. Creates ``final_run_dir`` if it doesn't exist
        and moves ``closed_trades.csv`` + ``execution.log`` into it, then
        reattaches the per-run log handler so subsequent log calls land
        in the new path. Removes the (now-empty) staging directory and
        returns the final directory.
        """
        final_run_dir.mkdir(parents=True, exist_ok=True)
        for name in ("closed_trades.csv", _RUN_LOG_FILENAME):
            src = staging_dir / name
            if src.exists():
                src.rename(final_run_dir / name)
        # Remove the empty staging directory so it doesn't pollute
        # "latest output dir" tests.
        try:
            staging_dir.rmdir()
        except OSError:
            # Staging dir wasn't empty (e.g. external process wrote into
            # it); leave it in place rather than masking the cause.
            pass
        # Rebind the handler to the new log path.
        self._ensure_run_log_file(final_run_dir)
        return final_run_dir

    def _build_run_dir(
        self,
        backtest_start_utc: datetime,
        data_start: str | None,
        data_end: str | None,
    ) -> Path:
        """Build the per-run output directory path (does not create it)."""
        strategy_name = type(self._strategy).__name__
        backtest_start_str = backtest_start_utc.strftime("%Y%m%d_%H%M%S")
        if data_start is None or data_end is None:
            data_start = backtest_start_str
            data_end = backtest_start_str
        return (
            Path("output")
            / "backtest"
            / strategy_name
            / f"{backtest_start_str}_{self._symbol}_{data_start}_{data_end}_short"
        )

    # Sentinel attribute on handlers we attach ourselves so subsequent
    # ``_ensure_run_log_file`` calls can detect (and rebind to the new
    # run directory) handlers we previously attached, while still treating
    # researcher-installed FileHandlers as a no-op signal.
    _QUANTREX_RUN_HANDLER = "_quantrex_run_log_handler"

    def _ensure_run_log_file(self, run_dir: Path) -> None:
        """Attach a per-run ``execution.log`` FileHandler to the root logger.

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

        # Case 1: we attached a handler in an earlier engine.run() — rebind
        # it to the current run directory and stop. Otherwise, per-candle
        # INFO records would silently keep landing in the stale directory
        # from the first run (this is the root cause of the regression).
        for h in root.handlers:
            if getattr(h, self._QUANTREX_RUN_HANDLER, False):
                rebind_path = run_dir / _RUN_LOG_FILENAME
                if Path(h.baseFilename) != rebind_path:
                    h.close()
                    root.removeHandler(h)
                    new_handler = logging.FileHandler(
                        rebind_path, mode="a", encoding="utf-8"
                    )
                    new_handler.setLevel(logging.INFO)
                    new_handler.setFormatter(
                        logging.Formatter(
                            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
                        )
                    )
                    setattr(new_handler, self._QUANTREX_RUN_HANDLER, True)
                    root.addHandler(new_handler)
                return

        # Case 2: a researcher-installed FileHandler exists — respect it.
        # We ignore FileHandlers pointing at "/dev/null" (or any other
        # throwaway path) because those are test-infrastructure sentinels
        # (pytest's logging capture writes here), not the researcher's
        # actual log destination. Without this guard, every test run would
        # silently skip attaching execution.log because pytest attaches
        # a /dev/null FileHandler before the engine runs.
        if any(
            isinstance(h, logging.FileHandler)
            and getattr(h, "baseFilename", None) != os.devnull
            for h in root.handlers
        ):
            return

        # Case 3: first run in this process and no researcher handler.
        log_path = run_dir / _RUN_LOG_FILENAME
        # Python's logging filters records against the LOGGER's level
        # first (default WARNING). If the root logger stays at WARNING,
        # our ``logger.info(...)`` calls never reach this file handler
        # and ``execution.log`` is created but stays empty. Lower the
        # root level (and the handler) to INFO so per-bar audit lines
        # actually land in the file.
        if root.level == logging.NOTSET or root.level > logging.INFO:
            root.setLevel(logging.INFO)
        handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
        )
        setattr(handler, self._QUANTREX_RUN_HANDLER, True)
        root.addHandler(handler)

    def _export_trades_csv(self, output_dir: Path) -> None:
        """Export closed trades to CSV inside ``output_dir``."""
        trades = self._position_manager.get_closed_trades()
        output_file = output_dir / "closed_trades.csv"

        # Write CSV with headers (even if empty)
        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "symbol", "side", "quantity",
                "entry_timestamp", "entry_price",
                "exit_timestamp", "exit_price",
                "pnl"
            ])
            for trade in trades:
                writer.writerow([
                    trade.symbol,
                    trade.side.value,
                    trade.quantity,
                    trade.entry_timestamp.isoformat(),
                    trade.entry_price,
                    trade.exit_timestamp.isoformat(),
                    trade.exit_price,
                    trade.pnl,
                ])

        logger.info("Exported %d closed trades to %s", len(trades), output_file)