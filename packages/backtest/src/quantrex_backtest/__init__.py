"""Quantrex Backtest Engine - Minimal public API."""

from quantrex_core import InstrumentSpec, PortfolioConfig
from .core.engine import BacktestEngine
from .exceptions.backtest_error import BacktestError, ProviderError
from .portfolio import BacktestPortfolioContext, PortfolioResult, SymbolResult
from .data import DataOrchestrator, DataOrchestratorConfig

__all__ = [
    "BacktestEngine",
    "BacktestError",
    "ProviderError",
    "BacktestPortfolioContext",
    "PortfolioResult",
    "SymbolResult",
    "DataOrchestrator",
    "DataOrchestratorConfig",
    "InstrumentSpec",
    "PortfolioConfig",
]