"""ResearchComponent abstract base class.

Defines the contract for all research components. A research component declares
what it observes and how it reacts to candles; ResearchEngine only orchestrates
data and the research-component lifecycle.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

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
        emission_candle: Candle | None = None,
    ) -> None:
        """Emit a research event. Engine will track horizons and trigger calculation when elapsed.
        
        Args:
            symbol: Trading symbol.
            direction: OrderSide.BUY for LONG, OrderSide.SELL for SHORT.
            timestamp: Event timestamp (should match current candle timestamp).
            metadata: Additional event metadata.
            emission_candle: Optional candle that triggered this event. Defaults to current_candle.
                Useful when emitting from @on_timeframe callbacks where the emission candle
                is the higher timeframe candle, not the base timeframe candle.
        """
        if self._engine is None:
            raise RuntimeError("Engine not set. Call set_event_receiver() first.")
        
        candle = emission_candle if emission_candle is not None else self._current_candle
        if candle is None:
            raise RuntimeError("No current candle. emit_event() must be called from on_candle() or on_timeframe().")
        
        from quantrex_research.research_components.forward_return.models import ForwardReturnEvent
        
        event = ForwardReturnEvent(
            symbol=symbol,
            timestamp=timestamp,
            direction=direction,
            metadata=metadata,
            candle=candle,
        )
        self._engine.receive_event(self, event, candle)

    def compute_indicators(
        self,
        candles: Sequence[Mapping[str, object]],
        timeframe: str | None = None,
    ) -> Sequence[Mapping[str, float | int | None]]:
        """Precompute technical indicators over the ordered candle history.

        Default: no-op (returns empty mapping per bar). Subclasses may
        override to compute RSI, SMA, etc. using pandas/numpy/ta-lib.
        The framework does not provide built-in indicator calculations.

        Args:
            candles: Sequence of raw candle row dictionaries, sorted by timestamp.
            timeframe: Timeframe interval (e.g., "1M", "1H", "1D"). None for base timeframe.

        Returns:
            Sequence of indicator mappings aligned 1:1 with input candles.
            Each mapping contains indicator name -> value (float, int, or None).
        """
        return [{} for _ in candles]