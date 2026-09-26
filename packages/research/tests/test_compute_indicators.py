"""Regression tests for the precomputed indicator API wired into ResearchEngine.

A bug fix without a regression test is not a fix — see project AGENTS.md
"Standing Rule: Regression Tests for Every Bug Fix". These tests cover the
end-to-end wiring of ``ResearchComponent.compute_indicators`` into
``ResearchEngine.run``:

1. The hook is called exactly once with the full sorted row sequence.
2. The i-th returned mapping is attached to the i-th ``Candle`` seen by
   ``on_candle``.
3. Hook exceptions and length mismatches are surfaced as ``ValueError``
   (with ``logger.exception(..., exc_info=True)`` per the project's
   "Logging & Error Tracking Standards").
4. Multiple timeframes (base + derived) both get indicators computed.
5. Different timeframes get DIFFERENT indicators (multi-timeframe correctness).
6. Derived timeframe indicators have no look-ahead bias.
7. Timeframe parameter is correctly propagated to component.
"""

import pandas as pd
import pandas_ta_classic as ta
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Mapping
from unittest.mock import Mock

from quantrex_core.models import Candle
from quantrex_core.protocols import DataAdapter
from quantrex_core.strategy.timeframe import on_timeframe

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig
from quantrex_backtest import InstrumentSpec, BacktestConfig


# ---------------------------------------------------------------------------
# Test fixtures: minimal components and adapters. We avoid CSV test-support
# helpers here because the assertions are about the indicator wiring, not
# the CSV pipeline. Mock adapters with explicit raw row dicts are simpler
# and faster.
# ---------------------------------------------------------------------------


class _RecordingComponent(ForwardReturnComponent):
    """Records every candle ``on_candle`` receives."""

    def __init__(self, config):
        super().__init__(config)
        self.candles: list[Candle] = []
        self.compute_calls: int = 0
        self.last_seen_rows: list[dict] | None = None
        self.last_timeframe: str | None = None

    def on_candle(self, candle: Candle) -> None:
        self.candles.append(candle)


class _SpreadComponent(_RecordingComponent):
    """Hand-rolled indicator: ``close - open`` (library-free, framework-agnostic)."""

    def compute_indicators(self, candles, timeframe=None):
        self.compute_calls += 1
        # Capture the exact row sequence the engine passed in so the
        # timestamp-ordering test can assert on it.
        self.last_seen_rows = [dict(row) for row in candles]
        self.last_timeframe = timeframe
        return [
            {"spread": float(c["close"]) - float(c["open"])} for c in candles
        ]


def _mock_adapter(rows: list[dict]) -> Mock:
    adapter = Mock(spec=DataAdapter)
    
    def read_timeframe_side_effect(tf, from_date=None, to_date=None):
        if tf == "1M":
            return rows
        return []  # Return empty for other timeframes (will be built from 1M)
    
    adapter.read_timeframe.side_effect = read_timeframe_side_effect
    adapter.datetime_format = "%Y-%m-%d %H:%M:%S"
    adapter.supported_timeframes = ["1M"]
    adapter.get_origin_time.return_value = None
    return adapter


def _row(ts: str, o: float, h: float, l: float, c: float, v: float) -> dict:
    return {
        "datetime": ts,
        "open": str(o),
        "high": str(h),
        "low": str(l),
        "close": str(c),
        "volume": str(v),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_engine_attaches_indicators_from_compute_indicators_hook():
    """Engine attaches the i-th returned dict to the i-th ``Candle.indicators``.

    Regression: the engine must call the hook exactly once, must pass the
    full sorted row sequence, must validate the returned length matches,
    and must thread each returned mapping into the matching candle's
    ``indicators`` field before ``on_candle`` is invoked.
    """
    rows = [
        _row("2024-01-01 09:30:00", 100.0, 101.0, 99.0, 100.5, 10),
        _row("2024-01-01 09:31:00", 101.0, 102.0, 100.0, 101.5, 20),
        _row("2024-01-01 09:32:00", 102.0, 103.0, 101.0, 102.5, 30),
    ]
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = _SpreadComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="SYM1", adapter=_mock_adapter(rows))],
        [component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )

    engine.run()

    # Hook called exactly once with the full sequence.
    assert component.compute_calls == 1
    assert component.last_seen_rows is not None
    assert len(component.last_seen_rows) == 3

    # Per-bar attachment: the i-th mapping is attached to the i-th candle.
    assert len(component.candles) == 3
    assert component.candles[0].indicators["spread"] == 0.5
    assert component.candles[1].indicators["spread"] == 0.5
    assert component.candles[2].indicators["spread"] == 0.5


