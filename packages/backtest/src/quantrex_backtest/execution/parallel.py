"""Parallel multi-instrument execution mode for Quantrex Backtest."""

import pickle
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from quantrex_core.logging import get_logger
from quantrex_core import InstrumentSpec
from quantrex_backtest.config import BacktestConfig
from quantrex_core.strategy.base import Strategy
from quantrex_backtest.results import BacktestResult
from quantrex_backtest.execution.base import ExecutionMode
from quantrex_backtest.execution.detector import ParallelismDetector
from quantrex_core.models.trade import TradeRecord

logger = get_logger(__name__)

_EXECUTION_LOG_DIR = "execution_log"


def _run_single_instrument_worker(
    instrument: InstrumentSpec,
    strategy_class: type[Strategy],
    strategy_init_kwargs: Dict[str, Any],
    config: BacktestConfig,
    backtest_start_local: datetime,
    staging_dir_path: str,
    raw_data: Dict[str, Dict[str, List[Dict]]],
    indicators: Dict[str, Dict[str, List[Dict]]],
    base_timeframe: str,
) -> Tuple[List[TradeRecord], List[tuple[datetime, float]]]:
    """Run backtest for a single instrument in a worker process.

    This function must be at module level for multiprocessing pickling.
    Runs sequentially (no parallel) to avoid recursive parallelism.

    Args:
        instrument: Single instrument to backtest
        strategy_class: Strategy class (not instance) to instantiate
        strategy_init_kwargs: Keyword arguments for strategy __init__
        config: Backtest configuration
        backtest_start_local: Backtest start timestamp (local timezone)
        staging_dir_path: Path to shared staging directory for log files
        raw_data: Raw data for this instrument
        indicators: Computed indicators for this instrument
        base_timeframe: Base timeframe

    Returns:
        Tuple of (trades, equity_curve) for this single instrument
    """
    # Import here to avoid circular imports
    from quantrex_backtest.core.portfolio_context import BacktestPortfolioContext
    from quantrex_core.position.manager import PositionManager
    from quantrex_core.order import OrderManagementSystem
    from quantrex_core.models import Candle
    from quantrex_backtest.core.timeframe import calculate_close_time
    from quantrex_backtest.data import DataOrchestrator
    from quantrex_backtest.exceptions.backtest_error import ProviderError

    # Create a new engine with just this instrument
    strategy = strategy_class(**strategy_init_kwargs)

    # Use the shared staging directory
    staging_dir = Path(staging_dir_path)

    # Set up logging for this symbol in the shared execution_log directory
    symbols = [instrument.symbol]

    # Create position manager and OMS for this worker
    position_manager = PositionManager()
    oms = OrderManagementSystem()

    # Create context
    origin_time = instrument.adapter.get_origin_time()
    context = BacktestPortfolioContext(
        position_manager=position_manager,
        oms=oms,
        current_time=datetime.min,
        instruments=symbols,
        initial_cash=config.initial_cash,
        margin_requirement=config.margin_requirement,
        raw_data_by_timeframe=raw_data,
        indicators_by_timeframe=indicators,
        base_timeframe=base_timeframe,
        origin_time=origin_time,
    )

    strategy.set_context(context)

    # Get base data for time index
    base_data = raw_data[instrument.symbol][base_timeframe]
    if not base_data:
        logger.warning("No base timeframe data for %s; backtest completed with zero candles", instrument.symbol)
        strategy.on_stop()
        return [], []

    # Sort base data by datetime
    base_data.sort(key=lambda row: row.get("datetime", ""))

    # Build datetime->row lookup
    symbol_tf_to_rows = {}
    symbol_tf_to_rows[instrument.symbol] = {}
    for tf in raw_data[instrument.symbol].keys():
        row_map = {}
        for row in raw_data[instrument.symbol][tf]:
            dt_val = row.get("datetime")
            if isinstance(dt_val, str):
                dt = datetime.strptime(dt_val, instrument.adapter.datetime_format)
            elif isinstance(dt_val, datetime):
                dt = dt_val
            else:
                continue
            row_map[dt] = row
        symbol_tf_to_rows[instrument.symbol][tf] = row_map

    # Main event loop
    data_start: str | None = None
    data_end: str | None = None
    equity_curve: List[tuple[datetime, float]] = []

    for idx, base_row in enumerate(base_data):
        try:
            timestamp = base_row.get("datetime")
            if isinstance(timestamp, str):
                ts = datetime.strptime(timestamp, instrument.adapter.datetime_format)
            else:
                ts = timestamp

            if data_start is None:
                data_start = ts.strftime("%Y%m%d_%H%M%S")
            data_end = ts.strftime("%Y%m%d_%H%M%S")

            # Create candle
            symbol_row = symbol_tf_to_rows[instrument.symbol][base_timeframe].get(ts)
            if symbol_row is None:
                continue

            candle_indicators = indicators[instrument.symbol].get(base_timeframe, [{}])[idx] if idx < len(indicators[instrument.symbol].get(base_timeframe, [])) else {}
            candle = Candle.from_row(
                symbol_row,
                instrument.symbol,
                instrument.adapter.datetime_format,
                indicators=candle_indicators,
            )

            # Drain pending orders at open price
            if oms.pending_count > 0:
                entries = oms.drain(candle.open, candle.timestamp)
                for entry in entries:
                    order = entry.order
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
                    position_manager._record_order(
                        symbol=order.symbol,
                        side=order.side,
                        quantity=order.quantity,
                        order_type=order.order_type,
                        timestamp=order.timestamp,
                        price=candle.open,
                    )
                    delta = order.quantity if order.side == order.side.BUY else -order.quantity
                    position_manager.apply(
                        order.symbol, delta, candle.timestamp, candle.open
                    )
                    logger.info(
                        "[%s %s] FILL id=%s side=%s qty=%s price=%s",
                        order.symbol,
                        candle.timestamp.isoformat(),
                        order.id,
                        order.side.value,
                        order.quantity,
                        candle.open,
                    )

            # Update context time with close time
            close_time = calculate_close_time(candle.timestamp, base_timeframe)
            context.update_time(close_time)

            # Update context and call strategy
            context.update_candle(candle)
            context.record_candle(candle)

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

            if any("on_candle" in cls.__dict__ for cls in strategy.__class__.__mro__ if cls is not Strategy):
                strategy.on_candle(candle)

            # Dispatch timeframe events for this symbol
            strategy.timeframe_dispatcher.dispatch_all(context, instrument.symbol)

            # Record equity curve point
            equity_curve.append((close_time, context.equity))

        except Exception as e:
            logger.exception("Failed to process candle at index %d for %s", idx, instrument.symbol)
            raise ProviderError(f"Failed to process candle at index {idx}: {e}") from e

    # Flush remaining pending orders at final close price
    if 'candle' in locals():
        last_close_time = calculate_close_time(candle.timestamp, base_timeframe)
        if oms.pending_count > 0:
            logger.warning(
                "%d order(s) still pending at final candle for %s — "
                "filling at close price %s as a last resort",
                oms.pending_count,
                instrument.symbol,
                candle.close,
            )
            entries = oms.drain(candle.close, last_close_time)
            for entry in entries:
                order = entry.order
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
                position_manager._record_order(
                    symbol=order.symbol,
                    side=order.side,
                    quantity=order.quantity,
                    order_type=order.order_type,
                    timestamp=order.timestamp,
                    price=candle.close,
                )
                delta = order.quantity if order.side == order.side.BUY else -order.quantity
                position_manager.apply(
                    order.symbol, delta, last_close_time, candle.close
                )
                logger.info(
                    "[%s %s] FILL id=%s side=%s qty=%s price=%s",
                    order.symbol,
                    last_close_time.isoformat(),
                    order.id,
                    order.side.value,
                    order.quantity,
                    candle.close,
                )

    strategy.on_stop()
    logger.info("Backtest completed for %s: %d candles processed", instrument.symbol, len(base_data))

    # Return raw data for merging in main process
    trades = position_manager.get_closed_trades()
    symbol_trades = [t for t in trades if t.symbol == instrument.symbol]

    return symbol_trades, equity_curve


