"""Regression tests for timeframe dispatch registry."""

from datetime import datetime, timedelta
from quantrex_core.models import Candle
from quantrex_core.strategy.base import Strategy
from quantrex_core.strategy.timeframe import TimeframeRegistry, TimeframeDispatcher, on_timeframe
from quantrex_core.strategy.context import StrategyContext


class MockStrategyContext(StrategyContext):
    """Mock StrategyContext for testing."""

    def __init__(self, candles: list[Candle]):
        self._history = candles

    def submit_order(self, symbol: str, side, quantity: float, order_type=None):
        raise NotImplementedError

    def get_position(self, symbol: str):
        raise NotImplementedError

    @property
    def history(self) -> tuple[Candle, ...]:
        return tuple(self._history)

    @property
    def current_time(self) -> datetime:
        # For testing, we return a fixed time; the tests don't rely on this value.
        return datetime.min

    def timeframe_history(self, interval: str) -> tuple[Candle, ...]:
        # Simple filtering for testing: group by hour
        if interval == "1H":
            result = []
            current_hour = None
            for candle in self._history:
                candle_hour = candle.timestamp.replace(minute=0, second=0, microsecond=0)
                if current_hour is None:
                    current_hour = candle_hour
                elif candle_hour != current_hour:
                    result.append(candle)
                    current_hour = candle_hour
            return tuple(result)
        return tuple(self._history)


class TestStrategy(Strategy):
    """Test strategy with timeframe methods."""

    def __init__(self):
        super().__init__()
        self.calls_1h = []
        self.calls_1d = []
        self.on_candle_calls = []

    @on_timeframe("1H")
    def on_1h_candle(self, candle: Candle) -> None:
        self.calls_1h.append(candle)

    @on_timeframe("1D")
    def on_daily_candle(self, candle: Candle) -> None:
        self.calls_1d.append(candle)

    def on_candle(self, candle: Candle) -> None:
        self.on_candle_calls.append(candle)
        # Engine manages dispatch automatically; never call manually.


def make_candle(timestamp: datetime, symbol: str = "TEST") -> Candle:
    """Create a test candle."""
    return Candle(
        symbol=symbol,
        timestamp=timestamp,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000.0,
    )


def test_on_timeframe_decorator_registers_methods():
    """Test that @on_timeframe decorator registers methods correctly."""
    strategy = TestStrategy()

    # Check registry has the methods
    registry = strategy.timeframe_registry
    assert "1H" in registry.intervals()
    assert "1D" in registry.intervals()
    assert len(registry.get_methods("1H")) == 1
    assert len(registry.get_methods("1D")) == 1


def test_timeframe_dispatcher_dispatches_correctly():
    """Test that TimeframeDispatcher calls registered methods with filtered candles."""
    # Create candles spanning multiple hours
    base_time = datetime(2024, 1, 1, 9, 0)
    candles = [
        make_candle(base_time + timedelta(minutes=i * 30)) for i in range(6)  # 3 hours of 30-min candles
    ]

    ctx = MockStrategyContext(candles)
    strategy = TestStrategy()
    strategy.set_context(ctx)

    # Engine manages dispatch automatically; dispatcher called directly in tests
    for candle in candles:
        strategy.on_candle(candle)
        strategy.timeframe_dispatcher.dispatch_all(ctx)

    # Should have received 1H candles (one per hour boundary)
    # With 30-min candles: 9:00, 9:30, 10:00, 10:30, 11:00, 11:30
    # 1H boundaries: 9:00-10:00 (last=9:30), 10:00-11:00 (last=10:30), 11:00-12:00 (last=11:30)
    # But our mock filters by hour change, so we get candles at hour transitions
    assert len(strategy.calls_1h) >= 1  # At least one 1H candle dispatched


def test_backwards_compatibility_on_candle_works():
    """Test that strategies with only on_candle still work."""
    class SimpleStrategy(Strategy):
        def __init__(self):
            super().__init__()
            self.candles = []

        def on_candle(self, candle: Candle) -> None:
            self.candles.append(candle)

    strategy = SimpleStrategy()
    candles = [make_candle(datetime(2024, 1, 1, 9, 0) + timedelta(minutes=i * 30)) for i in range(3)]

    ctx = MockStrategyContext(candles)
    strategy.set_context(ctx)

    for candle in candles:
        strategy.on_candle(candle)

    assert len(strategy.candles) == 3
    assert strategy.timeframe_registry.intervals() == []


def test_multiple_methods_same_timeframe():
    """Test that multiple methods can be registered for the same timeframe."""
    class MultiMethodStrategy(Strategy):
        def __init__(self):
            super().__init__()
            self.calls_a = []
            self.calls_b = []

        @on_timeframe("1H")
        def method_a(self, candle: Candle) -> None:
            self.calls_a.append(candle)

        @on_timeframe("1H")
        def method_b(self, candle: Candle) -> None:
            self.calls_b.append(candle)

        def on_candle(self, candle: Candle) -> None:
            # Engine manages dispatch automatically; never call manually.
            pass

    strategy = MultiMethodStrategy()
    candles = [make_candle(datetime(2024, 1, 1, 9, 0) + timedelta(minutes=i * 30)) for i in range(4)]

    ctx = MockStrategyContext(candles)
    strategy.set_context(ctx)

    for candle in candles:
        strategy.on_candle(candle)
        strategy.timeframe_dispatcher.dispatch_all(ctx)

    # Both methods should be called
    assert len(strategy.calls_a) >= 1
    assert len(strategy.calls_b) >= 1
    assert len(strategy.calls_a) == len(strategy.calls_b)


def test_timeframe_history_returns_tuple():
    """Test that timeframe_history returns immutable tuple."""
    candles = [make_candle(datetime(2024, 1, 1, 9, 0) + timedelta(minutes=i * 30)) for i in range(4)]
    ctx = MockStrategyContext(candles)

    tf_history = ctx.timeframe_history("1H")
    assert isinstance(tf_history, tuple)

    # Should not be able to mutate
    try:
        tf_history[0] = candles[0]  # type: ignore
        assert False, "Should have raised TypeError"
    except TypeError:
        pass


def test_strategy_without_timeframe_methods():
    """Test strategy with no @on_timeframe methods works normally."""
    class NoTimeframeStrategy(Strategy):
        def __init__(self):
            super().__init__()
            self.count = 0

        def on_candle(self, candle: Candle) -> None:
            self.count += 1

    strategy = NoTimeframeStrategy()
    assert strategy.timeframe_registry.intervals() == []
    assert strategy.timeframe_dispatcher._registry.intervals() == []