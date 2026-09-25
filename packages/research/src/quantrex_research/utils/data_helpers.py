"""Shared pandas/numpy utilities for research components."""

from datetime import timedelta
from typing import Dict, List

import pandas as pd

from quantrex_core.models import Candle


def merge_candle_streams(symbol_candles: Dict[str, List[Candle]]) -> List[Candle]:
    """Merge multiple symbol candle streams into a single time-ordered stream.
    
    Args:
        symbol_candles: Dictionary mapping symbol to list of candles.
        
    Returns:
        Single list of candles sorted by timestamp.
    """
    all_candles = []
    for symbol, candles in symbol_candles.items():
        all_candles.extend(candles)
    
    # Sort by timestamp (open time)
    all_candles.sort(key=lambda c: c.timestamp)
    return all_candles


def timedelta_to_bars(horizon: timedelta, base_timeframe_minutes: int = 1) -> int:
    """Convert a timedelta horizon to number of base timeframe bars.
    
    Args:
        horizon: Time horizon as timedelta.
        base_timeframe_minutes: Base timeframe in minutes (default 1M = 1 minute).
        
    Returns:
        Number of base timeframe bars in the horizon.
    """
    total_minutes = horizon.total_seconds() / 60
    return int(round(total_minutes / base_timeframe_minutes))


def timedelta_to_bars_list(horizons: List[timedelta], base_timeframe_minutes: int = 1) -> List[int]:
    """Convert a list of timedelta horizons to bar counts.
    
    Args:
        horizons: List of timedelta horizons.
        base_timeframe_minutes: Base timeframe in minutes.
        
    Returns:
        List of bar counts corresponding to each horizon.
    """
    return [timedelta_to_bars(h, base_timeframe_minutes) for h in horizons]