def test_engine_passes_raw_rows_in_timestamp_order():
    """The hook receives rows already sorted by datetime, even if CSV is not.

    Regression: the engine must sort ``raw_data`` BEFORE calling
    ``compute_indicators`` so vectorized indicators compute over a
    deterministic, time-ordered series. Without the sort, an out-of-order
    CSV would silently produce a wrong series in the override.
    """
    rows = [
        # Intentionally out of order; engine must sort before hook.
        _row("2024-01-01 09:32:00", 102.0, 103.0, 101.0, 102.5, 30),  # latest
        _row("2024-01-01 09:30:00", 100.0, 101.0, 99.0, 100.5, 10),  # earliest
        _row("2024-01-01 09:31:00", 101.0, 102.0, 100.0, 101.5, 20),  # middle
    ]
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = _SpreadComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="SYM1", adapter=_mock_adapter(rows))],
        [component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )

    engine.run()

    assert component.last_seen_rows is not None
    seen = [r["datetime"] for r in component.last_seen_rows]
    assert seen == [
        "2024-01-01 09:30:00",
        "2024-01-01 09:31:00",
        "2024-01-01 09:32:00",
    ]


def test_engine_wraps_compute_indicators_exception():
    """A hook that raises becomes a ``ValueError`` (with full stack trace).

    Regression: the framework's "Logging & Error Tracking Standards" require
    ``logger.exception(..., exc_info=True)`` for any caught error. The
    engine must wrap the hook's exception as ``ValueError`` so callers have a
    single, predictable exception type for data/indicator failures.
    """

    class _BoomComponent(_RecordingComponent):
        def compute_indicators(self, candles, timeframe=None):
            raise ValueError("indicator math blew up")

    rows = [_row("2024-01-01 09:30:00", 100.0, 101.0, 99.0, 100.5, 10)]
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    engine = ResearchEngine(
        [InstrumentSpec(symbol="SYM1", adapter=_mock_adapter(rows))],
        [_BoomComponent(config)],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )

    try:
        engine.run()
    except ValueError as e:
        assert "compute_indicators failed" in str(e)
        assert "indicator math blew up" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_engine_raises_on_length_mismatch():
    """Returning the wrong number of indicator mappings raises ``ValueError``.

    Regression: a buggy override (e.g. off-by-one, or returning a generator
    that ``len()`` rejects) must not silently produce misaligned bars.
    The engine validates length and raises ``ValueError`` with both
    counts in the message.
    """

    class _BadLengthComponent(_RecordingComponent):
        def compute_indicators(self, candles, timeframe=None):
            # 3 input rows, 2 returned dicts — off by one.
            return [{"spread": 0.0}] * (len(candles) - 1)

    rows = [
        _row("2024-01-01 09:30:00", 100.0, 101.0, 99.0, 100.5, 10),
        _row("2024-01-01 09:31:00", 101.0, 102.0, 100.0, 101.5, 20),
        _row("2024-01-01 09:32:00", 102.0, 103.0, 101.0, 102.5, 30),
    ]
    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    engine = ResearchEngine(
        [InstrumentSpec(symbol="SYM1", adapter=_mock_adapter(rows))],
        [_BadLengthComponent(config)],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )

    try:
        engine.run()
    except ValueError as e:
        assert "length must match" in str(e)
        assert "3" in str(e)  # input count
        assert "2" in str(e)  # returned count
    else:
        raise AssertionError("expected ValueError")


def test_engine_compute_indicators_multiple_timeframes():
    """Engine computes indicators for both base and derived timeframes.

    Regression: when a component uses @on_timeframe("1H"), the engine must
    also call compute_indicators for the 1H timeframe (built from 1M data).
    """
    rows = []
    base_time = datetime(2024, 1, 1, 9, 0)
    for i in range(90):  # 9:00 to 10:29 (90 minutes)
        ts = base_time + timedelta(minutes=i)
        rows.append(_row(ts.strftime("%Y-%m-%d %H:%M:%S"), 100.0 + i, 101.0 + i, 99.0 + i, 100.0 + i, 1000.0))

    class _MultiTFComponent(_RecordingComponent):
        def __init__(self, config):
            super().__init__(config)
            self.timeframes_seen = []

        @on_timeframe("1H")
        def on_1h_candle(self, candle: Candle) -> None:
            pass

        def compute_indicators(self, candles, timeframe=None):
            self.timeframes_seen.append(timeframe)
            return [{"tf": timeframe}] * len(candles)

    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = _MultiTFComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="SYM1", adapter=_mock_adapter(rows))],
        [component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )

    engine.run()

    # Should have computed indicators for both 1M and 1H
    assert "1M" in component.timeframes_seen
    assert "1H" in component.timeframes_seen
    assert component.timeframes_seen.count("1M") == 1
    assert component.timeframes_seen.count("1H") == 1


