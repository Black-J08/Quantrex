"""Regression tests for timeframe dispatch registry."""

from datetime import datetime, timedelta
from quantrex_core.models import Candle
from quantrex_core.strategy.base import Strategy
from quantrex_core.strategy.timeframe import TimeframeRegistry, TimeframeDispatcher, on_timeframe
from quantrex_core.strategy.context import StrategyContext
from quantrex_core.timeframe.parser import interval_to_minutes


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


def make_candle(timestamp: datetime, symbol: str = "TEST", timeframe: str = "1M") -> Candle:
    """Create a test candle."""
    from datetime import timedelta
    close_time = timestamp + timedelta(minutes=1) if timeframe == "1M" else timestamp + timedelta(hours=1)
    return Candle(
        symbol=symbol,
        timestamp=timestamp,
        close_time=close_time,
        timeframe=timeframe,
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


def test_dispatch_all_orders_by_timeframe_hierarchy():
    """Test that dispatch_all dispatches intervals in duration order (smallest first)."""
    # Create a strategy with multiple timeframes registered in non-sorted order
    class OrderedDispatchStrategy(Strategy):
        def __init__(self):
            super().__init__()
            self.dispatch_order = []

        @on_timeframe("1D")
        def on_daily(self, candle: Candle) -> None:
            self.dispatch_order.append("1D")

        @on_timeframe("15M")
        def on_15m(self, candle: Candle) -> None:
            self.dispatch_order.append("15M")

        @on_timeframe("1H")
        def on_1h(self, candle: Candle) -> None:
            self.dispatch_order.append("1H")

        def on_candle(self, candle: Candle) -> None:
            pass

    strategy = OrderedDispatchStrategy()
    
    # Registry now maintains intervals sorted by duration (smallest first)
    registry_intervals = strategy.timeframe_registry.intervals()
    assert registry_intervals == ["15M", "1H", "1D"]  # Sorted by duration
    
    # dispatch_all should also dispatch in duration order
    # Create mock context with candles for all timeframes
    base_time = datetime(2024, 1, 1, 9, 0)
    candles = [make_candle(base_time + timedelta(minutes=i * 15)) for i in range(8)]  # 2 hours of 15M candles
    
    class MockCtx(StrategyContext):
        def __init__(self, candles):
            self._history = candles
        def submit_order(self, *a, **k): pass
        def get_position(self, *a, **k): pass
        @property
        def history(self): return tuple(self._history)
        @property
        def current_time(self): return datetime(2024, 1, 1, 12, 0)  # After all intervals close
        def timeframe_history(self, interval):
            # Return appropriate candles for each timeframe
            if interval == "15M":
                return tuple(self._history)  # All 15M candles
            elif interval == "1H":
                # Return last candle of each hour
                return tuple([self._history[3], self._history[7]])  # 9:45, 10:45
            elif interval == "1D":
                return tuple([self._history[-1]])  # Last candle
            return tuple(self._history)
    
    ctx = MockCtx(candles)
    strategy.set_context(ctx)
    
    # Call dispatch_all once
    strategy.timeframe_dispatcher.dispatch_all(ctx)
    
    # Verify dispatch order: first 15M dispatch happens before first 1H dispatch,
    # which happens before first 1D dispatch
    # Find first occurrence of each timeframe in dispatch order
    first_15m = strategy.dispatch_order.index("15M")
    first_1h = strategy.dispatch_order.index("1H")
    first_1d = strategy.dispatch_order.index("1D")
    
    assert first_15m < first_1h < first_1d, \
        f"Expected 15M before 1H before 1D, got order: {strategy.dispatch_order}"


def test_registry_rejects_non_multiple_timeframe():
    """Test that TimeframeRegistry.register validates higher timeframe is multiple of base."""
    registry = TimeframeRegistry()
    
    # Register base timeframe first (5M)
    registry.register("5M", lambda c: None)
    
    # Valid multiples should work
    registry.register("15M", lambda c: None)  # 3 * 5M
    registry.register("1H", lambda c: None)   # 12 * 5M
    registry.register("1D", lambda c: None)   # 288 * 5M
    
    # Non-multiple should raise ValueError
    try:
        registry.register("7M", lambda c: None)  # 7 is not a multiple of 5
        assert False, "Should have raised ValueError for non-multiple timeframe"
    except ValueError as e:
        assert "must be a multiple of base timeframe" in str(e)
    
    try:
        registry.register("13M", lambda c: None)  # 13 is not a multiple of 5
        assert False, "Should have raised ValueError for non-multiple timeframe"
    except ValueError as e:
        assert "must be a multiple of base timeframe" in str(e)