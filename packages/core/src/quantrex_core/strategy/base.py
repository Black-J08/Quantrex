"""Strategy base class for Quantrex framework.

Abstract base class defining the strategy interface that works across
all execution environments (backtest, live, paper trading, etc.).
"""

from abc import ABC, abstractmethod
from ..models.candle import Candle


class Strategy(ABC):
    """Base class for all trading strategies.
    
    Strategies maintain their own internal state (positions, indicators, etc.)
    and receive candles via the on_candle callback.
    
    The same Strategy implementation can be used across different execution
    environments without modification.
    """
    
    def __init__(self) -> None:
        """Initialize strategy. Override to set up initial state.
        
        Example:
            def __init__(self):
                super().__init__()
                self.position = 0
                self.indicator_values = []
        """
        pass
    
    @abstractmethod
    def on_candle(self, candle: Candle) -> None:
        """Process a single candle.
        
        This method is called for each candle in the data feed.
        Strategies should implement their trading logic here.
        
        Args:
            candle: The candle to process (OHLCV data with symbol and timestamp)
        """
        pass
    
    def on_start(self) -> None:
        """Called once before processing begins.
        
        Override to perform initialization that requires the strategy
        to be fully constructed (e.g., connecting to indicators).
        """
        pass
    
    def on_stop(self) -> None:
        """Called once after processing ends.
        
        Override to perform cleanup (e.g., closing positions, saving state).
        """
        pass