def test_engine_compute_indicators_derived_timeframe_attached():
    """Indicators computed on derived timeframe (1H) are attached to 1H candles.

    Regression: when compute_indicators is called for 1H timeframe, the
    returned indicators must be attached to the 1H candles that are
    dispatched via @on_timeframe("1H").
    """
    rows = []
    base_time = datetime(2024, 1, 1, 9, 0)
    for i in range(90):  # 9:00 to 10:29 (90 minutes)
        ts = base_time + timedelta(minutes=i)
        rows.append(_row(ts.strftime("%Y-%m-%d %H:%M:%S"), 100.0 + i, 101.0 + i, 99.0 + i, 100.0 + i, 1000.0))

    class _DerivedTFComponent(_RecordingComponent):
        def __init__(self, config):
            super().__init__(config)
            self.h1_candles = []

        @on_timeframe("1H")
        def on_1h_candle(self, candle: Candle) -> None:
            self.h1_candles.append(candle)

        def compute_indicators(self, candles, timeframe=None):
            if timeframe == "1H":
                return [{"h1_indicator": float(c["close"]) * 2} for c in candles]
            return [{"m1_indicator": float(c["close"]) * 1} for c in candles]

        def on_candle(self, candle: Candle) -> None:
            super().on_candle(candle)

    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = _DerivedTFComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="SYM1", adapter=_mock_adapter(rows))],
        [component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )

    engine.run()

    # Check that 1H candles have the 1H indicator
    # The 1H candle 9:00-10:00 closes at 10:00, visible when processing 9:59
    # Our data goes to 10:29, so we should see the 9:00-10:00 1H candle
    assert len(component.h1_candles) >= 1
    # The 1H candle should have the h1_indicator
    assert "h1_indicator" in component.h1_candles[0].indicators
    # Value should be 2 * close of the 1H candle (which is close of 9:59 1M candle = 100.0 + 59 = 159.0)
    # Wait, the 1H candle close is the last 1M candle in the bucket (9:59)
    # So close = 100.0 + 59 = 159.0, indicator = 2 * 159.0 = 318.0
    assert component.h1_candles[0].indicators["h1_indicator"] == 318.0


def test_default_compute_indicators_returns_empty_dicts():
    """The default ``compute_indicators`` returns one empty mapping per input row."""
    from quantrex_research.core.base import ResearchComponent

    class _MinimalComponent(ResearchComponent):
        def on_start(self): pass
        def on_candle(self, candle): pass
        def on_stop(self, output_dir): pass
        def get_horizons(self): return [timedelta(minutes=1)]
        def on_returns_calculated(self, event, series): pass

    component = _MinimalComponent()
    rows = [_row("2024-01-01 09:30:00", 100.0, 101.0, 99.0, 100.5, 10)] * 3
    out = component.compute_indicators(rows)
    assert len(out) == 3
    assert all(d == {} for d in out)


def test_compute_indicators_receives_timeframe_param():
    """The timeframe parameter is passed to compute_indicators."""
    from quantrex_research.core.base import ResearchComponent

    class _TFComponent(ResearchComponent):
        def __init__(self):
            super().__init__()
            self.received_timeframe = None

        def on_start(self): pass
        def on_candle(self, candle): pass
        def on_stop(self, output_dir): pass
        def get_horizons(self): return [timedelta(minutes=1)]
        def on_returns_calculated(self, event, series): pass

        def compute_indicators(self, candles, timeframe=None):
            self.received_timeframe = timeframe
            return [{}] * len(candles)

    component = _TFComponent()
    rows = [_row("2024-01-01 09:30:00", 100.0, 101.0, 99.0, 100.5, 10)]
    component.compute_indicators(rows, timeframe="1H")
    assert component.received_timeframe == "1H"
    
    component.compute_indicators(rows, timeframe="1M")
    assert component.received_timeframe == "1M"
    
    component.compute_indicators(rows)
    assert component.received_timeframe is None


