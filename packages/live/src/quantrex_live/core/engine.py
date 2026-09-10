"""Live trading engine.

Connects to brokers and executes strategies in real-time with multi-timeframe support.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from quantrex_core.logging import get_logger
from quantrex_core.models import Candle
from quantrex_core.strategy.base import Strategy
from quantrex_core.position.manager import PositionManager
from quantrex_core.protocols import DataAdapter

if TYPE_CHECKING:
    from quantrex_data.adapters.base import BaseDataAdapter

from .context import LiveStrategyContext


logger = get_logger(__name__)


class LiveEngine:
    """Live trading engine with multi-timeframe support.
    
    Subscribes to real-time market data for multiple timeframes,
    manages strategy lifecycle, and routes orders to the broker.
    """
    
    def __init__(
        self,
        strategy: Strategy,
        adapter: DataAdapter,
        symbol: str = "",
        max_history_size: int = 10000,
    ) -> None:
        """Initialize live engine with a strategy and data adapter.

        Args:
            strategy: Strategy instance to execute
            adapter: DataAdapter providing normalized market data
            symbol: Trading symbol
            max_history_size: Maximum number of candles to keep in history buffer
        """
        self._strategy = strategy
        self._adapter = adapter
        self._symbol = symbol
        self._position_manager = PositionManager()
        self._context = LiveStrategyContext(self._position_manager, max_history_size)
        self._strategy.set_context(self._context)
        self._running = False
        
        # Get required timeframes from strategy
        self._required_timeframes = self._get_required_timeframes()
        self._context.set_base_timeframe(self._required_timeframes[0])
        
        logger.info("LiveEngine initialized for symbol=%s, timeframes=%s", symbol, self._required_timeframes)
    
    def _get_required_timeframes(self) -> list[str]:
        """Get timeframes required by strategy. If on_candle overridden,
        base is 1M; otherwise base is first registered interval."""
        strategy_timeframes = self._strategy.timeframe_registry.intervals()
        has_custom_on_candle = any(
            "on_candle" in cls.__dict__ for cls in self._strategy.__class__.__mro__
            if cls is not Strategy
        )
        if has_custom_on_candle:
            base_timeframe = "1M"
        elif strategy_timeframes:
            base_timeframe = strategy_timeframes[0]
        else:
            base_timeframe = "1M"
        all_timeframes = [base_timeframe] + [tf for tf in strategy_timeframes if tf != base_timeframe]
        return all_timeframes

    def run(self) -> None:
        """Run strategy with live market data.

        Performs warmup from historical data, then subscribes to real-time
        candle streams for all required timeframes. Calls strategy.on_start(),
        then strategy.on_candle() for each live candle, then strategy.on_stop()
        on shutdown.

        Raises:
            NotImplementedError: Live data subscription not yet implemented.
        """
        self._running = True
        
        # Warmup: fetch historical data for all timeframes
        logger.info("Performing warmup for timeframes: %s", self._required_timeframes)
        warmup_data = self._warmup()
        
        # Pre-fill context history with warmup data
        if warmup_data:
            base_tf = self._required_timeframes[0]
            base_candles = warmup_data.get(base_tf, [])
            self._context.warmup_from_history(base_candles)
        
        self._strategy.on_start()
        
        # TODO: Subscribe to real-time data streams for all required timeframes
        # This would typically involve:
        # 1. Opening WebSocket connections for each timeframe
        # 2. Registering callbacks for candle updates
        # 3. Running event loop until shutdown
        
        raise NotImplementedError("Live data subscription not yet implemented. "
                                  "Warmup completed successfully.")
    
    def _warmup(self) -> dict[str, list]:
        """Fetch historical data for warmup across all required timeframes.
        
        Returns:
            Dictionary mapping timeframe to list of Candle objects.
        """
        warmup_data = {}
        for tf in self._required_timeframes:
            try:
                if tf == self._required_timeframes[0]:
                    raw_data = self._adapter.read()
                else:
                    raw_data = self._adapter.read_timeframe(tf)
                
                # Convert to candles (simplified - would use proper datetime format)
                candles = []
                for row in raw_data:
                    try:
                        from quantrex_core.models import Candle
                        candle = Candle.from_row(
                            row,
                            self._symbol,
                            self._adapter.datetime_format,
                        )
                        candles.append(candle)
                    except Exception:
                        continue
                
                warmup_data[tf] = candles
                logger.info("Warmup: fetched %d candles for timeframe %s", len(candles), tf)
            except Exception as e:
                logger.warning("Failed to fetch warmup data for timeframe %s: %s", tf, e)
                warmup_data[tf] = []
        
        return warmup_data
    
    def stop(self) -> None:
        """Stop the live engine gracefully."""
        self._running = False
        self._strategy.on_stop()
        logger.info("LiveEngine stopped")
    
    def on_candle(self, candle: Candle) -> None:
        """Handle incoming live candle.
        
        Called by data feed when a new candle is received.
        Updates context and invokes strategy.
        
        Args:
            candle: The new candle from the live feed.
        """
        if not self._running:
            return
        
        # Add to context history (updates derived histories)
        self._context.add_candle(candle)
        
        # Call strategy
        try:
            self._strategy.on_candle(candle)
        except Exception as e:
            logger.exception("Strategy.on_candle raised: %s", e)