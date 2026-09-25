"""Forward Return models - Event, Series, and Result dataclasses."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide


@dataclass(frozen=True, slots=True)
class ForwardReturnEvent:
    """Research event emitted by a component.
    
    Attributes:
        symbol: Trading symbol.
        timestamp: Event timestamp (candle open time).
        direction: OrderSide.BUY for LONG, OrderSide.SELL for SHORT.
        metadata: Additional event metadata.
        candle: The candle at which the event was emitted (includes close_time, timeframe).
    """
    symbol: str
    timestamp: datetime
    direction: OrderSide
    metadata: Dict[str, any]
    candle: Candle


@dataclass(frozen=True, slots=True)
class ForwardReturnSeries:
    """Raw percentage forward returns for a single event across horizons.
    
    Attributes:
        event: The research event this series corresponds to.
        returns: Dictionary mapping horizon (timedelta) to percentage return (float) or None if incomplete.
    """
    event: ForwardReturnEvent
    returns: Dict[timedelta, Optional[float]]


@dataclass(frozen=True, slots=True)
class ForwardReturnResult:
    """Aggregated forward return statistics per horizon.
    
    Attributes:
        horizon_stats: Dictionary mapping horizon to statistics dict.
        raw_returns: Dictionary mapping horizon to list of raw percentage returns.
    """
    horizon_stats: Dict[timedelta, Dict[str, float]]
    raw_returns: Dict[timedelta, List[float]]
    
    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dictionary."""
        result = {}
        for horizon, stats in self.horizon_stats.items():
            horizon_key = str(horizon)
            result[horizon_key] = {
                "horizon": str(horizon),
                **stats,
                "raw_returns": self.raw_returns.get(horizon, []),
            }
        return result
    
    def get_horizon_stats(self, horizon: timedelta) -> Dict[str, float]:
        """Get statistics for a specific horizon."""
        return self.horizon_stats.get(horizon, {})
    
    def get_raw_returns(self, horizon: timedelta) -> List[float]:
        """Get raw returns for a specific horizon."""
        return self.raw_returns.get(horizon, [])