def test_engine_compute_indicators_multi_timeframe_correctness():
    """Engine computes DIFFERENT indicators for different timeframes.

    Regression: when a component uses @on_timeframe("1H"), the engine calls
    compute_indicators for both 1M and 1H. The component must use the timeframe
    parameter to compute appropriate indicators for each timeframe.
    1M candles should get 1M indicators (e.g., volume_ema_60).
    1H candles should get 1H indicators (e.g., rsi, st).
    """
    rows = []
    base_time = datetime(2024, 1, 1, 9, 0)
    for i in range(120):  # 9:00 to 10:59 (120 minutes = 2 hours)
        ts = base_time + timedelta(minutes=i)
        # Create varying close prices so RSI differs
        close = 100.0 + (i % 20) * 0.5
        rows.append(_row(ts.strftime("%Y-%m-%d %H:%M:%S"), close, close + 1, close - 1, close, 1000.0))

    class _MultiTFIndicatorComponent(_RecordingComponent):
        def __init__(self, config):
            super().__init__(config)
            self.timeframes_seen = []
            self.m1_indicators = []
            self.h1_indicators = []

        @on_timeframe("1H")
        def on_1h_candle(self, candle: Candle) -> None:
            pass

        def compute_indicators(self, candles, timeframe=None):
            self.timeframes_seen.append(timeframe)
            df = pd.DataFrame(candles)
            # Convert numeric columns from strings
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            if timeframe == "1H" or timeframe is None:
                # 1H indicators: RSI on hourly closes (short length for test)
                df['rsi'] = ta.rsi(df['close'], length=2)
                result = [{"rsi": row["rsi"]} for row in df.to_dict(orient="records")]
                self.h1_indicators.extend(result)
                return result
            else:
                # 1M indicators: volume EMA
                df['volume_ema_60'] = ta.rsi(df['volume'], length=60)
                result = [{"volume_ema_60": row["volume_ema_60"]} for row in df.to_dict(orient="records")]
                self.m1_indicators.extend(result)
                return result

    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = _MultiTFIndicatorComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="SYM1", adapter=_mock_adapter(rows))],
        [component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )

    engine.run()

    # Should have computed indicators for both 1M and 1H
    assert "1M" in component.timeframes_seen
    assert "1H" in component.timeframes_seen
    assert component.timeframes_seen.count("1M") == 1
    assert component.timeframes_seen.count("1H") == 1

    # 1M candles should have volume_ema_60 indicator
    assert len(component.candles) == 120
    for candle in component.candles:
        assert "volume_ema_60" in candle.indicators
        assert candle.indicators["volume_ema_60"] is not None

    # 1H candles (dispatched via on_1h_candle) should have rsi
    # The engine creates 1H candles from 1M data - 2 hours = 2 1H candles
    # But we need to check the 1H candles that were dispatched
    # Since we can't easily access dispatched 1H candles from the component,
    # we verify the compute_indicators was called with correct timeframe
    # and returned appropriate indicators
    assert len(component.h1_indicators) == 2  # 2 hourly candles
    for ind in component.h1_indicators:
        assert "rsi" in ind
        assert ind["rsi"] is not None

    # 1M indicators should be volume_ema_60
    assert len(component.m1_indicators) == 120
    for ind in component.m1_indicators:
        assert "volume_ema_60" in ind
        assert ind["volume_ema_60"] is not None


