"""Portfolio configuration types for Quantrex."""

from dataclasses import dataclass
from typing import Optional

from quantrex_core.protocols import DataAdapter
from .sizing import PositionSizer


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """Specification for a single instrument in a portfolio backtest.

    Attributes:
        symbol: Trading symbol (e.g., "COPPER", "AAPL").
        adapter: DataAdapter providing normalized market data for this symbol.
        data_path: Optional path to local data file for auto-download/caching.
        timeframe_overrides: Optional timeframe-specific configuration.
    """
    symbol: str
    adapter: DataAdapter
    data_path: Optional[str] = None
    timeframe_overrides: Optional[dict] = None


@dataclass(frozen=True, slots=True)
class PortfolioConfig:
    """Configuration for portfolio backtesting.

    Attributes:
        initial_cash: Starting cash balance for the portfolio.
        margin_requirement: Margin requirement as a multiplier (1.0 = no leverage, 2.0 = 2x leverage).
        position_sizer: Optional PositionSizer for portfolio-level allocation.
        data_start: Start date for data (ISO format "YYYY-MM-DD"). None = earliest available.
        data_end: End date for data (ISO format "YYYY-MM-DD"). None = latest available.
        auto_download: Whether to automatically download missing data via providers.
        validate_completeness: Whether to validate data completeness (minimum bars).
        min_bars_required: Minimum number of bars required for completeness check.
    """
    initial_cash: float = 1_000_000.0
    margin_requirement: float = 1.0
    position_sizer: Optional[PositionSizer] = None
    data_start: Optional[str] = None
    data_end: Optional[str] = None
    auto_download: bool = True
    validate_completeness: bool = True
    min_bars_required: int = 100