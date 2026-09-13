from quantrex_core import Strategy
from quantrex_core.models import Candle
from quantrex_core.logging import get_logger
from quantrex_core.models.enums import OrderSide
from quantrex_core.models.position import Position
from quantrex_core.strategy.timeframe import on_timeframe

from quantrex_backtest import BacktestEngine

from quantrex_data.providers.zerodha_provider import ZerodhaDataProvider
from quantrex_data.adapters.zerodha_adapter import ZerodhaDataAdapter



logger = get_logger(__name__)


class MCBStrategy(Strategy):
    """A breakout strategy."""

    def __init__(self):
        super().__init__()
        self.current_breakout_high = None
        self.current_breakout_low = None
        self.breakout_check_date = None

    @on_timeframe("30M")
    def on_half_hourly(self, candle: Candle):
        """Handle 30-minute candles."""
        if self.breakout_check_date is None or candle.timestamp.date() != self.breakout_check_date:
            self.breakout_check_date = candle.timestamp.date()
            self.current_breakout_high = candle.high
            self.current_breakout_low = candle.low

    def on_candle(self, candle: Candle):
        """Handle all candles."""
        position = self.ctx.get_position(candle.symbol)

        # Exit conditions
        if position.quantity > 0:  # long
            if (self.current_breakout_low is not None) and (candle.close < self.current_breakout_low):
                logger.info(f"Exiting long at breakout low: {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(
                    symbol=candle.symbol,
                    side=OrderSide.SELL,
                    quantity=position.quantity
                )
        elif position.quantity < 0:  # short
            if (self.current_breakout_high is not None) and (candle.close > self.current_breakout_high):
                logger.info(f"Exiting short at breakout high: {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(
                    symbol=candle.symbol,
                    side=OrderSide.BUY,
                    quantity=-position.quantity  # make positive
                )

        # Entry conditions (only if flat)
        if position.quantity == 0:
            if (self.current_breakout_high is not None) and (candle.close > self.current_breakout_high):
                logger.info(
                    f"Breakout high hit at {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(
                    symbol=candle.symbol,
                    side=OrderSide.BUY,
                    quantity=1.0
                )
            elif (self.current_breakout_low is not None) and (candle.close < self.current_breakout_low):
                logger.info(
                    f"Breakout low hit at {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(
                    symbol=candle.symbol,
                    side=OrderSide.SELL,
                    quantity=1.0
                )


if __name__ == "__main__":
    mcb_strategy = MCBStrategy()

    symbol = "TCS"
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
        strategy=mcb_strategy,
        symbol=symbol,
    )
    engine.run()
