"""ResearchComponent base class for research mode.

Research components receive on_candle callbacks during the research
event loop, enabling multiple independent analyses per run.
"""

from __future__ import annotations

from quantrex.core.models.market_data import OHLCVCandle


class ResearchComponent:
    """Base class for research components.

    Subclasses can implement on_candle to receive each bar during the
    research event loop.
    """

    def on_candle(self, candle: OHLCVCandle) -> None:
        """Handle a new bar/candle during research.

        Args:
            candle: The completed OHLCV candle.
        """
