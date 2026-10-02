"""Timeframe model for the trading framework."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum


class TimeframeUnit(Enum):
    """Timeframe unit enumeration."""

    SECOND = "s"
    MINUTE = "m"
    HOUR = "h"
    DAY = "d"
    WEEK = "w"
    MONTH = "M"


@dataclass(slots=True, kw_only=True, frozen=True)
class Timeframe:
    """Timeframe representation for market data.

    Attributes:
        value: Numeric value (e.g., 1, 5, 15).
        unit: Time unit (second, minute, hour, day, week, month).
    """

    value: int
    unit: TimeframeUnit

    def __post_init__(self) -> None:
        """Validate timeframe fields."""
        if self.value <= 0:
            raise ValueError("value must be positive")

    def __str__(self) -> str:
        """Return string representation (e.g., '1m', '5m', '1h', '1d')."""
        return f"{self.value}{self.unit.value}"

    @classmethod
    def from_string(cls, s: str) -> Timeframe:
        """Parse timeframe from string (e.g., '1m', '5m', '1h', '1d')."""
        if not s:
            raise ValueError("timeframe string cannot be empty")
        
        # Find the first non-digit character
        for i, ch in enumerate(s):
            if not ch.isdigit():
                value_str = s[:i]
                unit_str = s[i:]
                break
        else:
            raise ValueError(f"invalid timeframe format: {s}")
        
        if not value_str:
            raise ValueError(f"invalid timeframe format: {s}")
        
        try:
            value = int(value_str)
        except ValueError:
            raise ValueError(f"invalid timeframe value: {value_str}")
        
        try:
            unit = TimeframeUnit(unit_str)
        except ValueError:
            raise ValueError(f"invalid timeframe unit: {unit_str}")
        
        return cls(value=value, unit=unit)

    def to_timedelta(self) -> timedelta:
        """Convert to timedelta (approximate for months/weeks)."""
        multipliers = {
            TimeframeUnit.SECOND: 1,
            TimeframeUnit.MINUTE: 60,
            TimeframeUnit.HOUR: 3600,
            TimeframeUnit.DAY: 86400,
            TimeframeUnit.WEEK: 604800,
            TimeframeUnit.MONTH: 2592000,  # 30 days approximate
        }
        seconds = self.value * multipliers[self.unit]
        return timedelta(seconds=seconds)

    def __lt__(self, other: Timeframe) -> bool:
        """Compare timeframes by total seconds."""
        if not isinstance(other, Timeframe):
            return NotImplemented
        return self.to_timedelta() < other.to_timedelta()

    def __le__(self, other: Timeframe) -> bool:
        return self == other or self < other

    def __gt__(self, other: Timeframe) -> bool:
        if not isinstance(other, Timeframe):
            return NotImplemented
        return self.to_timedelta() > other.to_timedelta()

    def __ge__(self, other: Timeframe) -> bool:
        return self == other or self > other