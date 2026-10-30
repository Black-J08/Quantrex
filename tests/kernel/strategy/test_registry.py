"""Tests for StrategyRegistry."""

from __future__ import annotations

from quantrex.core.models.timeframe import Timeframe, TimeframeUnit

from quantrex.kernel.strategy.registry import StrategyRegistry


class TestStrategyRegistry:
    """Tests for StrategyRegistry."""

    def test_register_and_get_timeframe(self) -> None:
        registry = StrategyRegistry()
        tf = Timeframe(value=5, unit=TimeframeUnit.MINUTE)
        registry.register_timeframe("5m", tf)
        assert registry.get_timeframe("5m") is tf

    def test_get_unknown_timeframe_returns_none(self) -> None:
        registry = StrategyRegistry()
        assert registry.get_timeframe("nonexistent") is None

    def test_registered_names(self) -> None:
        registry = StrategyRegistry()
        registry.register_timeframe("1m", Timeframe(value=1, unit=TimeframeUnit.MINUTE))
        registry.register_timeframe("5m", Timeframe(value=5, unit=TimeframeUnit.MINUTE))
        names = registry.registered_names()
        assert "1m" in names
        assert "5m" in names
        assert len(names) == 2
