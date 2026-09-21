"""Execution mode base class for Quantrex Backtest."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from quantrex_core import InstrumentSpec, PortfolioConfig
from quantrex_core.strategy.base import Strategy
from quantrex_backtest.results import SingleInstrumentResult, PortfolioResult


class ExecutionMode(ABC):
    """Abstract base class for backtest execution modes."""

    @abstractmethod
    def execute(
        self,
        instruments: List[InstrumentSpec],
        strategy: Strategy,
        config: PortfolioConfig,
        engine_config: Any,  # EngineConfig
        context: Any,  # BacktestPortfolioContext
        raw_data: Dict[str, Dict[str, List[Dict]]],
        indicators: Dict[str, Dict[str, List[Dict]]],
        symbol_to_adapter: Dict[str, Any],
        base_timeframe: str,
        staging_dir: Any,  # Path
        backtest_start_local: Any,  # datetime
    ) -> PortfolioResult:
        """Execute the backtest and return results.

        Args:
            instruments: List of instrument specifications
            strategy: Strategy instance to execute
            config: Portfolio configuration
            engine_config: Engine-specific configuration
            context: Portfolio context (shared across instruments)
            raw_data: Raw data by symbol and timeframe
            indicators: Computed indicators by symbol and timeframe
            symbol_to_adapter: Map of symbol to data adapter
            base_timeframe: Base timeframe for synchronization
            staging_dir: Staging directory for logs
            backtest_start_local: Backtest start timestamp

        Returns:
            PortfolioResult with backtest results
        """
        pass