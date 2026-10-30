"""Time-forward distribution logic for research.

Computes forward returns over configured horizons for research events
emitted by a strategy.
"""

from __future__ import annotations

from datetime import datetime

from quantrex.core.models.market_data import OHLCVCandle


class ForwardReturnsDistribution:
    """Calculates forward returns over multiple horizons for events.

    Given a sequence of candles and a set of events (each with a
    timestamp and symbol), computes the forward return over each
    configured horizon.
    """

    def __init__(self, horizons: list[int]) -> None:
        """Initialize with a list of look-ahead horizons (in bars).

        Args:
            horizons: List of horizon lengths (number of bars forward).
        """
        self.horizons = horizons

    def compute(
        self,
        candles: list[OHLCVCandle],
        events: list[dict[str, object]],
    ) -> dict[str, list[float]]:
        """Compute forward returns for each event over each horizon.

        Args:
            candles: Time-sorted list of candles.
            events: List of event dicts with 'timestamp' and 'symbol'.

        Returns:
            A mapping of horizon (as string) to list of forward returns.
        """
        results: dict[str, list[float]] = {str(h): [] for h in self.horizons}

        # Build a lookup: symbol -> list of (index, close)
        symbol_to_candles: dict[str, list[tuple[int, float]]] = {}
        for idx, candle in enumerate(candles):
            symbol_to_candles.setdefault(candle.symbol, []).append((idx, float(candle.close)))

        for event in events:
            event_ts = event.get("timestamp")
            event_symbol = event.get("symbol")
            if not isinstance(event_ts, datetime) or event_symbol not in symbol_to_candles:
                continue

            # Find the candle index at or after the event timestamp
            start_idx = None
            for idx, _ in symbol_to_candles[event_symbol]:
                if candles[idx].timestamp >= event_ts:
                    start_idx = idx
                    break
            if start_idx is None:
                continue

            for h in self.horizons:
                target_idx = start_idx + h
                if target_idx < len(candles):
                    entry = candles[start_idx].close
                    exit_ = candles[target_idx].close
                    if entry != 0:
                        ret = (float(exit_) - float(entry)) / float(entry)
                        results[str(h)].append(ret)

        return results
