"""Portfolio specification types for Quantrex."""

from dataclasses import dataclass
from typing import Optional

from quantrex_core.protocols import DataAdapter


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