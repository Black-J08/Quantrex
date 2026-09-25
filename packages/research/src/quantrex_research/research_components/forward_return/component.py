"""ForwardReturnComponent - Concrete research component for forward return distribution."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.logging import get_logger

from quantrex_research.core.base import ResearchComponent
from quantrex_research.research_components.forward_return.config import ForwardReturnConfig
from quantrex_research.research_components.forward_return.models import (
    ForwardReturnEvent,
    ForwardReturnResult,
    ForwardReturnSeries,
)
from quantrex_research.research_components.forward_return.calculator import ForwardReturnCalculator
from quantrex_research.research_components.forward_return.aggregator import ForwardReturnAggregator
from quantrex_research.research_components.forward_return.visualization import (
    plot_distribution,
    plot_qq,
    plot_tail_comparison,
    plot_horizon_comparison,
)

logger = get_logger(__name__)


class ForwardReturnComponent(ResearchComponent):
    """Concrete research component for forward return distribution analysis.
    
    Implements the ResearchComponent interface. Handles forward-return-specific logic:
    configuration, event detection, incremental calculation, aggregation, and artifact writing.
    """
    
    def __init__(self, config: ForwardReturnConfig) -> None:
        """Initialize with configuration.
        
        Args:
            config: ForwardReturnConfig with horizons and other settings.
        """
        super().__init__()
        self._config = config
        self._events: List[ForwardReturnEvent] = []
        self._series_list: List[ForwardReturnSeries] = []
        self._result: Optional[ForwardReturnResult] = None
    
    @property
    def config(self) -> ForwardReturnConfig:
        return self._config
    
    def on_start(self) -> None:
        """Initialize component state."""
        self._events = []
        self._series_list = []
        self._result = None
        logger.info("ForwardReturnComponent started with horizons: %s", self._config.horizons)
    
    def on_candle(self, candle: Candle) -> None:
        """Process a single candle - override in subclass to detect events.
        
        Args:
            candle: The current candle being processed.
        """
        # Store current candle for emit_event
        self.current_candle = candle
        
        # This method should be overridden by the user to implement event detection
        # Example:
        # if self._detect_breakout(candle):
        #     self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {"reason": "breakout"})
        pass
    
    def get_horizons(self) -> List[timedelta]:
        """Return configured horizons."""
        return self._config.horizons
    
    def on_returns_calculated(self, event: ForwardReturnEvent, series: ForwardReturnSeries) -> None:
        """Receive incremental forward return series from engine.
        
        Args:
            event: The research event.
            series: Calculated forward return series for elapsed horizons.
        """
        self._series_list.append(series)
        logger.debug("Received returns for event %s at %s: %s", event.symbol, event.timestamp, series.returns)
    
    def on_stop(self, output_dir: Path) -> ForwardReturnResult:
        """Finalize aggregation, write artifacts, return result.
        
        Args:
            output_dir: Directory to write output artifacts.
            
        Returns:
            ForwardReturnResult with aggregated statistics.
        """
        logger.info("ForwardReturnComponent stopping, finalizing results for %d events", len(self._events))
        
        # If we have events but no series (e.g., all horizons incomplete), calculate all now
        if self._events and not self._series_list:
            # This shouldn't happen in normal operation, but handle gracefully
            from quantrex_research.utils.data_helpers import merge_candle_streams
            # We need the full candle stream - this would come from the engine
            # For now, we'll aggregate what we have
            pass
        
        # Aggregate all series
        self._result = ForwardReturnAggregator.aggregate(self._series_list)
        
        # Write artifacts
        self._write_artifacts(output_dir)
        
        logger.info("ForwardReturnComponent completed, wrote artifacts to %s", output_dir)
        return self._result
    
    def _write_artifacts(self, output_dir: Path) -> None:
        """Write all output artifacts to the output directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        plots_dir = output_dir / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Write JSON statistics
        import json
        json_path = output_dir / "forward_returns.json"
        with open(json_path, "w") as f:
            json.dump(self._result.to_dict(), f, indent=2, default=str)
        logger.info("Wrote statistics to %s", json_path)
        
        # 2. Write CSV raw returns
        import csv
        csv_path = output_dir / "forward_returns.csv"
        if self._result.raw_returns:
            horizons = sorted(self._result.raw_returns.keys())
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                # Header
                header = ["event_symbol", "event_timestamp", "event_direction"] + [str(h) for h in horizons]
                writer.writerow(header)
                # Data rows - need to reconstruct from series_list
                for series in self._series_list:
                    row = [
                        series.event.symbol,
                        series.event.timestamp.isoformat(),
                        series.event.direction.name,
                    ]
                    for h in horizons:
                        ret = series.returns.get(h)
                        row.append(ret if ret is not None else "")
                    writer.writerow(row)
        logger.info("Wrote raw returns to %s", csv_path)
        
        # 3. Write Parquet (optional, requires pyarrow)
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            
            parquet_path = output_dir / "forward_returns.parquet"
            if self._result.raw_returns:
                horizons = sorted(self._result.raw_returns.keys())
                data = {
                    "event_symbol": [],
                    "event_timestamp": [],
                    "event_direction": [],
                }
                for h in horizons:
                    data[str(h)] = []
                
                for series in self._series_list:
                    data["event_symbol"].append(series.event.symbol)
                    data["event_timestamp"].append(series.event.timestamp.isoformat())
                    data["event_direction"].append(series.event.direction.name)
                    for h in horizons:
                        ret = series.returns.get(h)
                        data[str(h)].append(ret if ret is not None else None)
                
                table = pa.table(data)
                pq.write_table(table, parquet_path)
                logger.info("Wrote parquet to %s", parquet_path)
        except ImportError:
            logger.debug("pyarrow not available, skipping parquet output")
        
        # 4. Generate plots
        if self._result.raw_returns:
            for horizon in sorted(self._result.raw_returns.keys()):
                returns = self._result.raw_returns[horizon]
                stats = self._result.horizon_stats.get(horizon, {})
                
                if returns:
                    # Distribution plot
                    plot_distribution(
                        returns, horizon, stats,
                        plots_dir / f"distribution_{horizon}.png"
                    )
                    
                    # Q-Q plot
                    plot_qq(
                        returns, horizon,
                        plots_dir / f"qq_{horizon}.png"
                    )
                    
                    # Tail comparison
                    plot_tail_comparison(
                        returns, horizon, stats,
                        plots_dir / f"tail_comparison_{horizon}.png"
                    )
            
            # Horizon comparison plot
            plot_horizon_comparison(
                self._result.horizon_stats,
                plots_dir / "horizon_comparison.png"
            )
        
        logger.info("Wrote plots to %s", plots_dir)