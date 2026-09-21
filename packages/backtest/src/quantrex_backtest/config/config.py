"""Backtest configuration for Quantrex Backtest.

Unified configuration combining portfolio-level and engine-specific settings.
"""

from dataclasses import dataclass
from typing import Optional

from quantrex_core.portfolio import PositionSizer


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Unified configuration for backtesting.

    Combines portfolio-level settings (initial_cash, margin_requirement,
    data_start, data_end) with engine-specific settings
    (max_workers, parallelism_enabled, export_trades, log_level).
    """

    # Portfolio settings
    initial_cash: float = 1_000_000.0
    margin_requirement: float = 1.0
    data_start: Optional[str] = None
    data_end: Optional[str] = None

    # Data validation settings
    auto_download: bool = True
    validate_completeness: bool = True
    min_bars_required: int = 100

    # Engine settings
    max_workers: int = 0
    parallelism_enabled: bool = True
    export_trades: bool = True
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if self.max_workers < 0:
            raise ValueError("max_workers must be >= 0")
        if self.min_bars_required < 1:
            raise ValueError("min_bars_required must be >= 1")
        if self.margin_requirement <= 0:
            raise ValueError("margin_requirement must be > 0")
        if self.initial_cash < 0:
            raise ValueError("initial_cash must be >= 0")

    @property
    def effective_max_workers(self) -> int:
        """Get effective worker count (auto-detect if 0)."""
        if self.max_workers > 0:
            return self.max_workers
        import os
        cpu_count = os.cpu_count() or 1
        return max(1, cpu_count // 2)