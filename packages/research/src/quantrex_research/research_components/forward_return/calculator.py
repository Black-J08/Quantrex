"""ForwardReturnCalculator - Pure percentage forward return calculation."""

from datetime import timedelta
from typing import Dict, List, Optional

from quantrex_core.models import Candle

from quantrex_research.research_components.forward_return.models import ForwardReturnEvent, ForwardReturnSeries


class ForwardReturnCalculator:
    """Pure function calculator for percentage forward returns.
    
    Calculates percentage forward returns: (close[t+h] - close[t]) / close[t] * 100
    Uses Candle.close for both event price and horizon price.
    """
    
    @staticmethod
    def calculate(
        candles: List[Candle],
        event: ForwardReturnEvent,
        elapsed_horizons: List[timedelta]
    ) -> ForwardReturnSeries:
        """Calculate percentage forward returns for elapsed horizons.
        
        Args:
            candles: Full list of candles (time-ordered).
            event: The research event containing the emission candle.
            elapsed_horizons: List of horizons that have elapsed (current_candle.timestamp >= event_candle.close_time + horizon).
            
        Returns:
            ForwardReturnSeries with percentage returns for each elapsed horizon.
        """
        event_candle = event.candle
        event_price = event_candle.close
        
        # Find the index of the event candle in the full candle list
        # The event candle might be from a different timeframe (e.g., 1H) than the base candles (1M)
        # So we search by timestamp and symbol instead of object identity
        event_index = None
        for i, candle in enumerate(candles):
            if candle.symbol == event_candle.symbol and candle.timestamp == event_candle.timestamp:
                event_index = i
                break
        
        # If not found by timestamp, try to find by close_time (for higher timeframe candles)
        if event_index is None:
            for i, candle in enumerate(candles):
                if candle.symbol == event_candle.symbol and candle.close_time == event_candle.close_time:
                    event_index = i
                    break
        
        if event_index is None:
            raise ValueError(f"Event candle not found in candle list (symbol={event_candle.symbol}, timestamp={event_candle.timestamp}, close_time={event_candle.close_time})")
        
        returns: Dict[timedelta, Optional[float]] = {}
        
        for horizon in elapsed_horizons:
            target_index = event_index + 1  # Start from next candle
            
            # Find the candle at or after the horizon elapsed time
            # Horizon is measured from event_candle.timestamp (open time)
            target_time = event_candle.timestamp + horizon
            
            # Search for the first candle with timestamp >= target_time
            horizon_candle = None
            for i in range(event_index + 1, len(candles)):
                if candles[i].timestamp >= target_time:
                    horizon_candle = candles[i]
                    break
            
            if horizon_candle is not None:
                horizon_price = horizon_candle.close
                # Percentage return: (close[t+h] - close[t]) / close[t] * 100
                pct_return = ((horizon_price - event_price) / event_price) * 100
                returns[horizon] = pct_return
            else:
                # Horizon extends beyond available data
                returns[horizon] = None
        
        return ForwardReturnSeries(event=event, returns=returns)
    
    @staticmethod
    def calculate_all_horizons(
        candles: List[Candle],
        event: ForwardReturnEvent,
        all_horizons: List[timedelta]
    ) -> ForwardReturnSeries:
        """Calculate percentage forward returns for all horizons (including incomplete).
        
        Args:
            candles: Full list of candles (time-ordered).
            event: The research event containing the emission candle.
            all_horizons: All configured horizons.
            
        Returns:
            ForwardReturnSeries with percentage returns for all horizons (None for incomplete).
        """
        event_candle = event.candle
        event_price = event_candle.close
        
        # Find the index of the event candle
        event_index = None
        for i, candle in enumerate(candles):
            if candle is event_candle:
                event_index = i
                break
        
        if event_index is None:
            raise ValueError("Event candle not found in candle list")
        
        returns: Dict[timedelta, Optional[float]] = {}
        
        for horizon in all_horizons:
            target_time = event_candle.timestamp + horizon
            
            horizon_candle = None
            for i in range(event_index + 1, len(candles)):
                if candles[i].timestamp >= target_time:
                    horizon_candle = candles[i]
                    break
            
            if horizon_candle is not None:
                horizon_price = horizon_candle.close
                pct_return = ((horizon_price - event_price) / event_price) * 100
                returns[horizon] = pct_return
            else:
                returns[horizon] = None
        
        return ForwardReturnSeries(event=event, returns=returns)