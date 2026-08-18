"""Live trading engine (placeholder).

Minimal placeholder to establish future integration point for live trading.
"""

from datetime import datetime
from quantrex_core.strategy.base import Strategy
from quantrex_core.position.manager import PositionManager
from .context import LiveStrategyContext


class LiveEngine:
    """Placeholder for live trading engine.
    
    Will eventually connect to brokers and execute strategies in real-time.
    """
    
    def __init__(self, strategy: Strategy) -> None:
        """Initialize live engine with a strategy.

        Args:
            strategy: Strategy instance to execute
        """
        self._strategy = strategy
        self._position_manager = PositionManager()
        self._context = LiveStrategyContext(self._position_manager)
        self._strategy.set_context(self._context)
    
    def run(self) -> None:
        """Run strategy with live market data.

        Calls strategy.on_start(), then strategy.on_candle() for each live candle,
        then strategy.on_stop().

        Raises:
            NotImplementedError: Always, as this is a placeholder.
        """
        self._strategy.on_start()
        raise NotImplementedError("Live engine not yet implemented")