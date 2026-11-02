"""Tests for TradeLog."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from quantrex.core.models.orders import OrderSide
from quantrex.core.models.trades import Trade
from quantrex.engine.base_engine.trade_log import TradeLog


def _make_trade() -> Trade:
    return Trade(
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=Decimal(1),
        entry_price=Decimal(100),
        exit_price=Decimal(101),
        entry_time=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        exit_time=datetime(2024, 1, 1, 10, 1, tzinfo=UTC),
        pnl=Decimal(1),
    )


class TestTradeLog:
    """Tests for TradeLog."""

    def test_write_appends_json_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "trades.jsonl"
            trade_log = TradeLog(log_path)
            trade = _make_trade()

            trade_log.write(trade)

            content = log_path.read_text(encoding="utf-8")
            record = json.loads(content.strip())
            assert record["symbol"] == "RELIANCE"
            assert record["side"] == "BUY"
            assert record["quantity"] == "1"
            assert record["entry_price"] == "100"
            assert record["exit_price"] == "101"
            assert record["pnl"] == "1"
