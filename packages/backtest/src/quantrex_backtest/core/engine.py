"""Backtest engine core orchestration."""

import logging
import os
from datetime import datetime, timezone, timedelta
import re
from pathlib import Path
import csv
from typing import List, Optional, Union

from quantrex_core.logging import get_logger
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.strategy.base import Strategy
from quantrex_core.order import OrderManagementSystem
from quantrex_core.position.manager import PositionManager
from quantrex_core import InstrumentSpec, PortfolioConfig
from quantrex_backtest.portfolio import PortfolioResult, SymbolResult
from .context import BacktestStrategyContext
from .timeframe import parse_timeframe_to_timedelta, calculate_close_time
from ..exceptions.backtest_error import ProviderError
from ..data import DataOrchestrator, DataOrchestratorConfig
from ..portfolio import BacktestPortfolioContext

logger = get_logger(__name__)

_RUN_LOG_FILENAME = "execution.log"


class BacktestEngine:
    """Deterministic event-driven backtest engine.

    Processes OHLCV candles sequentially in timestamp order,
    invoking a strategy's lifecycle methods for each candle.

    Supports both single-instrument and portfolio backtesting
    through a unified API.

    Example (single instrument):
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
        >>> result = engine.run()

    Example (portfolio):
        >>> from quantrex_backtest import InstrumentSpec, PortfolioConfig
        >>>
        >>> instruments = [
        ...     InstrumentSpec(symbol="COPPER", adapter=copper_adapter),
        ...     InstrumentSpec(symbol="SILVER", adapter=silver_adapter),
        ... ]
        >>> config = PortfolioConfig(initial_cash=1_000_000)
        >>> engine = BacktestEngine(instruments, strategy, config)
        >>> result = engine.run()
    """

    def __init__(
        self,
        instruments_or_adapter: Union[List[InstrumentSpec], object],
        strategy: Strategy,
        symbol: str = "",
        config: Optional[PortfolioConfig] = None,
    ) -> None:
        """Initialize the backtest engine.

        Two calling conventions supported:

        1. Portfolio mode (new):
           BacktestEngine(instruments: List[InstrumentSpec], strategy: Strategy, config: PortfolioConfig)

        2. Single-instrument mode (backward compatible):
           BacktestEngine(adapter: DataAdapter, strategy: Strategy, symbol: str = "")

        Args:
            instruments_or_adapter: Either list of InstrumentSpec (portfolio mode) or DataAdapter (single mode)
            strategy: Strategy instance to execute
            symbol_or_config: Either PortfolioConfig (portfolio mode) or symbol string (single mode)

        Raises:
            ProviderError: If required arguments are None or invalid.
        """
        if strategy is None:
            raise ProviderError("Strategy is required; received None")

        self._strategy = strategy

        # Detect calling convention
        if isinstance(instruments_or_adapter, list):
            # Portfolio mode
            self._instruments = instruments_or_adapter
            self._config = config if isinstance(config, PortfolioConfig) else PortfolioConfig()
            self._is_portfolio_mode = True

            if not self._instruments:
                raise ProviderError("At least one instrument required in portfolio mode")

            # Validate all instruments have adapters
            for spec in self._instruments:
                if spec.adapter is None:
                    raise ProviderError(f"DataAdapter required for instrument {spec.symbol}; received None")

            # Use first instrument's adapter for datetime format (they should be consistent)
            self._datetime_format = self._instruments[0].adapter.datetime_format

        else:
            # Single-instrument mode (backward compatible)
            adapter = instruments_or_adapter
            if adapter is None:
                raise ProviderError("DataAdapter is required; received None")

            self._instruments = [InstrumentSpec(
                symbol=symbol if isinstance(symbol, str) else "",
                adapter=adapter,
            )]
            self._config = PortfolioConfig()
            self._is_portfolio_mode = False
            self._symbol = symbol if isinstance(symbol, str) else ""
            self._datetime_format = adapter.datetime_format

        # Create PositionManager, OMS
        self._position_manager = PositionManager()
        self._oms = OrderManagementSystem()

        # Context will be created in run() after data preparation
        self._context: Optional[BacktestPortfolioContext] = None
        self._data_orchestrator = DataOrchestrator(DataOrchestratorConfig(
            cache_dir=Path("data/cache"),
            exchange_calendar="NSE",
            auto_download=self._config.auto_download,
            validate_completeness=self._config.validate_completeness if hasattr(self._config, 'validate_completeness') else True,
            min_bars_required=100,
        ))

        # Inject context into Strategy (will be updated in run())
        self._strategy.set_context(self._context)  # Will be set properly in run()

    def run(self, parallel: bool = False, max_workers: Optional[int] = None) -> PortfolioResult:
        """Run the backtest, invoking the strategy's lifecycle methods.

        Calls strategy.on_start(), then strategy.on_candle() for each candle
        in timestamp order, then strategy.on_stop().
        After completion, exports closed trades to CSV and returns PortfolioResult.

        Args:
            parallel: If True, run independent instruments in parallel (experimental).
            max_workers: Maximum number of worker processes for parallel execution.

        Returns:
            PortfolioResult with portfolio-level and per-symbol metrics.

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

        logger.info("Starting backtest for %d instrument(s)", len(self._instruments))

        self._strategy.on_start()

        # Single-instrument mode: use legacy logic for backward compatibility
        if not self._is_portfolio_mode:
            return self._run_single_instrument(staging_dir, backtest_start_utc)

        # Portfolio mode: use DataOrchestrator and synchronized execution
        return self._run_portfolio(staging_dir, backtest_start_utc)

    def _run_single_instrument(self, staging_dir: Path, backtest_start_utc: datetime) -> PortfolioResult:
        """Run backtest in single-instrument mode (legacy logic)."""
        # Get required timeframes from strategy
        required_timeframes = self._get_required_timeframes()
        
        # Read raw data for all required timeframes
        raw_data_by_tf = self._read_all_timeframes(required_timeframes)
        
        # Check if base timeframe has data
        base_timeframe = required_timeframes[0]
        base_raw = raw_data_by_tf.get(base_timeframe, [])
        
        if not base_raw:
            logger.warning("No data returned from adapter; backtest completed with zero candles")
            self._strategy.on_stop()
            self._export_trades_csv(staging_dir)
            logger.info("Run log: %s", staging_dir / _RUN_LOG_FILENAME)
            return PortfolioResult.empty(self._config.initial_cash)
        
        # Sort each timeframe's data by datetime for deterministic ordering
        for tf in raw_data_by_tf:
            raw_data_by_tf[tf].sort(key=lambda row: row.get("datetime", ""))

        # Compute indicators for each timeframe
        per_bar_by_tf = {}
        for tf in required_timeframes:
            try:
                per_bar_by_tf[tf] = self._strategy.compute_indicators(
                    raw_data_by_tf[tf], timeframe=tf
                )
            except Exception as e:
                logger.exception("Strategy.compute_indicators raised for timeframe %s", tf)
                raise ProviderError(
                    f"Strategy.compute_indicators failed for timeframe {tf}: {e}"
                ) from e

        # Validate lengths match for each timeframe
        for tf in required_timeframes:
            if len(per_bar_by_tf[tf]) != len(raw_data_by_tf[tf]):
                logger.exception(
                    "compute_indicators returned %d entries for %d candles (timeframe %s)",
                    len(per_bar_by_tf[tf]), len(raw_data_by_tf[tf]), tf,
                )
                raise ProviderError(
                    f"compute_indicators returned {len(per_bar_by_tf[tf])} entries "
                    f"for {len(raw_data_by_tf[tf])} candles (timeframe {tf}); length must match"
                )

        # Determine base timeframe (first in required_timeframes)
        base_timeframe = required_timeframes[0]
        
        # Create new context with multi-timeframe data
        # Get origin time from adapter for correct timeframe aggregation
        origin_time = self._instruments[0].adapter.get_origin_time()
        self._context = BacktestStrategyContext(
            self._position_manager,
            self._oms,
            datetime.min,
            raw_data_by_timeframe=raw_data_by_tf,
            indicators_by_timeframe=per_bar_by_tf,
            base_timeframe=base_timeframe,
            origin_time=origin_time,
        )
        
        # Set symbol and datetime format for derived candle construction
        self._context.set_symbol_and_format(self._symbol, self._datetime_format)
        
        # Inject context into Strategy
        self._strategy.set_context(self._context)

        logger.info("Processing %d candles (base timeframe: %s)", len(raw_data_by_tf[base_timeframe]), base_timeframe)

        data_start: str | None = None
        data_end: str | None = None
        base_raw = raw_data_by_tf[base_timeframe]
        base_indicators = per_bar_by_tf[base_timeframe]
        equity_curve: List[tuple[datetime, float]] = []

        for idx, row in enumerate(base_raw):
            try:
                candle = Candle.from_row(
                    row,
                    self._symbol,
                    self._datetime_format,
                    indicators=base_indicators[idx],
                )

                # Capture first and last candle timestamps for output path
                if data_start is None:
                    data_start = candle.timestamp.strftime("%Y%m%d_%H%M%S")
                data_end = candle.timestamp.strftime("%Y%m%d_%H%M%S")

                # Drain any pending orders at this candle's open price (T+1 execution).
                # This runs BEFORE update_time / update_candle so the timestamp and
                # price used for fill match the current candle exactly.
                self._drain_pending(candle.open, candle.timestamp)

                # Update context time with candle's close time for execution timing
                # and candle for order pricing
                close_time = calculate_close_time(candle.timestamp, base_timeframe)
                self._context.update_time(close_time)
                self._context.update_candle(candle)
                # Record the current bar in the context's history BEFORE
                # ``on_candle`` so the strategy observes it as the last
                # element of ``ctx.history`` (``ctx.history[-1] is candle``).
                # This is what makes the ``ctx.history[-N:]`` lookback idiom
                # work end-to-end with no per-bar bookkeeping in the
                # strategy.
                self._context.record_candle(candle)
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
                # Call on_candle only when strategy defines it; otherwise
                # only timeframe dispatch runs (no 1M iteration needed).
                if any("on_candle" in cls.__dict__ for cls in self._strategy.__class__.__mro__ if cls is not Strategy):
                    self._strategy.on_candle(candle)
                # Engine manages timeframe dispatch automatically.
                self._strategy.timeframe_dispatcher.dispatch_all(self._context)

                # Record equity curve point
                equity_curve.append((close_time, self._context.equity))

            except Exception as e:
                logger.exception("Failed to process candle at index %d", idx)
                raise ProviderError(f"Failed to process candle at index {idx}: {e}") from e

        # Flush any remaining pending orders at the final candle's close price.
        # This handles the case where the strategy submits an order on the
        # last candle; without this the order would be silently dropped.
        last_candle = Candle.from_row(
            base_raw[-1], self._symbol, self._datetime_format, indicators=base_indicators[-1]
        )
        last_close_time = calculate_close_time(last_candle.timestamp, base_timeframe)
        self._drain_pending(last_candle.close, last_close_time, is_final=True)

        self._strategy.on_stop()
        logger.info("Backtest completed: %d candles processed", len(base_raw))

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

        # Build PortfolioResult
        return self._build_portfolio_result(
            equity_curve=equity_curve,
            data_start=data_start,
            data_end=data_end,
            symbols=[self._symbol],
        )

    def _run_portfolio(self, staging_dir: Path, backtest_start_utc: datetime) -> PortfolioResult:
        """Run backtest in portfolio mode (new logic)."""
        # Step 1: Prepare data using DataOrchestrator
        logger.info("Preparing data for %d instruments", len(self._instruments))
        synchronized_data = self._data_orchestrator.validate_and_prepare(
            self._instruments,
            self._config,
        )

        if not synchronized_data:
            logger.warning("No data available for any instrument; backtest completed with zero candles")
            self._strategy.on_stop()
            self._export_trades_csv(staging_dir)
            logger.info("Run log: %s", staging_dir / _RUN_LOG_FILENAME)
            return PortfolioResult.empty(self._config.initial_cash)

        # Step 2: Create unified PortfolioContext
        symbols = list(synchronized_data.keys())
        origin_time = self._instruments[0].adapter.get_origin_time()
        
        self._context = BacktestPortfolioContext(
            position_manager=self._position_manager,
            oms=self._oms,
            current_time=datetime.min,
            instruments=symbols,
            initial_cash=self._config.initial_cash,
            margin_requirement=self._config.margin_requirement,
            raw_data_by_timeframe={},  # Will be populated per timeframe
            indicators_by_timeframe={},
            base_timeframe="1M",
            origin_time=origin_time,
        )

        # Set symbol and datetime format for each instrument's context
        for spec in self._instruments:
            self._context.strategy_context.set_symbol_and_format(spec.symbol, spec.adapter.datetime_format)

        # Inject context into Strategy
        self._strategy.set_context(self._context)

        # Step 3: Get required timeframes and compute indicators for each instrument
        required_timeframes = self._get_required_timeframes()
        
        # Compute indicators for each instrument and timeframe
        all_indicators = {}
        for spec in self._instruments:
            symbol = spec.symbol
            data = synchronized_data[symbol]
            all_indicators[symbol] = {}
            for tf in required_timeframes:
                try:
                    all_indicators[symbol][tf] = self._strategy.compute_indicators(data, timeframe=tf)
                except Exception as e:
                    logger.exception("Strategy.compute_indicators raised for %s timeframe %s", symbol, tf)
                    raise ProviderError(
                        f"Strategy.compute_indicators failed for {symbol} timeframe {tf}: {e}"
                    ) from e

        # Step 4: Create common time index from base timeframe data
        base_timeframe = required_timeframes[0]
        base_data = synchronized_data[symbols[0]]  # Use first symbol as reference
        
        if not base_data:
            logger.warning("No base timeframe data; backtest completed with zero candles")
            self._strategy.on_stop()
            self._export_trades_csv(staging_dir)
            logger.info("Run log: %s", staging_dir / _RUN_LOG_FILENAME)
            return PortfolioResult.empty(self._config.initial_cash)

        # Sort base data by datetime
        base_data.sort(key=lambda row: row.get("datetime", ""))

        # Step 5: Main event loop - iterate synchronized timestamps
        logger.info("Processing %d synchronized candles (base timeframe: %s)", len(base_data), base_timeframe)

        data_start: str | None = None
        data_end: str | None = None
        equity_curve: List[tuple[datetime, float]] = []

        for idx, base_row in enumerate(base_data):
            try:
                # Create candles for all symbols at this timestamp
                timestamp = base_row.get("datetime")
                if isinstance(timestamp, str):
                    for fmt in ("%Y%m%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                        try:
                            ts = datetime.strptime(timestamp, fmt)
                            break
                        except ValueError:
                            continue
                else:
                    ts = timestamp

                # Capture first and last candle timestamps for output path
                if data_start is None:
                    data_start = ts.strftime("%Y%m%d_%H%M%S")
                data_end = ts.strftime("%Y%m%d_%H%M%S")

                # Create candles for each symbol
                candles = {}
                for symbol in symbols:
                    # Find matching row for this symbol at this timestamp
                    symbol_row = None
                    for row in synchronized_data[symbol]:
                        if row.get("datetime") == base_row.get("datetime"):
                            symbol_row = row
                            break
                    
                    if symbol_row is None:
                        continue  # Skip if no data for this symbol at this timestamp

                    indicators = all_indicators[symbol].get(base_timeframe, [{}])[idx] if idx < len(all_indicators[symbol].get(base_timeframe, [])) else {}
                    candle = Candle.from_row(
                        symbol_row,
                        symbol,
                        self._instruments[0].adapter.datetime_format,  # Use first adapter's format
                        indicators=indicators,
                    )
                    candles[symbol] = candle

                # Drain pending orders at this timestamp's open prices
                for symbol, candle in candles.items():
                    self._drain_pending(candle.open, candle.timestamp, symbol=symbol)

                # Update context time with candle's close time
                close_time = calculate_close_time(candle.timestamp, base_timeframe)
                self._context.update_time(close_time)

                # Update context with each candle and call strategy
                for symbol, candle in candles.items():
                    self._context.update_candle(candle)
                    self._context.record_candle(candle)

                    # Emit per-bar audit line
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

                    # Call on_candle for this symbol
                    if any("on_candle" in cls.__dict__ for cls in self._strategy.__class__.__mro__ if cls is not Strategy):
                        self._strategy.on_candle(candle)

                # Dispatch timeframe events
                self._strategy.timeframe_dispatcher.dispatch_all(self._context)

                # Record equity curve point
                equity_curve.append((close_time, self._context.equity))

            except Exception as e:
                logger.exception("Failed to process candle at index %d", idx)
                raise ProviderError(f"Failed to process candle at index {idx}: {e}") from e

        # Flush any remaining pending orders at the final candle's close price
        if candles:
            last_candle = list(candles.values())[0]
            last_close_time = calculate_close_time(last_candle.timestamp, base_timeframe)
            self._drain_pending(last_candle.close, last_close_time, is_final=True)

        self._strategy.on_stop()
        logger.info("Backtest completed: %d candles processed", len(base_data))

        # Promote staging -> final run dir now that we know the data window
        final_run_dir = self._build_run_dir(backtest_start_utc, data_start, data_end)
        if final_run_dir != staging_dir:
            run_dir = self._promote_run_dir(staging_dir, final_run_dir)
        else:
            run_dir = staging_dir

        # Export closed trades into the final run dir
        self._export_trades_csv(run_dir)
        logger.info("Run log: %s", run_dir / _RUN_LOG_FILENAME)

        # Build PortfolioResult
        return self._build_portfolio_result(
            equity_curve=equity_curve,
            data_start=data_start,
            data_end=data_end,
            symbols=symbols,
        )

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

    def _drain_pending(
        self, execution_price: float, execution_timestamp: datetime, is_final: bool = False, symbol: Optional[str] = None
    ) -> None:
        """Drain all pending orders from the OMS.

        Called at the start of each candle loop iteration (before
        ``update_time`` / ``update_candle``) so the execution timestamp
        and price match the current candle. On the final candle the
        ``is_final`` flag triggers a WARNING if any orders were still
        pending (strategy submitted on the last bar).

        Args:
            execution_price: Price to fill orders at.
            execution_timestamp: Timestamp for the fill.
            is_final: Whether this is the final drain.
            symbol: Optional symbol to drain orders for (portfolio mode).
        """
        if self._oms.pending_count == 0:
            return

        if is_final:
            logger.warning(
                "%d order(s) still pending at final candle — "
                "filling at close price %s as a last resort",
                self._oms.pending_count,
                execution_price,
            )

        entries = self._oms.drain(execution_price, execution_timestamp)
        for entry in entries:
            order = entry.order
            # If symbol specified, only process orders for that symbol
            if symbol is not None and order.symbol != symbol:
                # Re-queue orders for other symbols
                self._oms.submit(order, entry.fill_price, entry.fill_timestamp)
                continue

            # Emit ORDER line at fill time (not signal time) so the timestamp
            # matches the candle the order executes on.
            logger.info(
                "[%s %s] ORDER id=%s status=ACCEPTED side=%s qty=%s type=%s price=%s",
                order.symbol,
                entry.fill_timestamp.isoformat(),
                order.id,
                order.side.value,
                order.quantity,
                order.order_type.value,
                entry.fill_price,
            )
            self._position_manager._record_order(
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                order_type=order.order_type,
                timestamp=order.timestamp,
                price=execution_price,
            )
            delta = order.quantity if order.side == OrderSide.BUY else -order.quantity
            self._position_manager.apply(
                order.symbol, delta, execution_timestamp, execution_price
            )
            logger.info(
                "[%s %s] FILL id=%s side=%s qty=%s price=%s",
                order.symbol,
                execution_timestamp.isoformat(),
                order.id,
                order.side.value,
                order.quantity,
                execution_price,
            )

    def _get_required_timeframes(self) -> list[str]:
        """Get timeframes required by strategy. If on_candle is overridden,
        base is 1M; otherwise base is the first registered @on_timeframe
        interval (no 1-minute data fetched)."""
        strategy_timeframes = self._strategy.timeframe_registry.intervals()
        # Detect whether strategy defines its own on_candle (not just base)
        has_custom_on_candle = any(
            "on_candle" in cls.__dict__ for cls in self._strategy.__class__.__mro__
            if cls is not Strategy
        )
        if has_custom_on_candle:
            base_timeframe = "1M"
        elif strategy_timeframes:
            base_timeframe = strategy_timeframes[0]
        else:
            base_timeframe = "1M"
        all_timeframes = [base_timeframe] + [tf for tf in strategy_timeframes if tf != base_timeframe]
        return all_timeframes

    def _read_all_timeframes(self, timeframes: list[str]) -> dict[str, list[dict]]:
        """Read normalized data for all required timeframes (single-instrument mode).
        
        Uses adapter.read_timeframe() for all timeframes. The adapter handles
        native support and aggregation from 1M internally per the protocol contract.
        
        Args:
            timeframes: List of timeframe intervals to read.
            
        Returns:
            Dictionary mapping timeframe to list of normalized row dicts.
            
        Raises:
            ProviderError: If adapter fails to read data for any timeframe.
        """
        result = {}
        for tf in timeframes:
            try:
                result[tf] = self._instruments[0].adapter.read_timeframe(tf)
            except ValueError as e:
                # Adapter raised ValueError for unsupported timeframe with no 1M available
                logger.exception("Adapter read_timeframe failed for timeframe %s", tf)
                raise ProviderError(
                    f"Cannot provide timeframe '{tf}': {e}. "
                    f"Available native timeframes: {self._instruments[0].adapter.supported_timeframes}"
                ) from e
            except Exception as e:
                logger.exception("Adapter read_timeframe failed for timeframe %s", tf)
                raise ProviderError(f"Failed to read data from adapter for timeframe {tf}: {e}") from e
        return result

    def _build_portfolio_result(
        self,
        equity_curve: List[tuple[datetime, float]],
        data_start: Optional[str],
        data_end: Optional[str],
        symbols: List[str],
    ) -> PortfolioResult:
        """Build PortfolioResult from backtest execution."""
        from quantrex_core.models.trade import TradeRecord
        from quantrex_core.models.position import Position

        # Get all closed trades
        trades = self._position_manager.get_closed_trades()

        # Calculate portfolio metrics
        initial_cash = self._config.initial_cash
        final_equity = equity_curve[-1][1] if equity_curve else initial_cash
        total_return = final_equity - initial_cash
        total_return_pct = (total_return / initial_cash * 100) if initial_cash > 0 else 0.0

        # Calculate max drawdown
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        peak = initial_cash
        for _, equity in equity_curve:
            if equity > peak:
                peak = equity
            drawdown = peak - equity
            drawdown_pct = (drawdown / peak * 100) if peak > 0 else 0.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            if drawdown_pct > max_drawdown_pct:
                max_drawdown_pct = drawdown_pct

        # Calculate trade statistics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.pnl > 0)
        losing_trades = sum(1 for t in trades if t.pnl < 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        # Profit factor
        gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

        # Per-symbol results
        per_symbol = {}
        for symbol in symbols:
            symbol_trades = [t for t in trades if t.symbol == symbol]
            symbol_total = len(symbol_trades)
            symbol_winning = sum(1 for t in symbol_trades if t.pnl > 0)
            symbol_losing = sum(1 for t in symbol_trades if t.pnl < 0)
            symbol_pnl = sum(t.pnl for t in symbol_trades)
            symbol_position = self._position_manager.get_position(symbol)

            per_symbol[symbol] = SymbolResult(
                symbol=symbol,
                trades=symbol_trades,
                final_position=symbol_position,
                total_trades=symbol_total,
                winning_trades=symbol_winning,
                losing_trades=symbol_losing,
                total_pnl=symbol_pnl,
                max_drawdown=0.0,  # Would need per-symbol equity curve
            )

        return PortfolioResult(
            initial_cash=initial_cash,
            final_equity=final_equity,
            total_return=total_return,
            total_return_pct=total_return_pct,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=None,  # Would need returns series
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            per_symbol=per_symbol,
            equity_curve=equity_curve,
            start_date=datetime.strptime(data_start, "%Y%m%d_%H%M%S") if data_start else None,
            end_date=datetime.strptime(data_end, "%Y%m%d_%H%M%S") if data_end else None,
            symbols=symbols,
        )

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
        
        # Use first symbol for directory name in portfolio mode
        symbol_str = self._instruments[0].symbol if self._instruments else "UNKNOWN"
        if len(self._instruments) > 1:
            symbol_str += f"_+{len(self._instruments)-1}"
        
        return (
            Path("output")
            / "backtest"
            / strategy_name
            / f"{backtest_start_str}_{symbol_str}_{data_start}_{data_end}_short"
        )

