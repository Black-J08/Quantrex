"""Common timeframe constants for Quantrex framework.

Predefined Timeframe instances for commonly used intervals.
"""

from quantrex_core.timeframe.model import Timeframe

# Minute-based timeframes
TF_1M = Timeframe("1M")
TF_3M = Timeframe("3M")
TF_5M = Timeframe("5M")
TF_10M = Timeframe("10M")
TF_15M = Timeframe("15M")
TF_30M = Timeframe("30M")

# Hour-based timeframes
TF_1H = Timeframe("1H")
TF_2H = Timeframe("2H")
TF_4H = Timeframe("4H")

# Day-based timeframes
TF_1D = Timeframe("1D")

# Week-based timeframes
TF_1W = Timeframe("1W")

# Month-based timeframes
TF_1MONTH = Timeframe("1MONTH")

# Commonly used sets for convenience
INTRADAY_TIMEFRAMES = (TF_1M, TF_3M, TF_5M, TF_10M, TF_15M, TF_30M, TF_1H, TF_2H, TF_4H)
DAILY_TIMEFRAMES = (TF_1D,)
WEEKLY_TIMEFRAMES = (TF_1W,)
MONTHLY_TIMEFRAMES = (TF_1MONTH,)

ALL_STANDARD_TIMEFRAMES = INTRADAY_TIMEFRAMES + DAILY_TIMEFRAMES + WEEKLY_TIMEFRAMES + MONTHLY_TIMEFRAMES


def get_standard_timeframes() -> tuple[Timeframe, ...]:
    """Get all standard timeframe constants.

    Returns:
        Tuple of all predefined Timeframe instances.
    """
    return ALL_STANDARD_TIMEFRAMES


def get_intraday_timeframes() -> tuple[Timeframe, ...]:
    """Get intraday timeframe constants.

    Returns:
        Tuple of intraday Timeframe instances.
    """
    return INTRADAY_TIMEFRAMES