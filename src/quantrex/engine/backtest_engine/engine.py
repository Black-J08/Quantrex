"""BacktestEngine — mode-specific engine for backtesting.

Owns the kernel lifecycle, sources historical data via CandleReplay,
converts strategy signals to orders, simulates fills, and writes
trade fills to the trade log file.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.signals import Signal
from quantrex.core.models.trades import Trade
from quantrex.engine.base import BaseEngine
from quantrex.engine.signal_to_order import signal_to_order
from quantrex.engine.simulator import Simulator
from quantrex.engine.trade_log import TradeLog
from quantrex.kernel.kernel import Kernel


class BacktestEngine(BaseEngine):
    """Backtest engine.

    Creates and owns the kernel, feeds it historical candles from a
    CandleReplay iterator, handles signals by converting them to orders
    and simulating fills, and writes trade fills to the trade log file.
    """

    def __init__(self, trade_log_path: Path | str | None = None) -> None:
        self._pending_fills: list[Trade] = []
        self._simulator = Simulator(self)
        self._trade_log = TradeLog(trade_log_path) if trade_log_path is not None else None

    def create_kernel(self, strategy) -> Kernel:
        """Create a kernel wired to this engine's signal handler."""
        return Kernel(strategy, on_signal=self.on_signal)

    def data_iterator(self) -> Iterator[OHLCVCandle]:
        """Return an iterator of historical candles from the replay."""
        return iter(self._candles)

    def set_candles(self, candles: list[OHLCVCandle]) -> None:
        """Set the historical candles to replay.

        Args:
            candles: List of OHLCV candles sorted by timestamp.
        """
        self._candles = list(candles)

    def on_signal(self, signal: Signal) -> None:
        """Handle a signal emitted by the kernel.

        Converts the signal to an order, simulates execution, and writes
        any resulting fill to the trade log.
        """
        order = signal_to_order(signal)
        self._simulator.submit_order(order)

    def add_fill(self, trade: Trade) -> None:
        """Record a trade fill (internal use by the simulator)."""
        self._pending_fills.append(trade)
        if self._trade_log is not None:
            self._trade_log.write(trade)

    def get_pending_fills(self) -> list[Trade]:
        """Return and clear any pending trade fills."""
        fills = list(self._pending_fills)
        self._pending_fills.clear()
        return fills
