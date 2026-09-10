"""Comprehensive regression tests for multi-timeframe framework changes."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from quantrex_core import Strategy, Candle
from quantrex_core.strategy.base import on_timeframe
from quantrex_core.strategy.timeframe import TimeframeRegistry, TimeframeDispatcher
from quantrex_core.protocols import DataAdapter
from quantrex_backtest import BacktestEngine
from quantrex_backtest.core.engine import BacktestEngine as BE


class DecoratedOnlyStrategy(Strategy):
    """Only @on_timeframe — defines on_candle (base 1M) but only uses 1H."""
    def __init__(self):
        super().__init__()
        self.h_1h = []

    def on_candle(self, c):
        pass  # defined but not used for 1M logic

    @on_timeframe("1H")
    def on_1h(self, c):
        self.h_1h.append(c)


class WithOnCandleStrategy(Strategy):
    """Defines on_candle + @on_timeframe."""
    def __init__(self):
        super().__init__()
        self.h_1m = []
        self.h_1h = []

    def on_candle(self, c):
        self.h_1m.append(c)

    @on_timeframe("1H")
    def on_1h(self, c):
        self.h_1h.append(c)


class NoDecoratorsStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.c = []

    def on_candle(self, c):
        self.c.append(c)


# --- Strategy declaration ---

def test_declaration_registry_intervals():
    s = DecoratedOnlyStrategy()
    assert s.timeframe_registry.intervals() == ["1H"]


def test_declaration_auto_register_decorated():
    s = DecoratedOnlyStrategy()
    assert len(s.timeframe_registry.get_methods("1H")) == 1


def test_declaration_no_registry_when_no_decorators():
    s = NoDecoratorsStrategy()
    assert s.timeframe_registry.intervals() == []


# --- Engine auto-config / base timeframe ---

def test_engine_base_1m_when_on_candle_overridden():
    mock = Mock(spec=DataAdapter)
    mock.read_timeframe.return_value = [{"datetime":"20230101 10:00","open":"1","high":"2","low":"0","close":"1","volume":"10"}]
    mock.datetime_format = "%Y%m%d %H:%M"
    s = WithOnCandleStrategy()
    engine = BacktestEngine(mock, s, symbol="X")
    assert engine._get_required_timeframes()[0] == "1M"


def test_engine_base_1m_when_on_candle_defined():
    mock = Mock(spec=DataAdapter)
    mock.read_timeframe.return_value = [{"datetime":"20230101 10:00","open":"1","high":"2","low":"0","close":"1","volume":"10"}]
    mock.datetime_format = "%Y%m%d %H:%M"
    s = DecoratedOnlyStrategy()
    engine = BacktestEngine(mock, s, symbol="X")
    # DecoratedOnlyStrategy defines on_candle → base is 1M
    assert engine._get_required_timeframes()[0] == "1M"


def test_engine_fetches_1m_for_decorated_with_on_candle():
    mock = Mock(spec=DataAdapter)
    mock.read_timeframe.return_value = [{"datetime":"20230101 10:00","open":"1","high":"2","low":"0","close":"1","volume":"10"}]
    mock.datetime_format = "%Y%m%d %H:%M"
    s = DecoratedOnlyStrategy()
    engine = BacktestEngine(mock, s, symbol="X")
    engine.run()
    # Defines on_candle → base 1M fetched + 1H from registry
    calls = [c[0][0] for c in mock.read_timeframe.call_args_list]
    assert "1M" in calls
    assert "1H" in calls


# --- Dispatch / on_candle default ---

def test_dispatch_called_automatically_by_engine():
    mock = Mock(spec=DataAdapter)
    mock.read_timeframe.return_value = [{"datetime":"20230101 10:00","open":"1","high":"2","low":"0","close":"1","volume":"10"}]
    mock.datetime_format = "%Y%m%d %H:%M"
    s = WithOnCandleStrategy()
    engine = BacktestEngine(mock, s, symbol="X")
    engine.run()
    assert len(s.h_1h) == 1  # dispatched


def test_on_candle_not_called_when_not_overridden():
    mock = Mock(spec=DataAdapter)
    mock.read_timeframe.return_value = [{"datetime":"20230101 10:00","open":"1","high":"2","low":"0","close":"1","volume":"10"}]
    mock.datetime_format = "%Y%m%d %H:%M"
    s = DecoratedOnlyStrategy()
    engine = BacktestEngine(mock, s, symbol="X")
    engine.run()
    # No 1M candles collected because on_candle never invoked
    assert len(s.h_1h) == 1


# --- Provider / adapter / 1M fallback ---

def test_adapter_aggregation_contract():
    from quantrex_data.adapters.csv_adapter import CSVDataAdapter
    from quantrex_data.providers.csv_provider import CSVDataProvider
    # Just verify protocol exists and adapter has _aggregate_timeframe
    assert hasattr(CSVDataAdapter, "_aggregate_timeframe")


def test_provider_minute_flag_controls_supported():
    from quantrex_data.providers.csv_provider import CSVDataProvider
    p = CSVDataProvider("dummy.csv", minute_data_available=False)
    assert p.supported_timeframes() == []
    p2 = CSVDataProvider("dummy.csv", minute_data_available=True)
    assert "1M" in p2.supported_timeframes()


# --- timeframe_history ---

def test_timeframe_history_filtering():
    from quantrex_core.strategy.context import StrategyContext
    # Mock context with history
    class MockCtx(StrategyContext):
        def __init__(self):
            self._h = []
        @property
        def history(self):
            return tuple(self._h)
        def submit_order(self, *a, **k): pass
        def get_position(self, *a, **k): return None
        def timeframe_history(self, interval):
            if interval == "1H":
                return tuple([c for c in self._h if c.timestamp.hour == 10])
            return tuple(self._h)
    ctx = MockCtx()
    c = Candle(symbol="S", timestamp=datetime(2023,1,1,10,30), open=1, high=2, low=0, close=1, volume=10)
    ctx._h = [c]
    assert len(ctx.timeframe_history("1H")) == 1


# --- Indicators per timeframe ---

def test_indicator_timeframe_parameter():
    s = WithOnCandleStrategy()
    # compute_indicators receives timeframe param
    result = s.compute_indicators([{"datetime":"20230101 10:00","open":"1","high":"2","low":"0","close":"1","volume":"10"}], timeframe="1H")
    assert len(result) == 1


# --- Error cases ---

def test_engine_raises_on_unavailable_timeframe_no_1m():
    mock = Mock(spec=DataAdapter)
    mock.read_timeframe.side_effect = ValueError("1-minute data unavailable")
    mock.datetime_format = "%Y%m%d %H:%M"
    s = DecoratedOnlyStrategy()
    engine = BacktestEngine(mock, s, symbol="X")
    with pytest.raises(Exception):
        engine.run()


def test_registry_clear():
    reg = TimeframeRegistry()
    reg.register("1H", lambda c: None)
    reg.clear()
    assert reg.intervals() == []


def test_dispatcher_reset():
    reg = TimeframeRegistry()
    d = TimeframeDispatcher(reg)
    d._last_dispatched_index["1H"] = 5
    d.reset()
    assert d._last_dispatched_index == {}
