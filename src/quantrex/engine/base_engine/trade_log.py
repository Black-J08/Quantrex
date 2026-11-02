"""File-based trade log writer shared by backtest and research engines.

Appends trade fill records as JSON lines to a log file.
"""

from __future__ import annotations

import json
from pathlib import Path

from quantrex.core.models.trades import Trade


class TradeLog:
    """Appends trade fills to a file as JSON lines."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def write(self, trade: Trade) -> None:
        """Append a trade fill to the log file.

        Args:
            trade: The trade fill to record.
        """
        record = {
            "symbol": trade.symbol,
            "side": trade.side.value,
            "quantity": str(trade.quantity),
            "entry_price": str(trade.entry_price),
            "exit_price": str(trade.exit_price),
            "entry_time": trade.entry_time.isoformat(),
            "exit_time": trade.exit_time.isoformat(),
            "pnl": str(trade.pnl),
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
