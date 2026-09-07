"""Regression tests for ``LiveStrategyContext.history`` placeholder.

The live engine itself is a ``NotImplementedError`` placeholder today.
This file pins down the contract for ``ctx.history`` on the live
context so the behaviour is documented and locked in: a fresh live
context returns an empty tuple, and that is the entire surface until
the live engine lands.

When ``LiveEngine`` becomes a real implementation, the
``test_live_context_history_placeholder`` test below should be replaced
(or supplemented) with a real-bufffer test that exercises pre-fill,
warmup, and per-bar append.
"""

from quantrex_live.core.context import LiveStrategyContext
from quantrex_core.position.manager import PositionManager


def test_live_context_history_placeholder():
    """``LiveStrategyContext.history`` returns an empty tuple.

    The live engine does not stream candles yet, so there is no buffer
    to draw from. Returning ``()`` (rather than a fake non-empty buffer)
    means any strategy that accidentally runs in a live context with
    the unimplemented engine will see ``len(ctx.history) == 0`` and
    take its warmup-guard branch instead of acting on fabricated data.
    """
    ctx = LiveStrategyContext(PositionManager())
    history = ctx.history

    # Must be a tuple (immutable) and empty.
    assert isinstance(history, tuple)
    assert history == ()
    assert len(history) == 0
