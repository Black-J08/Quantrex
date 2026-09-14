from datetime import time

from quantrex_core import Strategy
from quantrex_core.models import Candle
from quantrex_core.logging import get_logger
from quantrex_core.models.enums import OrderSide
from quantrex_core.strategy.timeframe import on_timeframe

from quantrex_backtest import BacktestEngine

from quantrex_data.providers.zerodha_provider import ZerodhaDataProvider
from quantrex_data.adapters.zerodha_adapter import ZerodhaDataAdapter


logger = get_logger(__name__)


class HourlyInsideBreakoutStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self._mother_candle: Candle | None = None
        self._inside_candle: Candle | None = None
        self._entry_pre_setup_condition_met = False

    def reset_state(self):
        self._mother_candle = None
        self._inside_candle = None
        self._entry_pre_setup_condition_met = False

    @on_timeframe("1H")
    def on_hour_candle(self, candle: Candle):
        prev_1h_candle = self.ctx.timeframe_history(
            "1H")[-2] if len(self.ctx.timeframe_history("1H")) >= 2 else None

        if prev_1h_candle is not None:
            if candle.high < prev_1h_candle.high and candle.low > prev_1h_candle.low:
                self._mother_candle = prev_1h_candle
                self._inside_candle = candle
                self._entry_pre_setup_condition_met = True
                logger.info(f"Mother candle detected: {self._mother_candle}")
                logger.info(f"Inside candle detected: {self._inside_candle}")
            else:
                self.reset_state()

    def on_candle(self, candle: Candle):
        prev_candle = self.ctx.history[-2] if len(
            self.ctx.history) >= 2 else None
        if prev_candle is not None:
            if (prev_candle.timestamp.date() != candle.timestamp.date()):
                self.reset_state()

        position = self.ctx.get_position(candle.symbol)

        if (candle.timestamp.time() >= time(15, 15)):
            if position.quantity > 0:  # long position
                logger.info(
                    f"Exiting long position at {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(
                    candle.symbol, OrderSide.SELL, position.quantity)
                self.reset_state()
            elif position.quantity < 0:  # short position
                logger.info(
                    f"Exiting short position at {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(
                    candle.symbol, OrderSide.BUY, abs(position.quantity))
                self.reset_state()

        if self._entry_pre_setup_condition_met and position.quantity == 0:
            if candle.close > self._inside_candle.high:
                self.ctx.submit_order(candle.symbol, OrderSide.BUY, 8)
                logger.info(
                    f"Breakout BUY order placed at {candle.close} on {candle.timestamp}")
                self.reset_state()
            elif candle.close < self._inside_candle.low:
                self.ctx.submit_order(candle.symbol, OrderSide.SELL, 8)
                logger.info(
                    f"Breakout SELL order placed at {candle.close} on {candle.timestamp}")
                self.reset_state()


if __name__ == "__main__":
    strategy = HourlyInsideBreakoutStrategy()

    symbol = "RELIANCE"
    provider = ZerodhaDataProvider(
        symbol=symbol,
        exchange_segment="NSE",
        # instrument="EQUITY",
        from_date="2026-01-01",
        to_date="2026-01-30",
    )
    adapter = ZerodhaDataAdapter(provider)

    engine = BacktestEngine(
        adapter=adapter,
        strategy=strategy,
        symbol=symbol,
    )
    engine.run()
