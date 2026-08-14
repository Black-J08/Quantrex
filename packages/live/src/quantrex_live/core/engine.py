"""Live trading engine (placeholder).

Minimal placeholder to establish future integration point for live trading.
"""

from quantrex_core.strategy.base import Strategy


class LiveEngine:
    """Placeholder for live trading engine.
    
    Will eventually connect to brokers and execute strategies in real-time.
    """
    
    def __init__(self) -> None:
        """Initialize live engine."""
        pass
    
    def run(self, strategy: Strategy) -> None:
        """Run strategy with live market data.
        
        Args:
            strategy: Strategy instance to run
            
        Raises:
            NotImplementedError: Always, as this is a placeholder.
        """
        raise NotImplementedError("Live engine not yet implemented")