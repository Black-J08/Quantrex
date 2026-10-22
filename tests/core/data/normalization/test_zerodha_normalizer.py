"""Tests for normalization layer."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from quantrex.core.broker.zerodha.historical.client import ZerodhaHistoricalDataClient
from quantrex.core.broker.zerodha.session.session import ZerodhaSession
from quantrex.core.data.normalization import ZerodhaNormalizer
from quantrex.core.models import OHLCVCandle, Timeframe, TimeframeUnit


class TestZerodhaNormalizer:
    """Tests for ZerodhaNormalizer."""

    def test_normalize_candles_success(self) -> None:
        """Test successful candle normalization."""
        normalizer = ZerodhaNormalizer()
        
        raw_response = {
            "status": "success",
            "data": {
                "candles": [
                    ["2024-01-15T09:15:00+05:30", 1500.0, 1510.0, 1495.0, 1505.0, 100000],
                    ["2024-01-15T09:16:00+05:30", 1505.0, 1515.0, 1500.0, 1510.0, 80000],
                ],
            },
        }
        
        candles = normalizer.normalize_candles(
            raw_response,
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        )
        
        assert len(candles) == 2
        assert all(isinstance(c, OHLCVCandle) for c in candles)
        assert candles[0].symbol == "NSE:INFY"
        assert candles[0].open == Decimal("1500.0")
        assert candles[0].high == Decimal("1510.0")
        assert candles[0].low == Decimal("1495.0")
        assert candles[0].close == Decimal("1505.0")
        assert candles[0].volume == Decimal(100000)

    def test_normalize_candles_with_oi(self) -> None:
        """Test normalization with open interest data."""
        normalizer = ZerodhaNormalizer()
        
        raw_response = {
            "status": "success",
            "data": {
                "candles": [
                    ["2024-01-15T09:15:00+05:30", 1500.0, 1510.0, 1495.0, 1505.0, 100000, 5000],
                ],
            },
        }
        
        candles = normalizer.normalize_candles(
            raw_response,
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        )
        
        assert len(candles) == 1
        assert candles[0].volume == Decimal(100000)

    def test_normalize_candles_api_error(self) -> None:
        """Test handling API error response."""
        normalizer = ZerodhaNormalizer()
        
        raw_response = {
            "status": "error",
            "message": "Invalid instrument_token",
        }
        
        with pytest.raises(Exception, match="API error"):
            normalizer.normalize_candles(
                raw_response,
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            )

    def test_normalize_candles_invalid_response_type(self) -> None:
        """Test handling invalid response type."""
        normalizer = ZerodhaNormalizer()
        
        with pytest.raises(Exception, match="Expected dict response"):
            normalizer.normalize_candles(
                "not a dict",
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            )

    def test_normalize_candles_invalid_candles_format(self) -> None:
        """Test handling invalid candles format."""
        normalizer = ZerodhaNormalizer()
        
        raw_response = {
            "status": "success",
            "data": {
                "candles": "not a list",
            },
        }
        
        with pytest.raises(Exception, match="Expected candles list"):
            normalizer.normalize_candles(
                raw_response,
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            )

    def test_normalize_candles_skips_invalid_candles(self) -> None:
        """Test that invalid candles are skipped with warning."""
        normalizer = ZerodhaNormalizer()
        
        raw_response = {
            "status": "success",
            "data": {
                "candles": [
                    ["2024-01-15T09:15:00+05:30", 1500.0, 1510.0, 1495.0, 1505.0, 100000],
                    ["invalid", "data", "here"],  # Invalid candle
                ],
            },
        }
        
        candles = normalizer.normalize_candles(
            raw_response,
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        )
        
        # Should only return the valid candle
        assert len(candles) == 1

    def test_map_timeframe_to_interval(self) -> None:
        """Test timeframe to interval mapping lives on the broker client."""
        client = ZerodhaHistoricalDataClient(MagicMock(spec=ZerodhaSession))

        assert client._map_timeframe_to_interval(Timeframe(value=1, unit=TimeframeUnit.MINUTE)).value == "minute"
        assert client._map_timeframe_to_interval(Timeframe(value=5, unit=TimeframeUnit.MINUTE)).value == "5minute"
        assert client._map_timeframe_to_interval(Timeframe(value=15, unit=TimeframeUnit.MINUTE)).value == "15minute"
        assert client._map_timeframe_to_interval(Timeframe(value=60, unit=TimeframeUnit.MINUTE)).value == "60minute"
        assert client._map_timeframe_to_interval(Timeframe(value=1, unit=TimeframeUnit.HOUR)).value == "60minute"
        assert client._map_timeframe_to_interval(Timeframe(value=1, unit=TimeframeUnit.DAY)).value == "day"

    def test_map_timeframe_to_interval_unsupported(self) -> None:
        """Test unsupported timeframe raises error on the broker client."""
        client = ZerodhaHistoricalDataClient(MagicMock(spec=ZerodhaSession))

        with pytest.raises(ValueError, match="Unsupported timeframe"):
            client._map_timeframe_to_interval(Timeframe(value=2, unit=TimeframeUnit.HOUR))

    def test_format_datetime(self) -> None:
        """Test datetime formatting lives on the broker client."""
        client = ZerodhaHistoricalDataClient(MagicMock(spec=ZerodhaSession))

        dt = datetime(2024, 1, 15, 9, 30, 0, tzinfo=UTC)
        formatted = client._format_datetime(dt)
        assert formatted == "2024-01-15 09:30:00"