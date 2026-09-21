"""Quantrex Core Timeframe Module.

Public exports for the timeframe subsystem.
"""

from quantrex_core.timeframe.model import Timeframe
from quantrex_core.timeframe.parser import (
    parse_interval,
    interval_to_minutes,
    validate_interval,
    get_supported_units,
    ParsedInterval,
)
from quantrex_core.timeframe.arithmetic import (
    align_to_origin,
    get_interval_bounds,
    is_interval_complete,
    compare_timeframes,
    is_multiple_of,
    get_next_interval_start,
)
from quantrex_core.timeframe.filtering import (
    filter_candles_by_timeframe,
    filter_candles_by_timeframe_minutes,
)
from quantrex_core.timeframe.constants import (
    TF_1M,
    TF_3M,
    TF_5M,
    TF_10M,
    TF_15M,
    TF_30M,
    TF_1H,
    TF_2H,
    TF_4H,
    TF_1D,
    TF_1W,
    TF_1MONTH,
    INTRADAY_TIMEFRAMES,
    DAILY_TIMEFRAMES,
    WEEKLY_TIMEFRAMES,
    MONTHLY_TIMEFRAMES,
    ALL_STANDARD_TIMEFRAMES,
    get_standard_timeframes,
    get_intraday_timeframes,
)
from quantrex_core.timeframe.provider_mapping import (
    ProviderTimeframeMapper,
    ZerodhaTimeframeMapper,
    DhanTimeframeMapper,
    ZERODHA_MAPPER,
    DHAN_MAPPER,
    get_mapper,
)
from quantrex_core.timeframe.registry import TimeframeRegistry
from quantrex_core.timeframe.dispatcher import TimeframeDispatcher
from quantrex_core.timeframe.decorators import on_timeframe

__all__ = [
    # Model
    "Timeframe",
    # Parser
    "parse_interval",
    "interval_to_minutes",
    "validate_interval",
    "get_supported_units",
    "ParsedInterval",
    # Arithmetic
    "align_to_origin",
    "get_interval_bounds",
    "is_interval_complete",
    "compare_timeframes",
    "is_multiple_of",
    "get_next_interval_start",
    # Filtering
    "filter_candles_by_timeframe",
    "filter_candles_by_timeframe_minutes",
    # Constants
    "TF_1M",
    "TF_3M",
    "TF_5M",
    "TF_10M",
    "TF_15M",
    "TF_30M",
    "TF_1H",
    "TF_2H",
    "TF_4H",
    "TF_1D",
    "TF_1W",
    "TF_1MONTH",
    "INTRADAY_TIMEFRAMES",
    "DAILY_TIMEFRAMES",
    "WEEKLY_TIMEFRAMES",
    "MONTHLY_TIMEFRAMES",
    "ALL_STANDARD_TIMEFRAMES",
    "get_standard_timeframes",
    "get_intraday_timeframes",
    # Provider Mapping
    "ProviderTimeframeMapper",
    "ZerodhaTimeframeMapper",
    "DhanTimeframeMapper",
    "ZERODHA_MAPPER",
    "DHAN_MAPPER",
    "get_mapper",
    # Registry & Dispatcher
    "TimeframeRegistry",
    "TimeframeDispatcher",
    "on_timeframe",
]