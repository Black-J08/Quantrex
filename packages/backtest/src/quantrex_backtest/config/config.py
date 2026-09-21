"""Engine configuration for Quantrex Backtest."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True, slots=True)
class EngineConfig:
    """Configuration for BacktestEngine behavior.

    Separates engine-specific settings from portfolio configuration.
    """

    # Parallelism settings
    max_workers: int = 0  # 0 = auto (half of CPU cores)
    parallelism_enabled: bool = True

    # Data settings (can override PortfolioConfig)
    auto_download: Optional[bool] = None
    validate_completeness: Optional[bool] = None
    min_bars_required: Optional[int] = None

    # Output settings
    export_trades: bool = True

    # Logging
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if self.max_workers < 0:
            raise ValueError("max_workers must be >= 0")
        if self.min_bars_required is not None and self.min_bars_required < 1:
            raise ValueError("min_bars_required must be >= 1")

    @property
    def effective_max_workers(self) -> int:
        """Get effective worker count (auto-detect if 0)."""
        if self.max_workers > 0:
            return self.max_workers
        import os
        cpu_count = os.cpu_count() or 1
        return max(1, cpu_count // 2)