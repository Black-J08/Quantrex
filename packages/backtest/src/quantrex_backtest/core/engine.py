"""Backtest engine core orchestration."""

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from quantrex_core.logging import get_logger
from quantrex_core.models import Candle
from quantrex_core.strategy.base import Strategy
from quantrex_core.order import OrderManagementSystem
from quantrex_core.position.manager import PositionManager
from quantrex_core import InstrumentSpec
from quantrex_backtest.config import BacktestConfig
from quantrex_backtest.data import DataOrchestrator, DataOrchestratorConfig
from quantrex_backtest.core import BacktestPortfolioContext, calculate_close_time
from quantrex_backtest.execution import (
    ExecutionMode,
    SingleInstrumentExecution,
    SequentialMultiExecution,
    ParallelMultiExecution,
    ParallelismDetector,
)
from quantrex_backtest.observability import RunLogger, RunDirectoryManager
from quantrex_backtest.results import ResultExporter
from quantrex_backtest.exceptions.backtest_error import ProviderError
from quantrex_backtest.results import BacktestResult

logger = get_logger(__name__)


class BacktestEngine:
    """Deterministic event-driven backtest engine.

    Processes OHLCV candles sequentially in timestamp order,
    invoking a strategy's lifecycle methods for each candle.

    Supports portfolio backtesting through a unified API.

    Example (portfolio):
        >>> from quantrex_backtest import InstrumentSpec, BacktestConfig
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
        >>> config = BacktestConfig(initial_cash=1_000_000)
        >>> strategy = MyStrategy()
        >>> engine = BacktestEngine(instruments, strategy, config)
        >>> result = engine.run()
    """

    def __init__(
        self,
        instruments: List[InstrumentSpec],
        strategy: Strategy,
        config: BacktestConfig,
    ) -> None:
        """Initialize the backtest engine in portfolio mode.

        Args:
            instruments: List of InstrumentSpec defining symbols and their data adapters
            strategy: Strategy instance to execute
            config: BacktestConfig with portfolio and engine settings

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

        # Data orchestrator
        self._data_orchestrator = DataOrchestrator(DataOrchestratorConfig(
            exchange_calendar="NSE",
            auto_download=self._config.auto_download,
            validate_completeness=self._config.validate_completeness,
            min_bars_required=self._config.min_bars_required,
        ))

        # Observability components
        self._run_logger = RunLogger()
        self._directory_manager = RunDirectoryManager()
        self._result_exporter = ResultExporter()

        # Execution components
        self._parallelism_detector = ParallelismDetector()
        self._single_execution = SingleInstrumentExecution(
            data_orchestrator=self._data_orchestrator,
            position_manager=self._position_manager,
            oms=self._oms,
            result_exporter=self._result_exporter,
            run_logger=self._run_logger,
            directory_manager=self._directory_manager,
        )
        self._sequential_execution = SequentialMultiExecution(
            data_orchestrator=self._data_orchestrator,
            position_manager=self._position_manager,
            oms=self._oms,
            result_exporter=self._result_exporter,
            run_logger=self._run_logger,
            directory_manager=self._directory_manager,
        )
        self._parallel_execution = ParallelMultiExecution(
            data_orchestrator=self._data_orchestrator,
            position_manager=self._position_manager,
            oms=self._oms,
            result_exporter=self._result_exporter,
            run_logger=self._run_logger,
            directory_manager=self._directory_manager,
            detector=self._parallelism_detector,
        )

    def _detect_parallelism(self):
        """Detect parallelism safety for the current strategy and instruments.
        
        This method is exposed for testing purposes.
        """
        return self._parallelism_detector.analyze(self._strategy, self._instruments)

    def run(self) -> BacktestResult:
        """Run the backtest, invoking the strategy's lifecycle methods.

        Calls strategy.on_start(), then strategy.on_candle() for each candle
        in timestamp order, then strategy.on_stop().
        After completion, exports closed trades to CSV and returns BacktestResult.

        For single instrument: runs directly in current process.
        For multiple instruments: detects parallelism safety, runs parallel if safe,
        otherwise falls back to sequential execution.

        Returns:
            BacktestResult with trade log and equity curve.

        Raises:
            ProviderError: If adapter.read() fails or returns invalid data.
        """
        backtest_start_local = datetime.now()  # Local timezone

        # Build a staging run directory
        staging_dir = self._directory_manager.build_run_dir(
            backtest_start_local, None, None, type(self._strategy).__name__
        )
        staging_dir.mkdir(parents=True, exist_ok=True)
        symbols = [spec.symbol for spec in self._instruments]
        self._run_logger.ensure_run_log_file(staging_dir, symbols)

        logger.info("Starting backtest for %d instrument(s)", len(self._instruments))

        self._strategy.on_start()

        # Step 1: Get required timeframes
        required_timeframes = self._get_required_timeframes()
        base_timeframe = required_timeframes[0]

        # Step 2: Use DataOrchestrator to prepare validated, synchronized base timeframe data
        logger.info("Preparing data for %d instrument(s) using DataOrchestrator", len(self._instruments))
        try:
            synchronized_base_data = self._data_orchestrator.validate_and_prepare(
                self._instruments,
                self._config,
            )
        except ValueError as e:
            raise ProviderError(f"Failed to read data: {e}") from e

        if not synchronized_base_data:
            logger.warning("No data available for any instrument; backtest completed with zero candles")
            self._strategy.on_stop()
            if self._config.export_trades:
                self._result_exporter.export_trades_csv([], staging_dir)
            logger.info("Run log: %s", staging_dir / "execution_log")
            return BacktestResult.empty(self._config.initial_cash, symbols)

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
                    all_raw_data[symbol][tf] = spec.adapter.read_timeframe(
                        tf,
                        from_date=self._config.data_start,
                        to_date=self._config.data_end,
                    )
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

        # Sort all raw data by datetime for each symbol and timeframe
        # This ensures compute_indicators receives time-ordered data
        for symbol in all_raw_data:
            for tf in all_raw_data[symbol]:
                adapter = self._symbol_to_adapter[symbol]
                all_raw_data[symbol][tf].sort(
                    key=lambda row: datetime.strptime(row.get("datetime", ""), adapter.datetime_format)
                    if isinstance(row.get("datetime"), str) else row.get("datetime", datetime.min)
                )

        # Step 4: Compute indicators for each instrument and timeframe
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

        # Step 5: Select and execute the appropriate execution mode
        try:
            if len(self._instruments) == 1:
                logger.info("Single instrument, running sequentially.")
                return self._single_execution.execute(
                    instruments=self._instruments,
                    strategy=self._strategy,
                    config=self._config,
                    context=None,  # Will be created inside
                    raw_data=all_raw_data,
                    indicators=all_indicators,
                    symbol_to_adapter=self._symbol_to_adapter,
                    base_timeframe=base_timeframe,
                    staging_dir=staging_dir,
                    backtest_start_local=backtest_start_local,
                )

            # Multiple instruments: detect parallelism
            if self._config.parallelism_enabled:
                report = self._parallelism_detector.analyze(self._strategy, self._instruments)

                if report.safe and report.independent_groups:
                    # Check if adapters are picklable
                    try:
                        for spec in self._instruments:
                            import pickle
                            pickle.dumps(spec.adapter)
                    except (pickle.PicklingError, TypeError, AttributeError):
                        logger.info("Adapters not picklable (likely test mocks). Running sequentially.")
                        return self._sequential_execution.execute(
                            instruments=self._instruments,
                            strategy=self._strategy,
                            config=self._config,
                            context=None,
                            raw_data=all_raw_data,
                            indicators=all_indicators,
                            symbol_to_adapter=self._symbol_to_adapter,
                            base_timeframe=base_timeframe,
                            staging_dir=staging_dir,
                            backtest_start_local=backtest_start_local,
                        )

                    logger.info("Running parallel backtest with %d workers for %d instruments",
                                self._config.effective_max_workers, len(self._instruments))
                    try:
                        return self._parallel_execution.execute(
                            instruments=self._instruments,
                            strategy=self._strategy,
                            config=self._config,
                            context=None,
                            raw_data=all_raw_data,
                            indicators=all_indicators,
                            symbol_to_adapter=self._symbol_to_adapter,
                            base_timeframe=base_timeframe,
                            staging_dir=staging_dir,
                            backtest_start_local=backtest_start_local,
                        )
                    except RuntimeError as e:
                        logger.info("Parallel execution failed: %s. Falling back to sequential.", e)

            # Fallback to sequential
            logger.info("Running sequentially.")
            return self._sequential_execution.execute(
                instruments=self._instruments,
                strategy=self._strategy,
                config=self._config,
                context=None,
                raw_data=all_raw_data,
                indicators=all_indicators,
                symbol_to_adapter=self._symbol_to_adapter,
                base_timeframe=base_timeframe,
                staging_dir=staging_dir,
                backtest_start_local=backtest_start_local,
            )

        except Exception as e:
            logger.exception("Backtest failed")
            raise

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