"""CSV row generators for testing."""

import random
from datetime import datetime, timedelta
from typing import Optional


def make_ohlc_series(
    num_rows: int = 100,
    start_datetime: datetime = datetime(2023, 1, 1, 9, 30),
    interval_minutes: int = 1,
    start_price: float = 100.0,
    volatility: float = 0.01,
    drift: float = 0.0,
    volume_range: tuple[int, int] = (100, 10000),
    seed: Optional[int] = None,
) -> list[list[str]]:
    """Generate realistic OHLC time series data for index mode testing.

    Generates strictly sequential datetime values with realistic price movements.
    OHLC values follow: high >= max(open, close), low <= min(open, close).

    Args:
        num_rows: Number of rows to generate (default: 100)
        start_datetime: Starting datetime for the series (default: 2023-01-01 09:30)
        interval_minutes: Minutes between each row (default: 1)
        start_price: Initial price for the first candle (default: 100.0)
        volatility: Price volatility per step as fraction (default: 0.01 = 1%)
        drift: Price drift per step as fraction (default: 0.0)
        volume_range: Tuple of (min_volume, max_volume) for random volume (default: (100, 10000))
        seed: Random seed for reproducibility (default: None)

    Returns:
        List of row lists in index mode format: [date, time, open, high, low, close, volume]
        All values are strings formatted for CSV.
    """
    if seed is not None:
        random.seed(seed)

    rows = []
    current_price = start_price
    current_dt = start_datetime

    for _ in range(num_rows):
        # Generate price movement
        change_pct = random.gauss(drift, volatility)
        new_price = current_price * (1 + change_pct)
        new_price = max(new_price, 0.01)  # Prevent negative/zero prices

        # Generate OHLC from current and new price
        open_price = current_price
        close_price = new_price

        # High/low with some intraday range
        intraday_range = abs(close_price - open_price) * random.uniform(0.5, 2.0)
        high_price = max(open_price, close_price) + intraday_range * random.uniform(0, 1)
        low_price = min(open_price, close_price) - intraday_range * random.uniform(0, 1)
        low_price = max(low_price, 0.01)

        # Volume
        volume = random.randint(volume_range[0], volume_range[1])

        # Format as strings
        date_str = current_dt.strftime("%Y%m%d")
        time_str = current_dt.strftime("%H:%M")
        row = [
            date_str,
            time_str,
            f"{open_price:.2f}",
            f"{high_price:.2f}",
            f"{low_price:.2f}",
            f"{close_price:.2f}",
            str(volume),
        ]
        rows.append(row)

        # Advance
        current_price = new_price
        current_dt += timedelta(minutes=interval_minutes)

    return rows


def csv_rows_to_string(rows: list[list[str]]) -> str:
    """Convert list of row lists to CSV-formatted string.

    Args:
        rows: List of row lists containing string values

    Returns:
        CSV-formatted string with newline termination
    """
    output = []
    for row in rows:
        output.append(",".join(row))
    return "\n".join(output) + "\n"


__all__ = [
    "make_ohlc_series",
    "csv_rows_to_string",
]