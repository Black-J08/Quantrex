"""Result export for Quantrex Backtest."""

import csv
from pathlib import Path
from typing import List, Any

from quantrex_core.logging import get_logger
from quantrex_core.models.trade import TradeRecord

logger = get_logger(__name__)


class ResultExporter:
    """Exports backtest results to CSV files."""

    def export_trades_csv(self, trades: List[TradeRecord], output_dir: Path) -> None:
        """Export closed trades to CSV inside ``output_dir``."""
        output_file = output_dir / "closed_trades.csv"

        # Write CSV with headers (even if empty)
        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "symbol", "side", "quantity",
                "entry_timestamp", "entry_price",
                "exit_timestamp", "exit_price",
                "pnl"
            ])
            for trade in trades:
                writer.writerow([
                    trade.symbol,
                    trade.side.value,
                    trade.quantity,
                    trade.entry_timestamp.isoformat(),
                    trade.entry_price,
                    trade.exit_timestamp.isoformat(),
                    trade.exit_price,
                    trade.pnl,
                ])

        logger.info("Exported %d closed trades to %s", len(trades), output_file)

    def export_aggregated_trades_csv(self, trades: List[TradeRecord], output_dir: Path) -> None:
        """Write aggregated trades from all instruments to a single CSV."""
        output_file = output_dir / "closed_trades.csv"

        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "symbol", "side", "quantity",
                "entry_timestamp", "entry_price",
                "exit_timestamp", "exit_price",
                "pnl"
            ])
            for trade in trades:
                writer.writerow([
                    trade.symbol,
                    trade.side.value,
                    trade.quantity,
                    trade.entry_timestamp.isoformat(),
                    trade.entry_price,
                    trade.exit_timestamp.isoformat(),
                    trade.exit_price,
                    trade.pnl,
                ])

        logger.info("Exported %d aggregated closed trades to %s", len(trades), output_file)