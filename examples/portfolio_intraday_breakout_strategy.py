"""Portfolio Intraday Breakout Strategy Example.

This example demonstrates the new portfolio backtesting features:
- Multiple instruments via InstrumentSpec
- BacktestConfig for initial cash, margin, auto-download
- PortfolioContext via ctx.portfolio (cash, equity, margin, positions)
- ctx.positions for all open positions
- Unified BacktestEngine API for both single and portfolio backtests
"""

from datetime import time

from quantrex_core import Strategy
from quantrex_core.models import Candle
from quantrex_core.logging import get_logger
from quantrex_core.models.enums import OrderSide
from quantrex_core.strategy.timeframe import on_timeframe

from quantrex_backtest import BacktestEngine, InstrumentSpec, BacktestConfig

from quantrex_data.providers.zerodha_provider import ZerodhaDataProvider
from quantrex_data.adapters.zerodha_adapter import ZerodhaDataAdapter


logger = get_logger(__name__)


class PortfolioHourlyInsideBreakoutStrategy(Strategy):
    """Portfolio version of the hourly inside breakout strategy.

    Demonstrates portfolio-level features:
    - ctx.portfolio for cash, equity, margin, unrealized/realized P&L
    - ctx.positions for all open positions across instruments
    - ctx.get_position(symbol) for per-symbol position
    - ctx.submit_order(symbol, ...) for per-symbol orders
    """

    def __init__(self):
        super().__init__()
        self._mother_candle: dict[str, Candle | None] = {}
        self._inside_candle: dict[str, Candle | None] = {}
        self._entry_pre_setup_condition_met: dict[str, bool] = {}

    def reset_state(self, symbol: str):
        self._mother_candle[symbol] = None
        self._inside_candle[symbol] = None
        self._entry_pre_setup_condition_met[symbol] = False

    @on_timeframe("1H")
    def on_hour_candle(self, candle: Candle):
        symbol = candle.symbol
        prev_1h_candle = self.ctx.timeframe_history("1H")[-2] if len(self.ctx.timeframe_history("1H")) >= 2 else None
        logger.info(f"[{symbol}] Received 1H candle: {candle}")
        logger.info(f"[{symbol}] Previous 1H candle: {prev_1h_candle}")

        if prev_1h_candle is not None:
            if candle.high < prev_1h_candle.high and candle.low > prev_1h_candle.low:
                self._mother_candle[symbol] = prev_1h_candle
                self._inside_candle[symbol] = candle
                self._entry_pre_setup_condition_met[symbol] = True
                logger.info(f"[{symbol}] Mother candle detected: {self._mother_candle[symbol]}")
                logger.info(f"[{symbol}] Inside candle detected: {self._inside_candle[symbol]}")
            else:
                self.reset_state(symbol)

    def on_candle(self, candle: Candle):
        symbol = candle.symbol

        # Initialize state for new symbols
        if symbol not in self._entry_pre_setup_condition_met:
            self.reset_state(symbol)

        prev_candle = self.ctx.history[-2] if len(self.ctx.history) >= 2 else None
        if prev_candle is not None:
            if prev_candle.timestamp.date() != candle.timestamp.date():
                self.reset_state(symbol)

        # Portfolio-level logging (NEW FEATURE)
        portfolio = self.ctx.portfolio
        logger.info(
            f"[{symbol}] Portfolio: cash={portfolio.cash:.2f}, "
            f"equity={portfolio.equity:.2f}, "
            f"margin_used={portfolio.margin_used:.2f}, "
            f"margin_available={portfolio.margin_available:.2f}, "
            f"unrealized_pnl={portfolio.unrealized_pnl:.2f}, "
            f"realized_pnl={portfolio.realized_pnl:.2f}"
        )

        # All positions across portfolio (NEW FEATURE)
        all_positions = self.ctx.positions
        for sym, pos in all_positions.items():
            if pos.quantity != 0:
                logger.info(f"  Position [{sym}]: qty={pos.quantity}, entry={pos.entry_price:.2f}")

        position = self.ctx.get_position(symbol)

        # End-of-day exit logic
        if candle.timestamp.time() >= time(15, 15):
            if position.quantity > 0:  # long position
                logger.info(f"[{symbol}] Exiting long position at {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(symbol, OrderSide.SELL, position.quantity)
                self.reset_state(symbol)
            elif position.quantity < 0:  # short position
                logger.info(f"[{symbol}] Exiting short position at {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(symbol, OrderSide.BUY, abs(position.quantity))
                self.reset_state(symbol)

        # Breakout entry logic
        if self._entry_pre_setup_condition_met.get(symbol, False) and position.quantity == 0:
            inside_candle = self._inside_candle.get(symbol)
            if inside_candle is None:
                return

            if candle.close > inside_candle.high:
                self.ctx.submit_order(symbol, OrderSide.BUY, 8)
                logger.info(f"[{symbol}] Breakout BUY order placed at {candle.close} on {candle.timestamp}")
                self.reset_state(symbol)
            elif candle.close < inside_candle.low:
                self.ctx.submit_order(symbol, OrderSide.SELL, 8)
                logger.info(f"[{symbol}] Breakout SELL order placed at {candle.close} on {candle.timestamp}")
                self.reset_state(symbol)


if __name__ == "__main__":
    from quantrex_core.logging import setup_logging

    setup_logging(level="INFO")

    strategy = PortfolioHourlyInsideBreakoutStrategy()

    # Define multiple instruments for portfolio backtest (NEW FEATURE)
    instruments = [
        InstrumentSpec(
            symbol="RELIANCE",
            adapter=ZerodhaDataAdapter(
                ZerodhaDataProvider(
                    symbol="RELIANCE",
                    exchange_segment="NSE",
                )
            ),
        ),
        InstrumentSpec(
            symbol="TCS",
            adapter=ZerodhaDataAdapter(
                ZerodhaDataProvider(
                    symbol="TCS",
                    exchange_segment="NSE",
                )
            ),
        ),
        InstrumentSpec(
            symbol="INFY",
            adapter=ZerodhaDataAdapter(
                ZerodhaDataProvider(
                    symbol="INFY",
                    exchange_segment="NSE",
                )
            ),
        ),
    ]

    # Portfolio configuration (NEW FEATURE)
    # Backtest period is specified ONCE here in BacktestConfig
    config = BacktestConfig(
        initial_cash=1_000_000.0,      # Starting capital
        margin_requirement=1.0,         # 1.0 = no leverage, 2.0 = 2x leverage
        auto_download=True,             # Auto-download missing data
        data_start="2026-01-01",
        data_end="2026-01-31",
    )

    # Unified BacktestEngine API - works for both single and portfolio (NEW FEATURE)
    engine = BacktestEngine(
        instruments,
        strategy,
        config,
    )

    # Run portfolio backtest
    result = engine.run()