class ParallelMultiExecution(ExecutionMode):
    """Multi-instrument parallel execution via ProcessPoolExecutor."""

    def __init__(
        self,
        data_orchestrator: Any,
        position_manager: Any,
        oms: Any,
        result_exporter: Any,
        run_logger: Any,
        directory_manager: Any,
        detector: ParallelismDetector,
    ):
        self._data_orchestrator = data_orchestrator
        self._position_manager = position_manager
        self._oms = oms
        self._result_exporter = result_exporter
        self._run_logger = run_logger
        self._directory_manager = directory_manager
        self._detector = detector

    def execute(
        self,
        instruments: List[InstrumentSpec],
        strategy: Strategy,
        config: BacktestConfig,
        context: Any,
        raw_data: Dict[str, Dict[str, List[Dict]]],
        indicators: Dict[str, Dict[str, List[Dict]]],
        symbol_to_adapter: Dict[str, Any],
        base_timeframe: str,
        staging_dir: Path,
        backtest_start_local: datetime,
    ) -> BacktestResult:
        """Execute multi-instrument parallel backtest."""
        # Check parallelism safety
        report = self._detector.analyze(strategy, instruments)
        if not report.safe:
            logger.info("Parallel execution not safe: %s. Falling back to sequential.", report.reason)
            # Fall back to sequential - this would be handled by the engine
            raise RuntimeError(f"Parallel execution not safe: {report.reason}")

        if not report.independent_groups:
            logger.info("No independent groups found. Falling back to sequential.")
            raise RuntimeError("No independent groups found")

        # Check if adapters are picklable
        try:
            for spec in instruments:
                pickle.dumps(spec.adapter)
        except (pickle.PicklingError, TypeError, AttributeError):
            logger.info("Adapters not picklable (likely test mocks). Falling back to sequential.")
            raise RuntimeError("Adapters not picklable")

        max_workers = config.effective_max_workers
        logger.info("Running parallel backtest with %d workers for %d instruments", max_workers, len(instruments))

        # Create the execution_log directory upfront
        exec_log_dir = staging_dir / _EXECUTION_LOG_DIR
        exec_log_dir.mkdir(parents=True, exist_ok=True)

        # Extract strategy init kwargs (assume default constructor for now)
        strategy_init_kwargs = {}

        all_trades: List[TradeRecord] = []
        all_equity_curves: List[List[tuple[datetime, float]]] = []
        symbols = [spec.symbol for spec in instruments]

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit tasks for each instrument
            future_to_symbol = {}
            for spec in instruments:
                # Prepare data for this instrument
                instrument_raw_data = {spec.symbol: raw_data[spec.symbol]}
                instrument_indicators = {spec.symbol: indicators[spec.symbol]}

                future = executor.submit(
                    _run_single_instrument_worker,
                    spec,
                    strategy.__class__,
                    strategy_init_kwargs,
                    config,
                    backtest_start_local,
                    str(staging_dir),
                    instrument_raw_data,
                    instrument_indicators,
                    base_timeframe,
                )
                future_to_symbol[future] = spec.symbol

            # Collect results
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    trades, equity_curve = future.result()
                    all_trades.extend(trades)
                    all_equity_curves.append(equity_curve)
                    logger.info("Completed backtest for %s", symbol)
                except Exception as e:
                    logger.exception("Worker failed for %s: %s", symbol, e)
                    raise

        # Merge equity curves
        merged_equity_curve = BacktestResult.merge_equity_curves(all_equity_curves, config.initial_cash)

        # Write aggregated CSV
        self._write_aggregated_trades_csv(staging_dir, all_trades)

        # Build minimal result
        final_equity = merged_equity_curve[-1][1] if merged_equity_curve else config.initial_cash

        return BacktestResult(
            trades=all_trades,
            equity_curve=merged_equity_curve,
            initial_cash=config.initial_cash,
            final_equity=final_equity,
            symbols=symbols,
        )

    def _write_aggregated_trades_csv(self, output_dir: Path, trades: List[TradeRecord]) -> None:
        """Write aggregated trades from all instruments to a single CSV."""
        import csv
        output_file = output_dir / "closed_trades.csv"

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

        logger.info("Exported %d aggregated closed trades to %s", len(trades), output_file)