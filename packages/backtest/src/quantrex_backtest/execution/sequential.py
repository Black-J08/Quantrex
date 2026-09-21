"""Sequential multi-instrument execution mode for Quantrex Backtest."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from quantrex_core.logging import get_logger
from quantrex_core.models import Candle
from quantrex_core.strategy.base import Strategy
from quantrex_core import InstrumentSpec, PortfolioConfig
from quantrex_backtest.results import PortfolioResult, SymbolResult
from quantrex_backtest.core.timeframe import calculate_close_time
from quantrex_backtest.data import DataOrchestrator
from quantrex_backtest.exceptions.backtest_error import ProviderError
from quantrex_backtest.execution.base import ExecutionMode

logger = get_logger(__name__)


class SequentialMultiExecution(ExecutionMode):
    """Multi-instrument sequential execution (unified event loop)."""

    def __init__(
        self,
        data_orchestrator: DataOrchestrator,
        position_manager: Any,
        oms: Any,
        result_exporter: Any,
        run_logger: Any,
        directory_manager: Any,
    ):
        self._data_orchestrator = data_orchestrator
        self._position_manager = position_manager
        self._oms = oms
        self._result_exporter = result_exporter
        self._run_logger = run_logger
        self._directory_manager = directory_manager

    def execute(
        self,
        instruments: List[InstrumentSpec],
        strategy: Strategy,
        config: PortfolioConfig,
        engine_config: Any,
        context: Any,
        raw_data: Dict[str, Dict[str, List[Dict]]],
        indicators: Dict[str, Dict[str, List[Dict]]],
        symbol_to_adapter: Dict[str, Any],
        base_timeframe: str,
        staging_dir: Path,
        backtest_start_local: datetime,
    ) -> PortfolioResult:
        """Execute multi-instrument sequential backtest."""
        symbols = [spec.symbol for spec in instruments]

        # Set up logging for all symbols
        self._run_logger.ensure_run_log_file(staging_dir, symbols)

        # Create context for all instruments
        origin_time = instruments[0].adapter.get_origin_time()
        context = self._create_context(
            instruments=symbols,
            origin_time=origin_time,
            raw_data=raw_data,
            indicators=indicators,
            base_timeframe=base_timeframe,
            config=config,
        )

        # Set symbol and datetime format for each instrument
        for spec in instruments:
            context.strategy_context.set_symbol_and_format(spec.symbol, spec.adapter.datetime_format)
        strategy.set_context(context)

        # Get base data for time index (use first symbol as reference)
        base_data = raw_data[symbols[0]][base_timeframe]
        if not base_data:
            logger.warning("No base timeframe data; backtest completed with zero candles")
            strategy.on_stop()
            self._result_exporter.export_trades_csv([], staging_dir)
            return PortfolioResult.empty(config.initial_cash)

        # Sort base data by datetime
        base_data.sort(key=lambda row: row.get("datetime", ""))

        # Build datetime->row lookup
        required_timeframes = list(raw_data[symbols[0]].keys())
        symbol_tf_to_rows = self._build_row_lookup(
            symbols=symbols,
            raw_data=raw_data,
            required_timeframes=required_timeframes,
            symbol_to_adapter=symbol_to_adapter,
        )

        # Main event loop
        data_start: str | None = None
        data_end: str | None = None
        equity_curve: List[tuple[datetime, float]] = []

        for idx, base_row in enumerate(base_data):
            try:
                timestamp = base_row.get("datetime")
                if isinstance(timestamp, str):
                    base_adapter = symbol_to_adapter[symbols[0]]
                    ts = datetime.strptime(timestamp, base_adapter.datetime_format)
                else:
                    ts = timestamp

                if data_start is None:
                    data_start = ts.strftime("%Y%m%d_%H%M%S")
                data_end = ts.strftime("%Y%m%d_%H%M%S")

                # Create candles for all symbols at this timestamp
                candles = {}
                for symbol in symbols:
                    symbol_row = symbol_tf_to_rows[symbol][base_timeframe].get(ts)
                    if symbol_row is None:
                        continue

                    symbol_adapter = symbol_to_adapter[symbol]
                    candle_indicators = indicators[symbol].get(base_timeframe, [{}])[idx] if idx < len(indicators[symbol].get(base_timeframe, [])) else {}
                    candle = Candle.from_row(
                        symbol_row,
                        symbol,
                        symbol_adapter.datetime_format,
                        indicators=candle_indicators,
                    )
                    candles[symbol] = candle

                # Drain pending orders at open prices
                for symbol, candle in candles.items():
                    self._drain_pending(candle.open, candle.timestamp, symbol=symbol)

                # Update context time with close time
                close_time = calculate_close_time(candle.timestamp, base_timeframe)
                context.update_time(close_time)

                # Update context with each candle and call strategy
                for symbol, candle in candles.items():
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

                # Dispatch timeframe events
                strategy.timeframe_dispatcher.dispatch_all(context)

                # Record equity curve point
                equity_curve.append((close_time, context.equity))

            except Exception as e:
                logger.exception("Failed to process candle at index %d", idx)
                raise ProviderError(f"Failed to process candle at index {idx}: {e}") from e

        # Flush remaining pending orders at final close price
        if candles:
            last_candle = list(candles.values())[0]
            last_close_time = calculate_close_time(last_candle.timestamp, base_timeframe)
            self._drain_pending(last_candle.close, last_close_time, is_final=True)

        strategy.on_stop()
        logger.info("Backtest completed: %d candles processed", len(base_data))

        # Parse dates
        data_start_dt = datetime.strptime(data_start, "%Y%m%d_%H%M%S") if data_start else None
        data_end_dt = datetime.strptime(data_end, "%Y%m%d_%H%M%S") if data_end else None

        # Promote staging -> final run dir
        final_run_dir = self._directory_manager.build_run_dir(
            backtest_start_local, data_start_dt, data_end_dt, type(strategy).__name__
        )
        if final_run_dir != staging_dir:
            run_dir = self._directory_manager.promote_staging_to_final(
                staging_dir, final_run_dir, symbols, self._run_logger
            )
        else:
            run_dir = staging_dir

        # Export trades
        self._result_exporter.export_trades_csv(
            self._position_manager.get_closed_trades(), run_dir
        )
        logger.info("Run log: %s", run_dir / "execution_log")

        # Build PortfolioResult
        return self._build_portfolio_result(
            symbols=symbols,
            equity_curve=equity_curve,
            initial_cash=config.initial_cash,
            data_start_dt=data_start_dt,
            data_end_dt=data_end_dt,
        )

    def _create_context(
        self,
        instruments: List[str],
        origin_time: Any,
        raw_data: Dict[str, Dict[str, List[Dict]]],
        indicators: Dict[str, Dict[str, List[Dict]]],
        base_timeframe: str,
        config: PortfolioConfig,
    ) -> Any:
        """Create portfolio context."""
        from quantrex_backtest.core.portfolio_context import BacktestPortfolioContext
        return BacktestPortfolioContext(
            position_manager=self._position_manager,
            oms=self._oms,
            current_time=datetime.min,
            instruments=instruments,
            initial_cash=config.initial_cash,
            margin_requirement=config.margin_requirement,
            raw_data_by_timeframe=raw_data,
            indicators_by_timeframe=indicators,
            base_timeframe=base_timeframe,
            origin_time=origin_time,
        )

    def _build_row_lookup(
        self,
        symbols: List[str],
        raw_data: Dict[str, Dict[str, List[Dict]]],
        required_timeframes: List[str],
        symbol_to_adapter: Dict[str, Any],
    ) -> Dict[str, Dict[str, Dict[datetime, Dict]]]:
        """Build datetime->row lookup maps."""
        symbol_tf_to_rows = {}
        for symbol in symbols:
            symbol_tf_to_rows[symbol] = {}
            for tf in required_timeframes:
                row_map = {}
                adapter = symbol_to_adapter[symbol]
                for row in raw_data[symbol][tf]:
                    dt_val = row.get("datetime")
                    if isinstance(dt_val, str):
                        dt = datetime.strptime(dt_val, adapter.datetime_format)
                    elif isinstance(dt_val, datetime):
                        dt = dt_val
                    else:
                        continue
                    row_map[dt] = row
                symbol_tf_to_rows[symbol][tf] = row_map
        return symbol_tf_to_rows

    def _drain_pending(
        self,
        execution_price: float,
        execution_timestamp: datetime,
        is_final: bool = False,
        symbol: str | None = None,
    ) -> None:
        """Drain all pending orders from the OMS."""
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
            if symbol is not None and order.symbol != symbol:
                self._oms.submit(order, entry.fill_price, entry.fill_timestamp)
                continue

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
            delta = order.quantity if order.side == order.side.BUY else -order.quantity
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

    def _build_portfolio_result(
        self,
        symbols: List[str],
        equity_curve: List[tuple[datetime, float]],
        initial_cash: float,
        data_start_dt: datetime | None,
        data_end_dt: datetime | None,
    ) -> PortfolioResult:
        """Build PortfolioResult from equity curve and trades."""
        all_trades = self._position_manager.get_closed_trades()

        final_equity = equity_curve[-1][1] if equity_curve else initial_cash
        total_return = final_equity - initial_cash
        total_return_pct = (total_return / initial_cash * 100) if initial_cash > 0 else 0.0

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

        total_trades = len(all_trades)
        winning_trades = sum(1 for t in all_trades if t.pnl > 0)
        losing_trades = sum(1 for t in all_trades if t.pnl < 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        gross_profit = sum(t.pnl for t in all_trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in all_trades if t.pnl < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

        symbol_results = {}
        for symbol in symbols:
            symbol_trades = [t for t in all_trades if t.symbol == symbol]

            symbol_total_trades = len(symbol_trades)
            symbol_winning_trades = sum(1 for t in symbol_trades if t.pnl > 0)
            symbol_losing_trades = sum(1 for t in symbol_trades if t.pnl < 0)
            symbol_win_rate = (symbol_winning_trades / symbol_total_trades * 100) if symbol_total_trades > 0 else 0.0

            symbol_gross_profit = sum(t.pnl for t in symbol_trades if t.pnl > 0)
            symbol_gross_loss = abs(sum(t.pnl for t in symbol_trades if t.pnl < 0))
            symbol_profit_factor = (symbol_gross_profit / symbol_gross_loss) if symbol_gross_loss > 0 else None

            symbol_position = self._position_manager.get_position(symbol)

            symbol_results[symbol] = SymbolResult(
                symbol=symbol,
                trades=symbol_trades,
                final_position=symbol_position,
                total_trades=symbol_total_trades,
                winning_trades=symbol_winning_trades,
                losing_trades=symbol_losing_trades,
                total_pnl=sum(t.pnl for t in symbol_trades),
                max_drawdown=max_drawdown,
                sharpe_ratio=None,
            )

        return PortfolioResult(
            initial_cash=initial_cash,
            final_equity=final_equity,
            total_return=total_return,
            total_return_pct=total_return_pct,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=None,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            per_symbol=symbol_results,
            equity_curve=equity_curve,
            start_date=data_start_dt,
            end_date=data_end_dt,
            symbols=symbols,
        )