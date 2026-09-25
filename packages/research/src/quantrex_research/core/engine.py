"""ResearchEngine - Generic orchestrator for research components."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from quantrex_backtest import DataOrchestrator, BacktestConfig
from quantrex_backtest.data.orchestrator import DataOrchestratorConfig
from quantrex_core import InstrumentSpec
from quantrex_core.models import Candle
from quantrex_core.logging import get_logger
from quantrex_core.timeframe import TimeframeRegistry, TimeframeDispatcher

from quantrex_research.core.base import ResearchComponent
from quantrex_research.utils.data_helpers import merge_candle_streams

logger = get_logger(__name__)


class BufferedEvent:
    """Internal event buffer entry."""
    
    def __init__(self, event, emission_candle: Candle):
        self.event = event
        self.emission_candle = emission_candle


class ResearchContext:
    """Minimal context for research components providing history and timeframe access.
    
    Mirrors the StrategyContext interface from backtest for compatibility.
    """
    
    def __init__(self, base_timeframe: str = "1M") -> None:
        self._history: List[Candle] = []
        self._base_timeframe = base_timeframe
        self._derived_histories: Dict[str, List[Candle]] = {}
        self._derived_indices: Dict[str, int] = {}
        self._symbol = ""
        self._current_derived_candles: Dict[str, Dict[str, Any]] = {}
    
    def set_symbol(self, symbol: str) -> None:
        self._symbol = symbol
    
    @property
    def history(self) -> tuple[Candle, ...]:
        """Return history as tuple (read-only snapshot)."""
        return tuple(self._history)
    
    def timeframe_history(self, timeframe: str) -> tuple[Candle, ...]:
        """Return history for a specific timeframe."""
        if timeframe == self._base_timeframe:
            return tuple(self._history)
        return tuple(self._derived_histories.get(timeframe, []))
    
    def record_candle(self, candle: Candle) -> None:
        """Record a candle to history and update derived timeframes."""
        self._history.append(candle)
        self._update_derived_timeframes(candle)
    
    def _update_derived_timeframes(self, candle: Candle) -> None:
        """Update derived timeframe candles (e.g., 1H from 1M)."""
        from quantrex_core.timeframe.parser import interval_to_minutes
        
        # Only support 1H for now (can be extended)
        target_timeframes = ["1H"]
        
        for tf in target_timeframes:
            tf_minutes = interval_to_minutes(tf)
            if tf_minutes is None or tf_minutes <= 1:
                continue
            
            # Calculate the bucket key for this candle
            dt = candle.timestamp
            bucket_minutes = (dt.hour * 60 + dt.minute) // tf_minutes * tf_minutes
            bucket_hour = bucket_minutes // 60
            bucket_min = bucket_minutes % 60
            bucket_key = f"{dt.date()}_{bucket_hour:02d}:{bucket_min:02d}"
            
            if bucket_key not in self._current_derived_candles:
                self._current_derived_candles[bucket_key] = {
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                    "timestamp": dt.replace(hour=bucket_hour, minute=bucket_min, second=0, microsecond=0),
                    "symbol": candle.symbol,
                    "timeframe": tf,
                }
            else:
                bucket = self._current_derived_candles[bucket_key]
                bucket["high"] = max(bucket["high"], candle.high)
                bucket["low"] = min(bucket["low"], candle.low)
                bucket["close"] = candle.close
                bucket["volume"] += candle.volume
            
            # Check if this is the last minute of the bucket
            next_candle_minute = (dt.hour * 60 + dt.minute + 1) % (24 * 60)
            next_bucket_minutes = next_candle_minute // tf_minutes * tf_minutes
            if next_bucket_minutes != bucket_minutes:
                # Bucket complete - create candle and add to history
                bucket = self._current_derived_candles.pop(bucket_key)
                derived_candle = Candle(
                    symbol=bucket["symbol"],
                    timestamp=bucket["timestamp"],
                    close_time=bucket["timestamp"] + timedelta(minutes=tf_minutes),
                    timeframe=tf,
                    open=bucket["open"],
                    high=bucket["high"],
                    low=bucket["low"],
                    close=bucket["close"],
                    volume=bucket["volume"],
                )
                if tf not in self._derived_histories:
                    self._derived_histories[tf] = []
                self._derived_histories[tf].append(derived_candle)
    
    def get_position(self, symbol: str):
        """Get position - returns dummy position for research (no actual positions)."""
        from quantrex_core.models.position import Position
        return Position.zero(symbol)


class ResearchEngine:
    """Generic research engine that orchestrates data and component lifecycle.
    
    Completely unaware of specific research concepts. Only handles:
    - Data loading via DataOrchestrator
    - Candle loop with time-ordered merged stream
    - Component lifecycle (on_start, on_candle, on_stop)
    - Event buffering with horizon tracking
    - Incremental calculation triggering
    - Output directory management
    """
    
    def __init__(
        self,
        instruments: List[InstrumentSpec],
        research_components: List[ResearchComponent],
        data_start: str,
        data_end: str,
        backtest_config: Optional[BacktestConfig] = None,
        data_orchestrator_config: Optional[DataOrchestratorConfig] = None,
    ) -> None:
        """Initialize the research engine.
        
        Args:
            instruments: List of instrument specifications.
            research_components: List of research components to run.
            data_start: Start date string (YYYY-MM-DD).
            data_end: End date string (YYYY-MM-DD).
            backtest_config: Optional BacktestConfig for data preparation.
            data_orchestrator_config: Optional DataOrchestratorConfig.
        """
        self.instruments = instruments
        self.research_components = research_components
        self.data_start = data_start
        self.data_end = data_end
        self.backtest_config = backtest_config or BacktestConfig(
            data_start=data_start,
            data_end=data_end,
            auto_download=True,
            validate_completeness=True,
        )
        self.data_orchestrator_config = data_orchestrator_config or DataOrchestratorConfig()
        
        # Per-component event buffers
        self._event_buffers: Dict[ResearchComponent, List[BufferedEvent]] = {
            comp: [] for comp in research_components
        }
        
        # Current candle index for progress tracking
        self._current_candle: Optional[Candle] = None
    
    def run(self) -> Dict[str, Any]:
        """Run the research engine.
        
        Returns:
            Dictionary mapping component class name to component result.
        """
        logger.info("Starting ResearchEngine with %d components", len(self.research_components))
        
        # 1. Load and prepare data via DataOrchestrator
        logger.info("Loading data via DataOrchestrator...")
        data_orchestrator = DataOrchestrator(self.data_orchestrator_config)
        symbol_data = data_orchestrator.validate_and_prepare(
            self.instruments, self.backtest_config
        )
        
        # Convert to Candle objects
        symbol_candles: Dict[str, List[Candle]] = {}
        for symbol, rows in symbol_data.items():
            candles = []
            for row in rows:
                # DataOrchestrator returns dict rows with datetime, open, high, low, close, volume
                # The datetime is already a string in the adapter's format
                # We need to create Candle objects with timeframe info
                # The base timeframe is 1M (1 minute)
                from quantrex_core.models import Candle
                # Get datetime format from the instrument's adapter
                adapter = next((inst.adapter for inst in self.instruments if inst.symbol == symbol), None)
                datetime_format = "%Y-%m-%d %H:%M:%S"  # Default
                if adapter and hasattr(adapter, 'datetime_format'):
                    datetime_format = adapter.datetime_format
                elif adapter and hasattr(adapter, 'provider') and hasattr(adapter.provider, '_datetime_format'):
                    datetime_format = adapter.provider._datetime_format
                candle = Candle.from_row(
                    row, 
                    symbol=symbol, 
                    timeframe="1M",
                    datetime_format=datetime_format
                )
                candles.append(candle)
            symbol_candles[symbol] = candles
        
        logger.info("Loaded data for %d symbols", len(symbol_candles))
        for symbol, candles in symbol_candles.items():
            logger.info("  %s: %d candles", symbol, len(candles))
        
        # 2. Merge into single time-ordered stream
        merged_candles = merge_candle_streams(symbol_candles)
        logger.info("Merged candle stream: %d total candles", len(merged_candles))
        
        # 3. Call on_start for all components (always, even with empty data)
        for component in self.research_components:
            component.set_event_receiver(self)
            component.on_start()
        
        if not merged_candles:
            logger.warning("No candles loaded, exiting")
            # Still call on_stop for components
            return self._finalize_components()
        
        # 4. Main candle loop
        logger.info("Starting candle loop...")
        
        # Create research context for history/timeframe access
        context = ResearchContext(base_timeframe="1M")
        
        # Create timeframe registry and dispatcher for @on_timeframe support
        registry = TimeframeRegistry()
        dispatcher = TimeframeDispatcher(registry)
        
        # Register @on_timeframe methods from all components
        for component in self.research_components:
            for attr_name in dir(component):
                attr = getattr(component, attr_name)
                if callable(attr) and hasattr(attr, '_quantrex_timeframe'):
                    interval = attr._quantrex_timeframe
                    registry.register(interval, attr)
        
        for candle in merged_candles:
            self._current_candle = candle
            
            # Set current candle on all components for emit_event
            for component in self.research_components:
                component.current_candle = candle
            
            # Update context with current candle
            context.set_symbol(candle.symbol)
            context.record_candle(candle)
            
            # Attach context to component for access via self.ctx
            for component in self.research_components:
                component.ctx = context
            
            # Dispatch timeframe methods (e.g., @on_timeframe("1H"))
            dispatcher.dispatch_all(context, candle.symbol)
            
            # Dispatch to all components
            for component in self.research_components:
                component.on_candle(candle)
            
            # Check buffered events for elapsed horizons
            self._process_elapsed_horizons(candle, merged_candles)
        
        # 5. Process remaining events (horizons beyond data end)
        self._process_remaining_events(merged_candles)
        
        # 6. Call on_stop for all components and collect results
        results = self._finalize_components()
        
        logger.info("ResearchEngine completed")
        return results
    
    def _process_elapsed_horizons(self, current_candle: Candle, all_candles: List[Candle]) -> None:
        """Check buffered events for elapsed horizons and trigger calculation."""
        for component, buffer in self._event_buffers.items():
            horizons = component.get_horizons()
            
            for buffered_event in buffer[:]:  # Copy to allow removal
                event_candle = buffered_event.emission_candle
                
                # Check if ALL horizons have elapsed for this event
                all_elapsed = [
                    h for h in horizons
                    if current_candle.timestamp >= event_candle.timestamp + h
                ]
                
                # Only calculate when ALL horizons have elapsed
                if len(all_elapsed) == len(horizons):
                    series = self._calculate_returns(all_candles, buffered_event.event, all_elapsed)
                    component.on_returns_calculated(buffered_event.event, series)
                    buffer.remove(buffered_event)
    
    def _process_remaining_events(self, all_candles: List[Candle]) -> None:
        """Process any remaining buffered events (horizons beyond data end -> NaN)."""
        for component, buffer in self._event_buffers.items():
            horizons = component.get_horizons()
            
            for buffered_event in buffer:
                # Calculate all remaining horizons (will be None)
                series = self._calculate_returns(all_candles, buffered_event.event, horizons)
                component.on_returns_calculated(buffered_event.event, series)
            
            buffer.clear()
    
    def _calculate_returns(
        self, 
        candles: List[Candle], 
        event, 
        horizons: List[timedelta]
    ):
        """Calculate forward returns for given horizons."""
        from quantrex_research.research_components.forward_return.calculator import ForwardReturnCalculator
        return ForwardReturnCalculator.calculate(candles, event, horizons)
    
    def receive_event(self, component: ResearchComponent, event, emission_candle: Candle) -> None:
        """Called by component.emit_event() to buffer the event."""
        self._event_buffers[component].append(BufferedEvent(event, emission_candle))
    
    def _finalize_components(self) -> Dict[str, Any]:
        """Call on_stop for all components and collect results."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_base = Path("output/research")
        results = {}
        
        for component in self.research_components:
            # output/research/<ComponentClassName>/<timestamp>/
            component_output_dir = output_base / component.__class__.__name__ / timestamp
            component_output_dir.mkdir(parents=True, exist_ok=True)
            
            # Component writes its own artifacts
            result = component.on_stop(component_output_dir)
            results[component.__class__.__name__] = result
            
        return results