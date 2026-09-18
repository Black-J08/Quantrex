"""Backtest engine core orchestration."""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
import csv
from typing import List, Optional

from quantrex_core.logging import get_logger
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.strategy.base import Strategy
from quantrex_core.order import OrderManagementSystem
from quantrex_core.position.manager import PositionManager
from quantrex_core import InstrumentSpec, PortfolioConfig
from quantrex_backtest.portfolio import PortfolioResult, SymbolResult
from .timeframe import calculate_close_time
from ..exceptions.backtest_error import ProviderError
from ..data import DataOrchestrator, DataOrchestratorConfig
from ..portfolio import BacktestPortfolioContext

logger = get_logger(__name__)

_RUN_LOG_FILENAME = "execution.log"


class BacktestEngine:
    """Deterministic event-driven backtest engine.

    Processes OHLCV candles sequentially in timestamp order,
    invoking a strategy's lifecycle methods for each candle.

    Supports portfolio backtesting through a unified API.

    Example (portfolio):
        >>> from quantrex_backtest import InstrumentSpec, PortfolioConfig
        >>> from quantrex_data.providers.csv_provider import CSVDataProvider
        >>> from quantrex_data.adapters.csv_adapter import CSVDataAdapter
        >>> from quantrex_core import Strategy, Candle
        >>>
        >>> class MyStrategy(Strategy):
        ...     def on_candle(self, candle: Candle) -> None:
        ...         print(candle.timestamp, candle.close)
        >>>
        >>> provider = CSVDataProvider("data.csv", has_header=False)
        >>> adapter = CSVDataAdapter(provider, mapping={...})
        >>> instruments = [
        ...     InstrumentSpec(symbol="COPPER", adapter=adapter),
        ... ]
        >>> config = PortfolioConfig(initial_cash=1_000_000)
        >>> strategy = MyStrategy()
        >>> engine = BacktestEngine(instruments, strategy, config)
        >>> result = engine.run()
    """

    def __init__(
        self,
        instruments: List[InstrumentSpec],
        strategy: Strategy,
        config: PortfolioConfig,
    ) -> None:
        """Initialize the backtest engine in portfolio mode.

        Args:
            instruments: List of InstrumentSpec defining symbols and their data adapters
            strategy: Strategy instance to execute
            config: PortfolioConfig with portfolio-level settings

        Raises:
            ProviderError: If required arguments are None or invalid.
        """
        if strategy is None:
            raise ProviderError("Strategy is required; received None")

        if not instruments:
            raise ProviderError("At least one instrument required")

        # Validate all instruments have adapters
        for spec in instruments:
            if spec.adapter is None:
                raise ProviderError(f"DataAdapter required for instrument {spec.symbol}; received None")

        self._instruments = instruments
        self._strategy = strategy
        self._config = config

        # Create PositionManager, OMS
        self._position_manager = PositionManager()
        self._oms = OrderManagementSystem()

        # Build symbol→adapter map for O(1) lookup in hot loop
        self._symbol_to_adapter = {spec.symbol: spec.adapter for spec in instruments}

        # Context will be created in run() after data preparation
        self._context: Optional[BacktestPortfolioContext] = None
        self._data_orchestrator = DataOrchestrator(DataOrchestratorConfig(
            cache_dir=Path("data/cache"),
            exchange_calendar="NSE",
            auto_download=self._config.auto_download,
            validate_completeness=self._config.validate_completeness,
            min_bars_required=self._config.min_bars_required,
        ))

        # Inject context into Strategy (will be updated in run())
        self._strategy.set_context(self._context)  # Will be set properly in run()

    def run(self) -> PortfolioResult:
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

        # Portfolio mode: use DataOrchestrator and synchronized execution
        return self._run_portfolio(staging_dir, backtest_start_utc)

    def _run_portfolio(self, staging_dir: Path, backtest_start_utc: datetime) -> PortfolioResult:
        """Run backtest in portfolio mode (new logic)."""
        # Step 1: Get required timeframes
        required_timeframes = self._get_required_timeframes()
        base_timeframe = required_timeframes[0]
        
        # Step 2: Use DataOrchestrator to prepare validated, synchronized base timeframe data
        logger.info("Preparing data for %d instruments using DataOrchestrator", len(self._instruments))
        try:
            synchronized_base_data = self._data_orchestrator.validate_and_prepare(
                self._instruments,
                self._config,
            )
        except ValueError as e:
            # Wrap orchestrator ValueError in ProviderError for consistent error handling
            raise ProviderError(f"Failed to read data: {e}") from e
        
        if not synchronized_base_data:
            logger.warning("No data available for any instrument; backtest completed with zero candles")
            self._strategy.on_stop()
            self._export_trades_csv(staging_dir)
            logger.info("Run log: %s", staging_dir / _RUN_LOG_FILENAME)
            return PortfolioResult.empty(self._config.initial_cash)

        # Step 3: Read additional timeframes directly from adapters (non-base timeframes)
        additional_timeframes = [tf for tf in required_timeframes if tf != base_timeframe]
        all_raw_data = {}
        
        # Add synchronized base timeframe data from orchestrator
        for symbol, data in synchronized_base_data.items():
            all_raw_data[symbol] = {base_timeframe: data}
        
        # Read additional timeframes for each instrument
        for spec in self._instruments:
            symbol = spec.symbol
            if symbol not in all_raw_data:
                all_raw_data[symbol] = {}
            for tf in additional_timeframes:
                try:
                    all_raw_data[symbol][tf] = spec.adapter.read_timeframe(tf)
                except ValueError as e:
                    logger.exception("Adapter read_timeframe failed for %s timeframe %s", symbol, tf)
                    raise ProviderError(
                        f"Cannot provide timeframe '{tf}': {e}. "
                        f"Available native timeframes: {spec.adapter.supported_timeframes}"
                    ) from e
                except Exception as e:
                    logger.exception("Adapter read_timeframe failed for %s timeframe %s", symbol, tf)
                    raise ProviderError(
                        f"Failed to read data for {symbol} timeframe {tf}: {e}"
                    ) from e

        # Step 4: Create unified PortfolioContext
        symbols = list(all_raw_data.keys())
        origin_time = self._instruments[0].adapter.get_origin_time()
        
        self._context = BacktestPortfolioContext(
            position_manager=self._position_manager,
            oms=self._oms,
            current_time=datetime.min,
            instruments=symbols,
            initial_cash=self._config.initial_cash,
            margin_requirement=self._config.margin_requirement,
            raw_data_by_timeframe=all_raw_data,
            indicators_by_timeframe={},  # Will be populated after indicator computation
            base_timeframe=base_timeframe,
            origin_time=origin_time,
        )

        # Set symbol and datetime format for each instrument's context
        for spec in self._instruments:
            self._context.strategy_context.set_symbol_and_format(spec.symbol, spec.adapter.datetime_format)

        # Inject context into Strategy
        self._strategy.set_context(self._context)

        # Step 5: Create common time index from base timeframe data
        base_data = all_raw_data[symbols[0]][base_timeframe]  # Use first symbol as reference
        
        if not base_data:
            logger.warning("No base timeframe data; backtest completed with zero candles")
            self._strategy.on_stop()
            self._export_trades_csv(staging_dir)
            logger.info("Run log: %s", staging_dir / _RUN_LOG_FILENAME)
            return PortfolioResult.empty(self._config.initial_cash)

        # Sort base data by datetime
        base_data.sort(key=lambda row: row.get("datetime", ""))

        # Step 5: Compute indicators for each instrument and timeframe
        all_indicators = {}
        for spec in self._instruments:
            symbol = spec.symbol
            all_indicators[symbol] = {}
            for tf in required_timeframes:
                try:
                    indicators = self._strategy.compute_indicators(
                        all_raw_data[symbol][tf], timeframe=tf
                    )
                    # Validate length matches
                    if len(indicators) != len(all_raw_data[symbol][tf]):
                        logger.exception(
                            "compute_indicators returned %d entries for %d candles (timeframe %s)",
                            len(indicators), len(all_raw_data[symbol][tf]), tf,
                        )
                        raise ProviderError(
                            f"compute_indicators returned {len(indicators)} entries "
                            f"for {len(all_raw_data[symbol][tf])} candles (timeframe {tf}); length must match"
                        )
                    all_indicators[symbol][tf] = indicators
                except Exception as e:
                    logger.exception("Strategy.compute_indicators raised for %s timeframe %s", symbol, tf)
                    raise ProviderError(
                        f"Strategy.compute_indicators failed for {symbol} timeframe {tf}: {e}"
                    ) from e

        # Update context with computed indicators
        self._context._strategy_context._indicators_by_timeframe = all_indicators

        # Step 6: Pre-build datetime→row dictionaries for O(1) lookup in main loop
        symbol_tf_to_rows = {}
        for symbol in symbols:
            symbol_tf_to_rows[symbol] = {}
            for tf in required_timeframes:
                row_map = {}
                adapter = self._symbol_to_adapter[symbol]
                for row in all_raw_data[symbol][tf]:
                    dt_val = row.get("datetime")
                    if isinstance(dt_val, str):
                        dt = datetime.strptime(dt_val, adapter.datetime_format)
                    elif isinstance(dt_val, datetime):
                        dt = dt_val
                    else:
                        continue
                    row_map[dt] = row
                symbol_tf_to_rows[symbol][tf] = row_map

        # Step 7: Main event loop - iterate synchronized timestamps
        logger.info("Processing %d synchronized candles (base timeframe: %s)", len(base_data), base_timeframe)

        data_start: str | None = None
        data_end: str | None = None
        equity_curve: List[tuple[datetime, float]] = []

        for idx, base_row in enumerate(base_data):
            try:
                # Create candles for all symbols at this timestamp
                timestamp = base_row.get("datetime")
                if isinstance(timestamp, str):
                    # Use first symbol's adapter format for base timeframe parsing
                    base_adapter = self._symbol_to_adapter[symbols[0]]
                    ts = datetime.strptime(timestamp, base_adapter.datetime_format)
                else:
                    ts = timestamp

                # Capture first and last candle timestamps for output path
                if data_start is None:
                    data_start = ts.strftime("%Y%m%d_%H%M%S")
                data_end = ts.strftime("%Y%m%d_%H%M%S")

                # Create candles for each symbol
                candles = {}
                for symbol in symbols:
                    # O(1) lookup for matching row
                    symbol_row = symbol_tf_to_rows[symbol][base_timeframe].get(ts)
                    
                    if symbol_row is None:
                        continue  # Skip if no data for this symbol at this timestamp

                    # O(1) adapter lookup
                    symbol_adapter = self._symbol_to_adapter[symbol]

                    indicators = all_indicators[symbol].get(base_timeframe, [{}])[idx] if idx < len(all_indicators[symbol].get(base_timeframe, [])) else {}
                    try:
                        candle = Candle.from_row(
                            symbol_row,
                            symbol,
                            symbol_adapter.datetime_format,  # Use this symbol's adapter format
                            indicators=indicators,
                        )
                    except ValueError as e:
                        logger.exception("Failed to create candle for %s at index %d", symbol, idx)
                        raise ProviderError(f"Failed to process candle at index {idx}: {e}") from e
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

    def _build_portfolio_result(
        self,
        equity_curve: List[tuple[datetime, float]],
        data_start: Optional[str],
        data_end: Optional[str],
        symbols: List[str],
    ) -> PortfolioResult:
        """Build PortfolioResult from backtest execution."""
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

