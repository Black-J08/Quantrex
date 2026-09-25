"""ResearchComponent abstract base class.

Defines the contract for all research components. A research component declares
what it observes and how it reacts to candles; ResearchEngine only orchestrates
data and the research-component lifecycle.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide


class ResearchComponent(ABC):
    """Abstract base class for all research components.
    
    A research component declares what it observes and how it reacts to candles.
    The ResearchEngine orchestrates data and the component lifecycle.
    """
    
    def __init__(self) -> None:
        self._engine = None
        self._current_candle: Optional[Candle] = None
        self.ctx = None  # ResearchContext attached by engine
    
    def set_event_receiver(self, engine) -> None:
        """Set the engine as event receiver. Called by ResearchEngine during initialization."""
        self._engine = engine
    
    @property
    def current_candle(self) -> Optional[Candle]:
        return self._current_candle
    
    @current_candle.setter
    def current_candle(self, candle: Optional[Candle]) -> None:
        self._current_candle = candle
    
    @abstractmethod
    def on_start(self) -> None:
        """Called once before the candle loop begins.
        
        Override to perform initialization that requires the component
        to be fully constructed.
        """
        pass
    
    @abstractmethod
    def on_candle(self, candle: Candle) -> None:
        """Process a single candle.
        
        Called for each candle in chronological order across all symbols.
        Override to implement event detection logic.
        
        Args:
            candle: The current candle being processed.
        """
        pass
    
    @abstractmethod
    def on_stop(self, output_dir: Path) -> Any:
        """Called once after the candle loop completes.
        
        Component should finalize its analysis, write artifacts to output_dir,
        and return its result object.
        
        Args:
            output_dir: Directory where component should write its output artifacts.
            
        Returns:
            Component-specific result object.
        """
        pass
    
    @abstractmethod
    def get_horizons(self) -> List[timedelta]:
        """Return the list of forward-return horizons this component uses.
        
        Returns:
            List of timedelta objects representing forward-return horizons.
        """
        pass
    
    @abstractmethod
    def on_returns_calculated(self, event: "ForwardReturnEvent", series: "ForwardReturnSeries") -> None:
        """Called by engine when forward returns for an event have been calculated.
        
        Args:
            event: The research event that triggered the calculation.
            series: The calculated forward return series for elapsed horizons.
        """
        pass
    
    def emit_event(
        self,
        symbol: str,
        direction: OrderSide,
        timestamp: datetime,
        metadata: Dict[str, Any],
        emission_candle: Optional[Candle] = None
    ) -> None:
        """Emit a research event. Engine will track horizons and trigger calculation when elapsed.
        
        Args:
            symbol: Trading symbol.
            direction: OrderSide.BUY for LONG, OrderSide.SELL for SHORT.
            timestamp: Event timestamp (should match current candle timestamp).
            metadata: Additional event metadata.
            emission_candle: The candle at which the event was emitted. Defaults to current_candle.
        """
        if self._engine is None:
            raise RuntimeError("Engine not set. Call set_event_receiver() first.")
        if self._current_candle is None and emission_candle is None:
            raise RuntimeError("No current candle. emit_event() must be called from on_candle() or provide emission_candle.")
        
        from quantrex_research.research_components.forward_return.models import ForwardReturnEvent
        
        event = ForwardReturnEvent(
            symbol=symbol,
            timestamp=timestamp,
            direction=direction,
            metadata=metadata,
            candle=emission_candle or self._current_candle,
        )
        self._engine.receive_event(self, event, emission_candle or self._current_candle)