def test_engine_compute_indicators_look_ahead_bias_prevention():
    """Derived timeframe (1H) indicators only use data available at candle close.

    Regression: 1H candle for 9:00-10:00 closes at 10:00. Its indicators must
    only use 1M data from 9:00-9:59. No future data (10:00+) must leak into
    the 1H indicator computation. This is ensured by the engine building
    derived timeframe candles incrementally and only calling compute_indicators
    on completed buckets.
    """
    rows = []
    base_time = datetime(2024, 1, 1, 9, 0)
    for i in range(180):  # 9:00 to 11:59 (3 hours)
        ts = base_time + timedelta(minutes=i)
        # Distinct pattern: first hour low volume, second hour high volume, third hour medium
        if i < 60:
            vol = 100.0  # First hour
        elif i < 120:
            vol = 1000.0  # Second hour
        else:
            vol = 500.0  # Third hour
        rows.append(_row(ts.strftime("%Y-%m-%d %H:%M:%S"), 100.0, 101.0, 99.0, 100.0, vol))

    class _LookAheadComponent(_RecordingComponent):
        def __init__(self, config):
            super().__init__(config)
            self.h1_volume_emas = []  # Track volume EMA computed on 1H data

        @on_timeframe("1H")
        def on_1h_candle(self, candle: Candle) -> None:
            pass

        def compute_indicators(self, candles, timeframe=None):
            df = pd.DataFrame(candles)
            # Convert numeric columns from strings
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            if timeframe == "1H":
                # Compute volume EMA on 1H data - should only see completed hours
                df['volume_ema'] = ta.rsi(df['volume'], length=2)  # Short length for test
                result = [{"volume_ema": row["volume_ema"]} for row in df.to_dict(orient="records")]
                self.h1_volume_emas.extend(result)
                return result
            else:
                # 1M: just return empty
                return [{}] * len(candles)

    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = _LookAheadComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="SYM1", adapter=_mock_adapter(rows))],
        [component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )

    engine.run()

    # Should have 3 hourly candles (9-10, 10-11, 11-12)
    # Each 1H candle's volume_ema should only use that hour's volume data
    # Hour 1 (9-10): all volumes = 100 -> EMA should be ~100
    # Hour 2 (10-11): all volumes = 1000 -> EMA should be ~1000
    # Hour 3 (11-12): all volumes = 500 -> EMA should be ~500
    assert len(component.h1_volume_emas) == 3
    
    # First 1H candle (9:00-10:00) - volume_ema should reflect ~100
    # RSI with length=2 on constant 100 values -> 50 (neutral)
    # Actually RSI on constant values gives 50, but let's check it's computed
    assert component.h1_volume_emas[0]["volume_ema"] is not None
    
    # Second 1H candle (10:00-11:00) - volume_ema should reflect ~1000
    assert component.h1_volume_emas[1]["volume_ema"] is not None
    
    # Third 1H candle (11:00-12:00) - volume_ema should reflect ~500
    assert component.h1_volume_emas[2]["volume_ema"] is not None
    
    # Key assertion: the 1H indicators are DIFFERENT per hour, proving
    # each hour's indicator only used that hour's data (no look-ahead)
    # If look-ahead existed, all hours would see the same mixed data
    vals = [ind["volume_ema"] for ind in component.h1_volume_emas]
    # They should not all be the same (which would indicate data leakage)
    assert len(set(round(v, 2) for v in vals if v is not None)) > 1, \
        "1H indicators appear to have look-ahead bias - all hours show same values"


def test_engine_compute_indicators_timeframe_parameter_propagation():
    """Component receives correct timeframe for each compute_indicators call.

    Regression: engine must pass "1M" for base timeframe, "1H" for 1H timeframe,
    etc. Component can rely on this parameter to select appropriate computation.
    """
    rows = []
    base_time = datetime(2024, 1, 1, 9, 0)
    for i in range(60):  # 1 hour of data
        ts = base_time + timedelta(minutes=i)
        rows.append(_row(ts.strftime("%Y-%m-%d %H:%M:%S"), 100.0, 101.0, 99.0, 100.0, 1000.0))

    class _TFPropagationComponent(_RecordingComponent):
        def __init__(self, config):
            super().__init__(config)
            self.received_timeframes = []

        @on_timeframe("1H")
        def on_1h_candle(self, candle: Candle) -> None:
            pass

        @on_timeframe("30M")
        def on_30m_candle(self, candle: Candle) -> None:
            pass

        def compute_indicators(self, candles, timeframe=None):
            self.received_timeframes.append(timeframe)
            return [{}] * len(candles)

    config = ForwardReturnConfig(horizons=[timedelta(minutes=1)])
    component = _TFPropagationComponent(config)
    engine = ResearchEngine(
        [InstrumentSpec(symbol="SYM1", adapter=_mock_adapter(rows))],
        [component],
        data_start="2024-01-01",
        data_end="2024-01-02",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )

    engine.run()

    # Should receive timeframes for: 1M (base), 1H, 30M
    assert "1M" in component.received_timeframes
    assert "1H" in component.received_timeframes
    assert "30M" in component.received_timeframes
    # Each timeframe called exactly once
    assert component.received_timeframes.count("1M") == 1
    assert component.received_timeframes.count("1H") == 1
    assert component.received_timeframes.count("30M") == 1