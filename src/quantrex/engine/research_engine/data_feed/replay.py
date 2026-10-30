"""Historical data replay for research.

Provides a candle stream from historical data, sorted by timestamp.
Same as backtest data feed.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from quantrex.core.models.market_data import OHLCVCandle


class CandleReplay:
    """Replays historical candles in timestamp order.

    Wraps an iterable of OHLCVCandle objects and presents them as a
    time-sorted stream for the research event loop.
    """

    def __init__(self, candles: Iterable[OHLCVCandle]) -> None:
        self._candles = list(candles)

    def __iter__(self) -> Iterator[OHLCVCandle]:
        return iter(self._candles)

    def __len__(self) -> int:
        return len(self._candles)
