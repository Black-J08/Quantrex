"""Tests for the StrategyContext ABC.

Regression coverage for converting ``StrategyContext`` from a structural
``typing.Protocol`` to a real ``abc.ABC``. The Protocol could be
instantiated and silently dropped unimplemented methods; the ABC refuses
to construct abstract subclasses, which is the safety property we want.
"""

from datetime import datetime

import pytest

from quantrex_core import StrategyContext
from quantrex_core.models.enums import OrderSide, OrderType
from quantrex_core.order import OrderManagementSystem
from quantrex_core.position.manager import PositionManager
from quantrex_backtest.core.context import BacktestStrategyContext
from quantrex_live.core.context import LiveStrategyContext


def test_strategy_context_cannot_be_instantiated_directly():
    """``StrategyContext()`` must raise ``TypeError`` because it is an ABC.

    Under the previous ``typing.Protocol`` definition, this call succeeded
    and silently produced an object with no behavior.
    """
    with pytest.raises(TypeError):
        StrategyContext()


def test_subclass_missing_submit_order_cannot_be_instantiated():
    """A subclass that omits ``submit_order`` must refuse to instantiate."""

    class IncompleteContext(StrategyContext):
        def get_position(self, symbol: str):  # type: ignore[override]
            raise NotImplementedError

    with pytest.raises(TypeError):
        IncompleteContext()


def test_subclass_missing_get_position_cannot_be_instantiated():
    """A subclass that omits ``get_position`` must refuse to instantiate."""

    class IncompleteContext(StrategyContext):
        def submit_order(  # type: ignore[override]
            self, symbol: str, side: OrderSide, quantity: float,
            order_type: OrderType = OrderType.MARKET,
        ):
            raise NotImplementedError

    with pytest.raises(TypeError):
        IncompleteContext()


def test_backtest_strategy_context_is_a_strategy_context():
    """``BacktestStrategyContext`` is a real subclass of ``StrategyContext``."""
    pm = PositionManager()
    oms = OrderManagementSystem()
    ctx = BacktestStrategyContext(pm, oms, current_time=datetime.min)
    assert isinstance(ctx, StrategyContext)


def test_live_strategy_context_is_a_strategy_context():
    """``LiveStrategyContext`` is a real subclass of ``StrategyContext``."""
    pm = PositionManager()
    ctx = LiveStrategyContext(pm)
    assert isinstance(ctx, StrategyContext)
