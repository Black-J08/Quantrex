"""ResearchEngine - Generic orchestrator for research components."""

from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from quantrex_backtest import DataOrchestrator, BacktestConfig
from quantrex_backtest.data.orchestrator import DataOrchestratorConfig
from quantrex_core import InstrumentSpec
from quantrex_core.models import Candle
from quantrex_core.logging import get_logger
from quantrex_core.timeframe import TimeframeRegistry, TimeframeDispatcher
from quantrex_core.timeframe.filtering import filter_candles_by_timeframe
from quantrex_core.timeframe.parser import interval_to_minutes, parse_interval

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
    Supports multi-timeframe via pre-computed derived candles using shared filtering logic.
    Supports multiple symbols by storing derived candles per symbol.
    """
    
    def __init__(
        self,
        base_timeframe: str = "1M",
        required_timeframes: Optional[List[str]] = None,
        origin_time: Optional[time] = None,
        raw_data_by_timeframe: Optional[Dict[str, Dict[str, List[dict]]]] = None,
        indicators_by_timeframe: Optional[Dict[str, Dict[str, List[Mapping]]]] = None,
    ) -> None:
        self._history: List[Candle] = []
        self._base_timeframe = base_timeframe
        self._required_timeframes = required_timeframes or [base_timeframe]
        self._origin_time = origin_time
        self._raw_data_by_timeframe = raw_data_by_timeframe or {}
        self._indicators_by_timeframe = indicators_by_timeframe or {}
        # Per-symbol derived candles
        self._derived_candles: Dict[str, Dict[str, List[Candle]]] = {}
        self._derived_histories: Dict[str, Dict[str, List[Candle]]] = {}
        self._derived_indices: Dict[str, Dict[str, int]] = {}
        self._base_completed_index = 0
        self._symbol = ""
        self._datetime_format = "%Y-%m-%d %H:%M:%S"
        
        # Pre-compute derived timeframe candles if data provided
        if self._raw_data_by_timeframe and self._indicators_by_timeframe:
            self._precompute_derived_candles()
    
    def set_symbol(self, symbol: str) -> None:
        self._symbol = symbol
    
    def set_symbol_and_format(self, symbol: str, datetime_format: str) -> None:
        """Set symbol and datetime format for derived candle construction.
        
        Called by engine after context creation.
        """
        self._symbol = symbol
        self._datetime_format = datetime_format
        # Rebuild derived candles for this symbol
        if self._raw_data_by_timeframe and self._indicators_by_timeframe:
            self._precompute_derived_candles_for_symbol(symbol)
    
    def _precompute_derived_candles(self) -> None:
        """Pre-compute candles for all non-base timeframes for all symbols."""
        for symbol in self._raw_data_by_timeframe.get(self._base_timeframe, {}).keys():
            self._precompute_derived_candles_for_symbol(symbol)
    
    def _precompute_derived_candles_for_symbol(self, symbol: str) -> None:
        """Pre-compute candles for all non-base timeframes for a specific symbol."""
        # Initialize per-symbol storage if not exists
        if symbol not in self._derived_candles:
            self._derived_candles[symbol] = {}
            self._derived_histories[symbol] = {}
            self._derived_indices[symbol] = {}
        
        for tf, symbol_data in self._raw_data_by_timeframe.items():
            if tf != self._base_timeframe:
                # Get data for current symbol
                raw_rows = symbol_data.get(symbol, [])
                if not raw_rows:
                    continue
                indicators = self._indicators_by_timeframe.get(tf, {}).get(symbol, [{} for _ in raw_rows])
                self._derived_candles[symbol][tf] = self._build_candles_for_timeframe(tf, raw_rows, indicators)
                self._derived_histories[symbol][tf] = []
                self._derived_indices[symbol][tf] = 0
    
    @property
    def history(self) -> tuple[Candle, ...]:
        """Return history as tuple (read-only snapshot).
        
        Returns only completed candles (those whose close time has passed).
        """
        return tuple(self._history[:self._base_completed_index])
    
    def timeframe_history(self, timeframe: str) -> tuple[Candle, ...]:
        """Return history for a specific timeframe for the current symbol."""
        if timeframe == self._base_timeframe:
            return tuple(self._history[:self._base_completed_index])
        
        # Return pre-computed derived history for current symbol (only completed candles)
        if self._symbol and timeframe in self._derived_histories.get(self._symbol, {}):
            return tuple(self._derived_histories[self._symbol][timeframe])
        
        # Fallback to filtering (for backward compatibility)
        return tuple(self._filter_by_timeframe(self._history, timeframe))
    
    def record_candle(self, candle: Candle) -> None:
        """Record a candle to history and update derived timeframe histories."""
        self._history.append(candle)
        
        # Update derived timeframe histories using the current execution
        # time (close of the base bar just processed), so a higher-
        # timeframe candle becomes visible exactly when its close time is
        # reached — not one base bar later.
        self._update_derived_histories(candle.close_time)
    
    def _update_derived_histories(self, current_timestamp: datetime) -> None:
        """Update derived timeframe histories with candles that have completed.
        
        A derived candle is complete when its **close time** (open time +
        its own timeframe duration) is at or before the current execution
        time. Comparing open times here would dispatch higher-timeframe
        candles before they finish forming.
        """
        # Update base timeframe completed index
        while (self._base_completed_index < len(self._history) and
               self._history[self._base_completed_index].close_time <= current_timestamp):
            self._base_completed_index += 1

        # Update derived histories for current symbol
        if self._symbol and self._symbol in self._derived_candles:
            for tf, derived_candles in self._derived_candles[self._symbol].items():
                derived_history = self._derived_histories[self._symbol][tf]
                idx = self._derived_indices[self._symbol][tf]

                # Add all derived candles whose close time has passed
                while idx < len(derived_candles) and derived_candles[idx].close_time <= current_timestamp:
                    derived_history.append(derived_candles[idx])
                    idx += 1

                self._derived_indices[self._symbol][tf] = idx
    
    def _build_candles_for_timeframe(self, timeframe: str, raw_rows: List[dict], indicators: List[Mapping]) -> List[Candle]:
        """Build Candle objects for a specific timeframe from raw rows."""
        candles = []
        for idx, row in enumerate(raw_rows):
            try:
                candle = Candle.from_row(
                    row,
                    self._symbol,
                    timeframe,
                    self._datetime_format,
                    indicators=indicators[idx] if idx < len(indicators) else {},
                )
                candles.append(candle)
            except Exception:
                # Skip malformed rows
                continue
        return candles
    
    def _filter_by_timeframe(self, candles: List[Candle], interval: str) -> List[Candle]:
        """Filter candles by timeframe interval using shared implementation.
        
        Delegates to quantrex_core.timeframe.filter_candles_by_timeframe.
        
        Args:
            candles: List of candles in chronological order.
            interval: Timeframe interval string (e.g., "1H", "1D", "4H").
            
        Returns:
            List of candles representing the last candle of each interval.
        """
        if not candles:
            return []

        # Use origin time for correct interval alignment
        # If origin_time is not set, default to midnight (00:00)
        origin_time = self._origin_time
        if origin_time is None:
            origin_time = time(0, 0)

        return list(filter_candles_by_timeframe(candles, interval, origin_time))
    
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
    
    def _get_required_timeframes(self) -> List[str]:
        """Get timeframes required by all research components.
        
        If any component defines on_candle (not just base), base is 1M;
        otherwise base is the first registered @on_timeframe interval.
        """
        # Collect all registered timeframes from all components
        all_timeframes = set()
        has_custom_on_candle = False
        
        for component in self.research_components:
            # Check if component has custom on_candle (not from base class)
            for cls in component.__class__.__mro__:
                if cls is ResearchComponent:
                    break
                if "on_candle" in cls.__dict__:
                    has_custom_on_candle = True
                    break
            
            # Collect @on_timeframe decorated methods
            for attr_name in dir(component):
                attr = getattr(component, attr_name)
                if callable(attr) and hasattr(attr, '_quantrex_timeframe'):
                    all_timeframes.add(attr._quantrex_timeframe)
        
        if has_custom_on_candle:
            base_timeframe = "1M"
        elif all_timeframes:
            base_timeframe = min(all_timeframes, key=interval_to_minutes)
        else:
            base_timeframe = "1M"
        
        # Return base timeframe first, then others sorted by duration
        other_timeframes = sorted([tf for tf in all_timeframes if tf != base_timeframe], key=interval_to_minutes)
        return [base_timeframe] + other_timeframes
    
    def _read_timeframe_data(self, timeframe: str) -> Dict[str, List[dict]]:
        """Read timeframe data from all instrument adapters.
        
        Args:
            timeframe: Timeframe interval string (e.g., "1M", "1H", "1D")
            
        Returns:
            Dictionary mapping symbol to list of raw data rows
        """
        symbol_data: Dict[str, List[dict]] = {}
        
        for instrument in self.instruments:
            adapter = instrument.adapter
            if adapter is None:
                logger.warning("No adapter for instrument %s, skipping", instrument.symbol)
                continue
            
            try:
                # Check if adapter supports this timeframe
                supported = getattr(adapter, 'supported_timeframes', [])
                if supported and timeframe not in supported:
                    logger.warning("Adapter for %s does not support timeframe %s, skipping", instrument.symbol, timeframe)
                    continue
                
                # Read data from adapter
                rows = adapter.read_timeframe(timeframe, from_date=self.data_start, to_date=self.data_end)
                if rows:
                    # Sort by datetime to ensure chronological order
                    datetime_format = getattr(adapter, 'datetime_format', "%Y-%m-%d %H:%M:%S")
                    rows.sort(key=lambda r: r.get('datetime', ''))
                    symbol_data[instrument.symbol] = rows
                    logger.info("Loaded %d rows for %s at %s", len(rows), instrument.symbol, timeframe)
                else:
                    logger.warning("No data returned for %s at %s", instrument.symbol, timeframe)
                    
            except Exception as e:
                logger.error("Failed to read %s data for %s: %s", timeframe, instrument.symbol, e)
                raise
        
        return symbol_data
    
    def _get_origin_time(self) -> Optional[time]:
        """Get market origin time from adapters.
        
        Returns the first non-None origin_time from adapters, or None.
        """
        for instrument in self.instruments:
            adapter = instrument.adapter
            if adapter and hasattr(adapter, 'get_origin_time'):
                origin = adapter.get_origin_time()
                if origin is not None:
                    return origin
        return None
    
    def run(self) -> Dict[str, Any]:
        """Run the research engine.
        
        Returns:
            Dictionary mapping component class name to component result.
        """
        logger.info("Starting ResearchEngine with %d components", len(self.research_components))
        
        # 1. Get required timeframes from all components
        required_timeframes = self._get_required_timeframes()
        base_timeframe = required_timeframes[0]
        logger.info("Required timeframes: %s (base: %s)", required_timeframes, base_timeframe)
        
        # 2. Get origin time for interval alignment
        origin_time = self._get_origin_time()
        if origin_time:
            logger.info("Using origin time: %s", origin_time)
        
        # 3. Load base timeframe data via DataOrchestrator (validated, synchronized)
        logger.info("Loading base timeframe (%s) data via DataOrchestrator...", base_timeframe)
        data_orchestrator = DataOrchestrator(self.data_orchestrator_config)
        base_symbol_data = data_orchestrator.validate_and_prepare(
            self.instruments, self.backtest_config
        )
        
        # 4. Load additional timeframes directly from adapters
        additional_timeframes = required_timeframes[1:]
        raw_data_by_timeframe: Dict[str, Dict[str, List[dict]]] = {base_timeframe: base_symbol_data}
        indicators_by_timeframe: Dict[str, Dict[str, List[Mapping]]] = {base_timeframe: {}}
        
        for tf in additional_timeframes:
            logger.info("Loading additional timeframe (%s) data from adapters...", tf)
            tf_data = self._read_timeframe_data(tf)
            raw_data_by_timeframe[tf] = tf_data
            indicators_by_timeframe[tf] = {symbol: [{} for _ in rows] for symbol, rows in tf_data.items()}
        
        # 5. Convert base timeframe data to Candle objects for merging
        symbol_candles: Dict[str, List[Candle]] = {}
        for symbol, rows in base_symbol_data.items():
            candles = []
            for row in rows:
                adapter = next((inst.adapter for inst in self.instruments if inst.symbol == symbol), None)
                datetime_format = "%Y-%m-%d %H:%M:%S"  # Default
                if adapter and hasattr(adapter, 'datetime_format'):
                    datetime_format = adapter.datetime_format
                elif adapter and hasattr(adapter, 'provider') and hasattr(adapter.provider, '_datetime_format'):
                    datetime_format = adapter.provider._datetime_format
                candle = Candle.from_row(
                    row, 
                    symbol=symbol, 
                    timeframe=base_timeframe,
                    datetime_format=datetime_format
                )
                candles.append(candle)
            symbol_candles[symbol] = candles
        
        logger.info("Loaded base data for %d symbols", len(symbol_candles))
        for symbol, candles in symbol_candles.items():
            logger.info("  %s: %d candles", symbol, len(candles))
        
        # 6. Merge into single time-ordered stream
        merged_candles = merge_candle_streams(symbol_candles)
        logger.info("Merged candle stream: %d total candles", len(merged_candles))
        
        # 7. Call on_start for all components (always, even with empty data)
        for component in self.research_components:
            component.set_event_receiver(self)
            component.on_start()
        
        if not merged_candles:
            logger.warning("No candles loaded, exiting")
            # Still call on_stop for components
            return self._finalize_components()
        
        # 8. Main candle loop
        logger.info("Starting candle loop...")
        
        # Create research context for history/timeframe access with multi-timeframe support
        context = ResearchContext(
            base_timeframe=base_timeframe,
            required_timeframes=required_timeframes,
            origin_time=origin_time,
            raw_data_by_timeframe=raw_data_by_timeframe,
            indicators_by_timeframe=indicators_by_timeframe,
        )
        
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
        
        # Set symbol and format for each symbol in context
        for symbol in symbol_candles.keys():
            adapter = next((inst.adapter for inst in self.instruments if inst.symbol == symbol), None)
            datetime_format = "%Y-%m-%d %H:%M:%S"  # Default
            if adapter and hasattr(adapter, 'datetime_format'):
                datetime_format = adapter.datetime_format
            elif adapter and hasattr(adapter, 'provider') and hasattr(adapter.provider, '_datetime_format'):
                datetime_format = adapter.provider._datetime_format
            context.set_symbol_and_format(symbol, datetime_format)
        
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
        
        # 9. Process remaining events (horizons beyond data end)
        self._process_remaining_events(merged_candles)
        
        # 10. Call on_stop for all components and collect results
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