"""Tests for Candle model."""

import pytest
from quantrex_core import Candle
from datetime import datetime, timedelta


def test_candle_creation():
    """Candle can be created with all required fields."""
    timestamp = datetime(2023, 1, 1, 9, 30)
    timeframe = "1M"
    close_time = timestamp + timedelta(minutes=1)
    
    candle = Candle(
        symbol="TEST",
        timestamp=timestamp,
        close_time=close_time,
        timeframe=timeframe,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000
    )
    
    assert candle.symbol == "TEST"
    assert candle.timestamp == timestamp
    assert candle.close_time == close_time
    assert candle.timeframe == timeframe
    assert candle.open == 100.0
    assert candle.high == 101.0
    assert candle.low == 99.0
    assert candle.close == 100.5
    assert candle.volume == 1000


def test_candle_is_immutable():
    """Candle is immutable (frozen dataclass)."""
    timestamp = datetime(2023, 1, 1, 9, 30)
    timeframe = "1M"
    close_time = timestamp + timedelta(minutes=1)
    
    candle = Candle(
        symbol="TEST",
        timestamp=timestamp,
        close_time=close_time,
        timeframe=timeframe,
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
    
    candle = Candle.from_row(row, "TEST", "1M")
    
    assert candle.symbol == "TEST"
    assert candle.timestamp == datetime(2023, 1, 1, 9, 30)
    assert candle.close_time == datetime(2023, 1, 1, 9, 31)
    assert candle.timeframe == "1M"
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
    
    candle = Candle.from_row(row, "TEST", "1M", datetime_format="%Y-%m-%d %H:%M:%S")
    
    assert candle.timestamp == datetime(2023, 1, 1, 9, 30, 0)
    assert candle.close_time == datetime(2023, 1, 1, 9, 31, 0)
    assert candle.timeframe == "1M"


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
        Candle.from_row(row, "TEST", "1M")


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
        Candle.from_row(row, "TEST", "1M")


# ---------------------------------------------------------------------------
# Regression tests for the precomputed indicator API (Candle.indicators).
# A bug fix without a regression test is not a fix — see project AGENTS.md
# "Standing Rule: Regression Tests for Every Bug Fix".
# ---------------------------------------------------------------------------


def test_candle_default_indicators_is_empty_mapping():
    """A newly constructed Candle exposes an empty, read-only indicators bag.

    Regression: default ``indicators`` must be an empty mapping (not a
    shared mutable sentinel), and the surface must be a ``MappingProxyType``
    so per-bar mutation is impossible.
    """
    from types import MappingProxyType

    candle = Candle(
        symbol="TEST",
        timestamp=datetime(2023, 1, 1, 9, 30),
        close_time=datetime(2023, 1, 1, 9, 31),
        timeframe="1M",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000,
    )

    assert dict(candle.indicators) == {}
    assert isinstance(candle.indicators, MappingProxyType)


def test_candle_indicators_via_from_row():
    """``Candle.from_row`` accepts an ``indicators`` kwarg and round-trips it.

    Regression: the engine threads precomputed per-bar indicators through
    ``Candle.from_row(row, ..., indicators=per_bar[i])``. The constructor
    must accept the kwarg and the values must be readable post-construction.
    """
    row = {
        "datetime": "20230101 09:30",
        "open": "100.0",
        "high": "101.0",
        "low": "99.0",
        "close": "100.5",
        "volume": "1000",
    }

    candle = Candle.from_row(
        row,
        "TEST",
        "1M",
        indicators={"sma20": 100.5, "rsi14": 55, "warmup": None},
    )

    assert candle.indicators["sma20"] == 100.5
    assert candle.indicators["rsi14"] == 55
    assert candle.indicators["warmup"] is None


def test_candle_immutability_extends_to_indicators():
    """Assigning into ``candle.indicators`` raises ``TypeError``.

    Regression: the per-bar indicators bag must be immutable at runtime
    so a buggy strategy cannot mutate another bar's indicators after
    the fact. The frozen dataclass only protects the field *binding*;
    ``MappingProxyType`` (wrapped in ``__post_init__``) blocks item
    assignment.
    """
    candle = Candle(
        symbol="TEST",
        timestamp=datetime(2023, 1, 1, 9, 30),
        close_time=datetime(2023, 1, 1, 9, 31),
        timeframe="1M",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000,
        indicators={"sma20": 100.5},
    )

    with pytest.raises(TypeError):
        candle.indicators["sma20"] = 999.0  # type: ignore[index]

    with pytest.raises(TypeError):
        candle.indicators["new"] = 1  # type: ignore[index]


def test_candle_close_time_validation():
    """Candle validates that close_time matches timestamp + timeframe."""
    timestamp = datetime(2023, 1, 1, 9, 30)
    timeframe = "1M"
    # Wrong close_time (should be 9:31)
    wrong_close_time = datetime(2023, 1, 1, 9, 32)
    
    with pytest.raises(ValueError, match="close_time.*does not match"):
        Candle(
            symbol="TEST",
            timestamp=timestamp,
            close_time=wrong_close_time,
            timeframe=timeframe,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000
        )


def test_candle_from_row_invalid_timeframe():
    """Candle.from_row raises ValueError for invalid timeframe format."""
    row = {
        "datetime": "20230101 09:30",
        "open": "100.0",
        "high": "101.0",
        "low": "99.0",
        "close": "100.5",
        "volume": "1000"
    }
    
    with pytest.raises(ValueError, match="Invalid interval format"):
        Candle.from_row(row, "TEST", "INVALID")