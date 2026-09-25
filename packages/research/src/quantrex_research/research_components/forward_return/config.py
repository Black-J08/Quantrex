"""ForwardReturnConfig - Configuration for forward return distribution analysis."""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional


@dataclass(frozen=True, slots=True)
class ForwardReturnConfig:
    """Configuration for forward return distribution analysis.
    
    Attributes:
        horizons: List of forward-return horizons as timedeltas.
        boundary_handling: How to handle events near data boundaries.
            "nan" - Return NaN for incomplete horizons (default).
            "drop" - Drop events where any horizon exceeds data.
        missing_data_handling: How to handle missing candles in data.
            "skip" - Skip gaps, calculate across available bars (default).
            "require_continuous" - Require continuous data, raise on gaps.
        base_timeframe_minutes: Base timeframe in minutes for bar conversion (default 1M = 1 minute).
    """
    horizons: List[timedelta]
    boundary_handling: str = "nan"
    missing_data_handling: str = "skip"
    base_timeframe_minutes: int = 1
    
    def __post_init__(self) -> None:
        if not self.horizons:
            raise ValueError("horizons must not be empty")
        if any(h <= timedelta(0) for h in self.horizons):
            raise ValueError("All horizons must be positive timedeltas")
        if self.boundary_handling not in ("nan", "drop"):
            raise ValueError(f"Invalid boundary_handling: {self.boundary_handling}. Must be 'nan' or 'drop'")
        if self.missing_data_handling not in ("skip", "require_continuous"):
            raise ValueError(f"Invalid missing_data_handling: {self.missing_data_handling}. Must be 'skip' or 'require_continuous'")
        if self.base_timeframe_minutes <= 0:
            raise ValueError("base_timeframe_minutes must be positive")
    
    @property
    def horizon_bars(self) -> List[int]:
        """Convert horizons to bar counts based on base timeframe."""
        from quantrex_research.utils.data_helpers import timedelta_to_bars_list
        return timedelta_to_bars_list(self.horizons, self.base_timeframe_minutes)