"""Timeframe dispatch registry for Quantrex framework.

Provides @on_timeframe decorator and TimeframeDispatcher for
multi-timeframe strategy support.

This module re-exports from quantrex_core.timeframe for backward compatibility.
"""

from quantrex_core.timeframe.registry import TimeframeRegistry
from quantrex_core.timeframe.dispatcher import TimeframeDispatcher
from quantrex_core.timeframe.decorators import on_timeframe

__all__ = [
    "TimeframeRegistry",
    "TimeframeDispatcher",
    "on_timeframe",
]