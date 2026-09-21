"""Quantrex Backtest Engine - Minimal public API."""

from quantrex_core import InstrumentSpec
from .core.engine import BacktestEngine
from .config import BacktestConfig
from .exceptions.backtest_error import BacktestError, ProviderError
from .core import BacktestPortfolioContext
from .results import PortfolioResult, SymbolResult, SingleInstrumentResult
from .data import DataOrchestrator, DataOrchestratorConfig
from .execution import ParallelismDetector, ParallelismReport

__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "BacktestError",
    "ProviderError",
    "BacktestPortfolioContext",
    "PortfolioResult",
    "SymbolResult",
    "SingleInstrumentResult",
    "DataOrchestrator",
    "DataOrchestratorConfig",
    "ParallelismDetector",
    "ParallelismReport",
    "InstrumentSpec",
]