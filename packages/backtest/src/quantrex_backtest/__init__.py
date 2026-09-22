"""Quantrex Backtest Engine - Minimal public API."""

from quantrex_core import InstrumentSpec
from .core.engine import BacktestEngine
from .config import BacktestConfig
from .exceptions.backtest_error import BacktestError, ProviderError
from .core import BacktestPortfolioContext
from .results import BacktestResult
from .data import DataOrchestrator, DataOrchestratorConfig
from .execution import ParallelismDetector, ParallelismReport

__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "BacktestError",
    "ProviderError",
    "BacktestPortfolioContext",
    "BacktestResult",
    "DataOrchestrator",
    "DataOrchestratorConfig",
    "ParallelismDetector",
    "ParallelismReport",
    "InstrumentSpec",
]