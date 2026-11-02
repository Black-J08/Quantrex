"""Shoonya-internal data models."""

from __future__ import annotations

from enum import Enum


class ShoonyaInterval(str, Enum):
    """Shoonya historical data intervals.

    Maps Quantrex Timeframe values to Shoonya API interval values.
    TPSeries supports intraday intervals: 1, 3, 5, 10, 15, 30, 60, 120, 240 minutes.
    EODChartData is used for daily (1D) data.
    """

    MINUTE_1 = "1"
    MINUTE_3 = "3"
    MINUTE_5 = "5"
    MINUTE_10 = "10"
    MINUTE_15 = "15"
    MINUTE_30 = "30"
    MINUTE_60 = "60"
    MINUTE_120 = "120"
    MINUTE_240 = "240"
    DAY = "1D"
