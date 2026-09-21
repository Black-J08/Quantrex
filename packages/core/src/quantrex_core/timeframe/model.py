"""Timeframe model for Quantrex framework.

Immutable value object representing a timeframe interval.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Timeframe:
    """Immutable timeframe interval.

    Uses string representation (e.g., "1H", "1D", "4H", "15M") for flexibility.
    No enum to allow arbitrary intervals without framework changes.
    """

    interval: str

    def __post_init__(self) -> None:
        if not self.interval or not isinstance(self.interval, str):
            raise ValueError("Timeframe interval must be a non-empty string")

    def __str__(self) -> str:
        return self.interval

    def __hash__(self) -> int:
        return hash(self.interval)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Timeframe):
            return NotImplemented
        return self.interval == other.interval

    def to_minutes(self) -> int:
        """Convert timeframe interval to total minutes.

        Returns:
            Total minutes for this timeframe interval.

        Raises:
            ValueError: If interval format is invalid.
        """
        from quantrex_core.timeframe.parser import interval_to_minutes
        return interval_to_minutes(self.interval)


# Common timeframe constants for convenience
TF_1M: Final = Timeframe("1M")
TF_5M: Final = Timeframe("5M")
TF_15M: Final = Timeframe("15M")
TF_30M: Final = Timeframe("30M")
TF_1H: Final = Timeframe("1H")
TF_4H: Final = Timeframe("4H")
TF_1D: Final = Timeframe("1D")
TF_1W: Final = Timeframe("1W")
TF_1MONTH: Final = Timeframe("1MONTH")