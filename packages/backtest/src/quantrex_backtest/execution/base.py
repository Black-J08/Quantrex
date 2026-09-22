"""Execution mode base class for Quantrex Backtest."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from quantrex_core import InstrumentSpec
from quantrex_backtest.config import BacktestConfig
from quantrex_core.strategy.base import Strategy
from quantrex_backtest.results import BacktestResult


class ExecutionMode(ABC):
    """Abstract base class for backtest execution modes."""

    @abstractmethod
    def execute(
        self,
        instruments: List[InstrumentSpec],
        strategy: Strategy,
        config: BacktestConfig,
        context: Any,  # BacktestPortfolioContext
        raw_data: Dict[str, Dict[str, List[Dict]]],
        indicators: Dict[str, Dict[str, List[Dict]]],
        symbol_to_adapter: Dict[str, Any],
        base_timeframe: str,
        staging_dir: Any,  # Path
        backtest_start_local: Any,  # datetime
    ) -> BacktestResult:
        """Execute the backtest and return results.

        Args:
            instruments: List of instrument specifications
            strategy: Strategy instance to execute
            config: Backtest configuration
            context: Portfolio context (shared across instruments)
            raw_data: Raw data by symbol and timeframe
            indicators: Computed indicators by symbol and timeframe
            symbol_to_adapter: Map of symbol to data adapter
            base_timeframe: Base timeframe for synchronization
            staging_dir: Staging directory for logs
            backtest_start_local: Backtest start timestamp

        Returns:
            BacktestResult with trade log and equity curve
        """
        pass