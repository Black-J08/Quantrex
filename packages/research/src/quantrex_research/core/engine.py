"""ResearchEngine - Generic orchestrator for research components."""

import shutil
from collections.abc import Sequence, Mapping
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from quantrex_backtest import DataOrchestrator, BacktestConfig
from quantrex_backtest.data.orchestrator import DataOrchestratorConfig
from quantrex_core import InstrumentSpec
from quantrex_core.logging import get_logger
from quantrex_core.models import Candle
from quantrex_core.timeframe import TimeframeRegistry, TimeframeDispatcher, filter_candles_by_timeframe
from quantrex_core.timeframe.parser import interval_to_minutes

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
    
    def __init__(self, base_timeframe: str = "1M", origin_time: time | None = None) -> None:
        self._history: List[Candle] = []
        self._base_timeframe = base_timeframe
        self._derived_histories: Dict[str, List[Candle]] = {}
        self._derived_indices: Dict[str, int] = {}
        self._symbol = ""
        self._origin_time = origin_time
    
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
        # Derived timeframe candles are already properly aligned closed candles
        # (either from adapter natively or built incrementally), so return directly
        # Filter by current symbol
        candles = self._derived_histories.get(timeframe, [])
        if not candles:
            return ()
        return tuple(c for c in candles if c.symbol == self._symbol)
    
    def record_candle(self, candle: Candle) -> None:
        """Record a candle to history. Derived timeframes are pre-built by the engine."""
        self._history.append(candle)
        # Note: Derived timeframes are pre-built by ResearchEngine.run() before the loop
        # to enable indicator computation on them. We don't build them on-the-fly here.
    
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
        script_path: Optional[Union[str, Path]] = None,
    ) -> None:
        """Initialize the research engine.
        
        Args:
            instruments: List of instrument specifications.
            research_components: List of research components to run.
            data_start: Start date string (YYYY-MM-DD).
            data_end: End date string (YYYY-MM-DD).
            backtest_config: Optional BacktestConfig for data preparation.
            data_orchestrator_config: Optional DataOrchestratorConfig.
            script_path: Optional path to the research script file. If provided,
                the script will be copied to each component's output directory
                for reproducibility.
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
        self._script_path = Path(script_path).resolve() if script_path else None
        
        # Per-component event buffers
        self._event_buffers: Dict[ResearchComponent, List[BufferedEvent]] = {
            comp: [] for comp in research_components
        }
        
        # Current candle index for progress tracking
        self._current_candle: Optional[Candle] = None
    
    def _get_required_timeframes(self, component: ResearchComponent) -> list[str]:
        """Get timeframes required by a component.
        
        Base timeframe is always "1M". Additional timeframes come from @on_timeframe decorators.
        """
        timeframes = ["1M"]
        for attr_name in dir(component):
            attr = getattr(component, attr_name)
            if callable(attr) and hasattr(attr, '_quantrex_timeframe'):
                interval = attr._quantrex_timeframe
                if interval not in timeframes:
                    timeframes.append(interval)
        return timeframes

    def _build_derived_timeframe_data(
        self,
        base_rows: List[Dict[str, Any]],
        timeframe: str,
        datetime_format: str,
        symbol: str,
        origin_time: time | None = None,
    ) -> List[Dict[str, Any]]:
        """Build derived timeframe (e.g., 1H) raw rows from base (1M) rows.
        
        This mirrors ResearchContext._update_derived_timeframes but operates on raw rows
        before Candle creation, so indicators can be computed on derived timeframes too.
        Uses align_to_origin for correct interval alignment with market origin time.
        """
        from quantrex_core.timeframe.arithmetic import align_to_origin
        
        tf_minutes = interval_to_minutes(timeframe)
        if tf_minutes is None or tf_minutes <= 1:
            return []
        
        derived_rows = []
        current_bucket = None
        
        # Use origin_time for alignment (default to midnight if not provided)
        origin = origin_time if origin_time is not None else time(0, 0)
        
        for row in base_rows:
            dt_val = row["datetime"]
            if hasattr(dt_val, 'strftime'):
                dt = dt_val.to_pydatetime()
            else:
                dt = datetime.strptime(dt_val, datetime_format)
            
            # Use align_to_origin for correct interval alignment
            bucket_timestamp = align_to_origin(dt, origin, tf_minutes)
            bucket_key = f"{dt.date()}_{bucket_timestamp.hour:02d}:{bucket_timestamp.minute:02d}"
            
            if current_bucket is None or current_bucket["key"] != bucket_key:
                # Finalize previous bucket
                if current_bucket is not None:
                    bucket = current_bucket["data"]
                    derived_rows.append({
                        "datetime": bucket["timestamp"].strftime(datetime_format),
                        "open": str(bucket["open"]),
                        "high": str(bucket["high"]),
                        "low": str(bucket["low"]),
                        "close": str(bucket["close"]),
                        "volume": str(bucket["volume"]),
                    })
                
                # Start new bucket
                current_bucket = {
                    "key": bucket_key,
                    "data": {
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row["volume"]),
                        "timestamp": bucket_timestamp,
                    }
                }
            else:
                # Update current bucket
                bucket = current_bucket["data"]
                bucket["high"] = max(bucket["high"], float(row["high"]))
                bucket["low"] = min(bucket["low"], float(row["low"]))
                bucket["close"] = float(row["close"])
                bucket["volume"] += float(row["volume"])
        
        # Finalize last bucket
        if current_bucket is not None:
            bucket = current_bucket["data"]
            derived_rows.append({
                "datetime": bucket["timestamp"].strftime(datetime_format),
                "open": str(bucket["open"]),
                "high": str(bucket["high"]),
                "low": str(bucket["low"]),
                "close": str(bucket["close"]),
                "volume": str(bucket["volume"]),
            })
        
        return derived_rows

    def run(self) -> Dict[str, Any]:
        """Run the research engine.
        
        Returns:
            Dictionary mapping component class name to component result.
        """
        logger.info("Starting ResearchEngine with %d components", len(self.research_components))
        
        # Get origin_time from first instrument's adapter (for timeframe alignment)
        origin_time = None
        if self.instruments:
            first_adapter = self.instruments[0].adapter
            if hasattr(first_adapter, 'get_origin_time'):
                origin_time = first_adapter.get_origin_time()
        
        # 1. Load and prepare data via DataOrchestrator (raw rows, not candles yet)
        logger.info("Loading data via DataOrchestrator...")
        data_orchestrator = DataOrchestrator(self.data_orchestrator_config)
        symbol_base_data = data_orchestrator.validate_and_prepare(
            self.instruments, self.backtest_config
        )
        
        if not symbol_base_data:
            logger.warning("No data available for any instrument; research completed with zero candles")
            for component in self.research_components:
                component.set_event_receiver(self)
                component.on_start()
            return self._finalize_components()
        
        logger.info("Loaded base data for %d symbols", len(symbol_base_data))
        for symbol, rows in symbol_base_data.items():
            logger.info("  %s: %d base rows", symbol, len(rows))
        
        # 2. Determine required timeframes for each component
        component_timeframes: Dict[ResearchComponent, List[str]] = {}
        all_timeframes: set[str] = {"1M"}
        for component in self.research_components:
            tfs = self._get_required_timeframes(component)
            component_timeframes[component] = tfs
            all_timeframes.update(tfs)
        
        # 3. Build raw data for all required timeframes (base + derived)
        # Structure: {symbol: {timeframe: List[raw_rows]}}
        all_raw_data: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        
        for symbol, base_rows in symbol_base_data.items():
            all_raw_data[symbol] = {"1M": base_rows}
            
            # Get datetime format for this symbol
            adapter = next((inst.adapter for inst in self.instruments if inst.symbol == symbol), None)
            datetime_format = "%Y-%m-%d %H:%M:%S"
            if adapter and hasattr(adapter, 'datetime_format'):
                datetime_format = adapter.datetime_format
            elif adapter and hasattr(adapter, 'provider') and hasattr(adapter.provider, '_datetime_format'):
                datetime_format = adapter.provider._datetime_format
            
            # Read additional timeframes from adapters (like backtest engine)
            # This allows adapters to provide native higher timeframe data
            additional_timeframes: list[str] = [tf for tf in all_timeframes if tf != "1M"]
            for tf in additional_timeframes:
                try:
                    adapter_rows = adapter.read_timeframe(
                        tf,
                        from_date=self.data_start,
                        to_date=self.data_end,
                    )
                    if adapter_rows:
                        all_raw_data[symbol][tf] = adapter_rows
                        logger.info("  %s: read %d rows for timeframe %s from adapter", symbol, len(adapter_rows), tf)
                    else:
                        # Fall back to building from 1M data
                        derived_rows = self._build_derived_timeframe_data(base_rows, tf, datetime_format, symbol, origin_time)
                        if derived_rows:
                            all_raw_data[symbol][tf] = derived_rows
                            logger.info("  %s: built %d rows for derived timeframe %s", symbol, len(derived_rows), tf)
                except Exception as e:
                    logger.warning("Failed to read timeframe %s from adapter for %s: %s. Building from 1M.", tf, symbol, e)
                    # Fall back to building from 1M data
                    derived_rows = self._build_derived_timeframe_data(base_rows, tf, datetime_format, symbol, origin_time)
                    if derived_rows:
                        all_raw_data[symbol][tf] = derived_rows
                        logger.info("  %s: built %d rows for derived timeframe %s", symbol, len(derived_rows), tf)
        
        # 4. Sort all raw data by datetime for each symbol and timeframe
        for symbol in all_raw_data:
            for tf in all_raw_data[symbol]:
                adapter = next((inst.adapter for inst in self.instruments if inst.symbol == symbol), None)
                dt_format = datetime_format
                if adapter and hasattr(adapter, 'datetime_format'):
                    dt_format = adapter.datetime_format
                all_raw_data[symbol][tf].sort(
                    key=lambda row: datetime.strptime(row.get("datetime", ""), dt_format)
                    if isinstance(row.get("datetime"), str) else row.get("datetime", datetime.min)
                )
        
        # 5. Compute indicators for each component, symbol, and timeframe
        # Structure: {component: {symbol: {timeframe: List[Dict[indicator_name -> value]]}}}
        all_indicators: Dict[ResearchComponent, Dict[str, Dict[str, List[Dict[str, float | int | None]]]]] = {}
        
        for component in self.research_components:
            all_indicators[component] = {}
            for symbol in all_raw_data:
                all_indicators[component][symbol] = {}
                for tf in all_raw_data[symbol]:
                    try:
                        indicators = component.compute_indicators(
                            all_raw_data[symbol][tf], timeframe=tf
                        )
                        # Validate length matches
                        if len(indicators) != len(all_raw_data[symbol][tf]):
                            logger.exception(
                                "compute_indicators returned %d entries for %d candles (symbol %s, timeframe %s)",
                                len(indicators), len(all_raw_data[symbol][tf]), symbol, tf,
                            )
                            raise ValueError(
                                f"compute_indicators returned {len(indicators)} entries "
                                f"for {len(all_raw_data[symbol][tf])} candles (symbol {symbol}, timeframe {tf}); length must match"
                            )
                        all_indicators[component][symbol][tf] = indicators
                        logger.debug(
                            "Computed indicators for component %s, symbol %s, timeframe %s: %d entries",
                            component.__class__.__name__, symbol, tf, len(indicators)
                        )
                    except Exception as e:
                        logger.exception(
                            "Component.compute_indicators raised for %s symbol %s timeframe %s",
                            component.__class__.__name__, symbol, tf
                        )
                        raise ValueError(
                            f"Component {component.__class__.__name__}.compute_indicators failed for {symbol} timeframe {tf}: {e}"
                        ) from e
        
        # 6. Prepare base timeframe candles for the main loop (with indicators)
        # Structure: {symbol: List[Candle]} for base timeframe only
        base_candles_by_symbol: Dict[str, List[Candle]] = {}
        
        for symbol in all_raw_data:
            if "1M" not in all_raw_data[symbol]:
                continue
            candles = []
            adapter = next((inst.adapter for inst in self.instruments if inst.symbol == symbol), None)
            datetime_format = "%Y-%m-%d %H:%M:%S"
            if adapter and hasattr(adapter, 'datetime_format'):
                datetime_format = adapter.datetime_format
            elif adapter and hasattr(adapter, 'provider') and hasattr(adapter.provider, '_datetime_format'):
                datetime_format = adapter.provider._datetime_format
            
            for idx, row in enumerate(all_raw_data[symbol]["1M"]):
                # Get indicators for each component for this candle
                merged_indicators: Dict[str, float | int | None] = {}
                for component in self.research_components:
                    comp_indicators = all_indicators[component][symbol]["1M"][idx]
                    merged_indicators.update(comp_indicators)
                
                candle = Candle.from_row(
                    row,
                    symbol=symbol,
                    timeframe="1M",
                    datetime_format=datetime_format,
                    indicators=merged_indicators,
                )
                candles.append(candle)
            base_candles_by_symbol[symbol] = candles
            logger.info("  %s: created %d base candles", symbol, len(candles))
        
        # 7. Merge base timeframe candles into single time-ordered stream for the main loop
        merged_candles = merge_candle_streams(base_candles_by_symbol)
        logger.info("Merged base candle stream: %d total candles", len(merged_candles))
        
        # 8. Call on_start for all components
        for component in self.research_components:
            component.set_event_receiver(self)
            component.on_start()
        
        if not merged_candles:
            logger.warning("No base candles loaded, exiting")
            return self._finalize_components()
        
        # 9. Main candle loop
        logger.info("Starting candle loop...")
        
        # Create research context for history/timeframe access
        context = ResearchContext(base_timeframe="1M", origin_time=origin_time)
        
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
        
        # Track derived timeframe building state per symbol
        # For timeframes provided by adapter natively: pre-build candles with indicators,
        # but add to context incrementally based on close_time for look-ahead prevention
        # For timeframes built from 1M: build incrementally from 1M data
        derived_state: Dict[str, Dict[str, Dict[str, Any]]] = {}
        prebuilt_native_candles: Dict[str, Dict[str, List[Candle]]] = {}
        
        for symbol in all_raw_data:
            derived_state[symbol] = {}
            prebuilt_native_candles[symbol] = {}
            adapter = next((inst.adapter for inst in self.instruments if inst.symbol == symbol), None)
            
            for tf in all_raw_data[symbol]:
                if tf == "1M":
                    continue
                
                # Check if this timeframe was provided by adapter natively
                is_native = False
                if adapter and hasattr(adapter, 'supported_timeframes'):
                    is_native = tf in adapter.supported_timeframes
                
                if is_native:
                    # Pre-build all candles for this native timeframe with indicators
                    candles: List[Candle] = []
                    datetime_format = "%Y-%m-%d %H:%M:%S"
                    if adapter and hasattr(adapter, 'datetime_format'):
                        datetime_format = adapter.datetime_format
                    elif adapter and hasattr(adapter, 'provider') and hasattr(adapter.provider, '_datetime_format'):
                        datetime_format = adapter.provider._datetime_format
                    
                    for idx, row in enumerate(all_raw_data[symbol][tf]):
                        merged_indicators: Dict[str, float | int | None] = {}
                        for component in self.research_components:
                            comp_indicators = all_indicators[component][symbol][tf][idx]
                            merged_indicators.update(comp_indicators)
                        
                        candle = Candle.from_row(
                            row,
                            symbol=symbol,
                            timeframe=tf,
                            datetime_format=datetime_format,
                            indicators=merged_indicators,
                        )
                        candles.append(candle)
                    prebuilt_native_candles[symbol][tf] = candles
                    logger.info("  %s: pre-built %d candles for native timeframe %s", symbol, len(candles), tf)
                else:
                    # Build incrementally from 1M data
                    derived_state[symbol][tf] = {
                        "rows": all_raw_data[symbol][tf],
                        "indicators": {comp: all_indicators[comp][symbol][tf] for comp in self.research_components},
                        "next_index": 0,
                        "current_bucket": None,
                    }
        
        # Track next native candle to dispatch per symbol/timeframe
        native_candle_indices: Dict[str, Dict[str, int]] = {}
        for symbol in prebuilt_native_candles:
            native_candle_indices[symbol] = {}
            for tf in prebuilt_native_candles[symbol]:
                native_candle_indices[symbol][tf] = 0
        
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
            
            # Update derived timeframes incrementally for timeframes built from 1M data
            # This ensures derived candles are only visible at their close time
            self._update_derived_timeframes_incremental(candle, derived_state, context)
            
            # Dispatch native timeframe candles that have closed by this execution time
            # Execution time = current candle's close_time
            # Only add native candles for the current symbol
            execution_time = candle.close_time
            symbol = candle.symbol
            if symbol in prebuilt_native_candles:
                for tf in prebuilt_native_candles[symbol]:
                    idx = native_candle_indices[symbol][tf]
                    while idx < len(prebuilt_native_candles[symbol][tf]):
                        native_candle = prebuilt_native_candles[symbol][tf][idx]
                        if native_candle.close_time <= execution_time:
                            # This native candle has closed, add to context history
                            if tf not in context._derived_histories:
                                context._derived_histories[tf] = []
                            context._derived_histories[tf].append(native_candle)
                            idx += 1
                        else:
                            break
                    native_candle_indices[symbol][tf] = idx
            
            # Dispatch timeframe methods (e.g., @on_timeframe("1H"))
            dispatcher.dispatch_all(context, candle.symbol)
            
            # Dispatch to all components
            for component in self.research_components:
                component.on_candle(candle)
            
            # Check buffered events for elapsed horizons
            self._process_elapsed_horizons(candle, merged_candles)
        
        # 10. Process remaining events (horizons beyond data end)
        self._process_remaining_events(merged_candles)
        
        # 11. Call on_stop for all components and collect results
        results = self._finalize_components()
        
        logger.info("ResearchEngine completed")
        return results

    def _update_derived_timeframes_incremental(
        self,
        candle: Candle,
        derived_state: Dict[str, Dict[str, Dict[str, Any]]],
        context: "ResearchContext",
    ) -> None:
        """Update derived timeframes incrementally, creating candles only when buckets complete.
        
        This mirrors the original ResearchContext._update_derived_timeframes but also
        attaches pre-computed indicators to derived candles when they're created.
        Uses align_to_origin for correct interval alignment with market origin time.
        """
        from quantrex_core.timeframe.arithmetic import align_to_origin
        
        symbol = candle.symbol
        if symbol not in derived_state:
            return
        
        # Get origin_time from context
        origin_time = context._origin_time if context._origin_time is not None else time(0, 0)
        
        for tf, state in derived_state[symbol].items():
            tf_minutes = interval_to_minutes(tf)
            if tf_minutes is None or tf_minutes <= 1:
                continue
            
            dt = candle.timestamp
            # Use align_to_origin for correct interval alignment
            bucket_timestamp = align_to_origin(dt, origin_time, tf_minutes)
            bucket_key = f"{dt.date()}_{bucket_timestamp.hour:02d}:{bucket_timestamp.minute:02d}"
            
            if state["current_bucket"] is None or state["current_bucket"]["key"] != bucket_key:
                # Finalize previous bucket if exists
                if state["current_bucket"] is not None:
                    bucket = state["current_bucket"]["data"]
                    idx = state["next_index"] - 1
                    
                    # Get merged indicators for this derived candle
                    merged_indicators: Dict[str, float | int | None] = {}
                    for component in self.research_components:
                        comp_indicators = state["indicators"][component][idx]
                        merged_indicators.update(comp_indicators)
                    
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
                        indicators=merged_indicators,
                    )
                    
                    if tf not in context._derived_histories:
                        context._derived_histories[tf] = []
                    context._derived_histories[tf].append(derived_candle)
                
                # Start new bucket
                state["current_bucket"] = {
                    "key": bucket_key,
                    "data": {
                        "open": candle.open,
                        "high": candle.high,
                        "low": candle.low,
                        "close": candle.close,
                        "volume": candle.volume,
                        "timestamp": bucket_timestamp,
                        "symbol": symbol,
                    }
                }
                state["next_index"] += 1
            else:
                # Update current bucket
                bucket = state["current_bucket"]["data"]
                bucket["high"] = max(bucket["high"], candle.high)
                bucket["low"] = min(bucket["low"], candle.low)
                bucket["close"] = candle.close
                bucket["volume"] += candle.volume
            
            # Check if this is the last minute of the bucket
            # Next candle's interval start
            next_dt = dt + timedelta(minutes=1)
            next_bucket_timestamp = align_to_origin(next_dt, origin_time, tf_minutes)
            if next_bucket_timestamp != bucket_timestamp:
                # Bucket complete - create candle and add to history
                bucket = state["current_bucket"]["data"]
                idx = state["next_index"] - 1
                
                # Get merged indicators for this derived candle
                merged_indicators: Dict[str, float | int | None] = {}
                for component in self.research_components:
                    comp_indicators = state["indicators"][component][idx]
                    merged_indicators.update(comp_indicators)
                
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
                    indicators=merged_indicators,
                )
                
                if tf not in context._derived_histories:
                    context._derived_histories[tf] = []
                context._derived_histories[tf].append(derived_candle)
                
                state["current_bucket"] = None
    
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
            
            # Copy research script for reproducibility
            if self._script_path and self._script_path.is_file():
                script_dest = component_output_dir / "research_script.py"
                try:
                    shutil.copy2(self._script_path, script_dest)
                    logger.debug("Copied research script to %s", script_dest)
                except Exception as e:
                    logger.warning("Failed to copy research script to %s: %s", script_dest, e)
            
            # Component writes its own artifacts
            result = component.on_stop(component_output_dir)
            results[component.__class__.__name__] = result
            
        return results