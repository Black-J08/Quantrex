"""Tests for Candle model."""

import pytest
from quantrex_core import Candle
from datetime import datetime


def test_candle_creation():
    """Candle can be created with all required fields."""
    candle = Candle(
        symbol="TEST",
        timestamp=datetime(2023, 1, 1, 9, 30),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000
    )
    
    assert candle.symbol == "TEST"
    assert candle.timestamp == datetime(2023, 1, 1, 9, 30)
    assert candle.open == 100.0
    assert candle.high == 101.0
    assert candle.low == 99.0
    assert candle.close == 100.5
    assert candle.volume == 1000


def test_candle_is_immutable():
    """Candle is immutable (frozen dataclass)."""
    candle = Candle(
        symbol="TEST",
        timestamp=datetime(2023, 1, 1, 9, 30),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000
    )
    
    with pytest.raises(AttributeError):
        candle.symbol = "OTHER"


def test_candle_from_row():
    """Candle can be created from a raw data row."""
    row = {
        "datetime": "20230101 09:30",
        "open": "100.0",
        "high": "101.0",
        "low": "99.0",
        "close": "100.5",
        "volume": "1000"
    }
    
    candle = Candle.from_row(row, "TEST")
    
    assert candle.symbol == "TEST"
    assert candle.timestamp == datetime(2023, 1, 1, 9, 30)
    assert candle.open == 100.0
    assert candle.high == 101.0
    assert candle.low == 99.0
    assert candle.close == 100.5
    assert candle.volume == 1000


def test_candle_from_row_custom_format():
    """Candle can be created with custom datetime format."""
    row = {
        "datetime": "2023-01-01 09:30:00",
        "open": "100.0",
        "high": "101.0",
        "low": "99.0",
        "close": "100.5",
        "volume": "1000"
    }
    
    candle = Candle.from_row(row, "TEST", datetime_format="%Y-%m-%d %H:%M:%S")
    
    assert candle.timestamp == datetime(2023, 1, 1, 9, 30, 0)


def test_candle_from_row_missing_key():
    """Candle.from_row raises ValueError for missing keys."""
    row = {
        "datetime": "20230101 09:30",
        "open": "100.0",
        "high": "101.0",
        "low": "99.0",
        # missing close and volume
    }
    
    with pytest.raises(ValueError, match="Missing required key"):
        Candle.from_row(row, "TEST")


def test_candle_from_row_invalid_values():
    """Candle.from_row raises ValueError for invalid values."""
    row = {
        "datetime": "20230101 09:30",
        "open": "not_a_number",
        "high": "101.0",
        "low": "99.0",
        "close": "100.5",
        "volume": "1000"
    }
    
    with pytest.raises(ValueError, match="Failed to parse row values"):
        Candle.from_row(row, "TEST")