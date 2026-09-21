from quantrex_core import Strategy
from quantrex_core.models import Candle
from quantrex_core.logging import get_logger
from quantrex_core.models.enums import OrderSide
from quantrex_core.models.position import Position
from quantrex_core.strategy.timeframe import on_timeframe

from quantrex_backtest import BacktestEngine, InstrumentSpec, PortfolioConfig

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
        # Track position state for 30-minute candle based exit logic
        self.entry_date = None
        self.consecutive_red_30m = 0
        self.consecutive_green_30m = 0

    @on_timeframe("30M")
    def on_half_hourly(self, candle: Candle):
        """Handle 30-minute candles."""
        if self.breakout_check_date is None or candle.timestamp.date() != self.breakout_check_date:
            self.breakout_check_date = candle.timestamp.date()
            self.current_breakout_high = candle.high
            self.current_breakout_low = candle.low
            # Reset consecutive counters at start of each new day
            self.consecutive_red_30m = 0
            self.consecutive_green_30m = 0

        # Update consecutive counters based on 30-minute candle color
        is_red = candle.close < candle.open
        is_green = candle.close >= candle.open
        
        position = self.ctx.get_position(candle.symbol)
        
        if position.quantity > 0:  # long position
            if is_red:
                self.consecutive_red_30m += 1
                self.consecutive_green_30m = 0  # reset green counter
            else:
                self.consecutive_red_30m = 0  # reset red counter
                self.consecutive_green_30m += 1
        elif position.quantity < 0:  # short position
            if is_green:
                self.consecutive_green_30m += 1
                self.consecutive_red_30m = 0  # reset red counter
            else:
                self.consecutive_green_30m = 0  # reset green counter
                self.consecutive_red_30m += 1
                
        position = self.ctx.get_position(candle.symbol)
        current_date = candle.timestamp.date()

        # Reset consecutive counters at start of each new day (handles case where on_candle fires before first 30M candle of new day)
        if hasattr(self, '_last_candle_date') and current_date != self._last_candle_date:
            self.consecutive_red_30m = 0
            self.consecutive_green_30m = 0
        self._last_candle_date = current_date

        # Exit conditions based on 30-minute candle consecutive counts
        if position.quantity > 0:  # long
            # Exit long after 2 consecutive red 30-minute candles (not same day as entry)
            if (self.consecutive_red_30m >= 2 and 
                self.entry_date is not None and 
                current_date != self.entry_date):
                logger.info(f"Exiting long after 2 consecutive red 30-minute candles: {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(
                    symbol=candle.symbol,
                    side=OrderSide.SELL,
                    quantity=position.quantity
                )
                # Reset after exit
                self.entry_date = None
                self.consecutive_red_30m = 0
                self.consecutive_green_30m = 0
        elif position.quantity < 0:  # short
            # Exit short after 2 consecutive green 30-minute candles (not same day as entry)
            if (self.consecutive_green_30m >= 2 and 
                self.entry_date is not None and 
                current_date != self.entry_date):
                logger.info(f"Exiting short after 2 consecutive green 30-minute candles: {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(
                    symbol=candle.symbol,
                    side=OrderSide.BUY,
                    quantity=-position.quantity  # make positive
                )
                # Reset after exit
                self.entry_date = None
                self.consecutive_red_30m = 0
                self.consecutive_green_30m = 0


    def on_candle(self, candle: Candle):
        """Handle all candles."""
        position = self.ctx.get_position(candle.symbol)
        current_date = candle.timestamp.date()

        # Entry conditions (only if flat)
        if position.quantity == 0:
            if (self.current_breakout_high is not None) and (candle.close > self.current_breakout_high):
                logger.info(
                    f"Breakout high hit at {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(
                    symbol=candle.symbol,
                    side=OrderSide.BUY,
                    quantity=10.0
                )
                self.entry_date = current_date
                # Reset counters on new entry
                self.consecutive_red_30m = 0
                self.consecutive_green_30m = 0
            elif (self.current_breakout_low is not None) and (candle.close < self.current_breakout_low):
                logger.info(
                    f"Breakout low hit at {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(
                    symbol=candle.symbol,
                    side=OrderSide.SELL,
                    quantity=10.0
                )
                self.entry_date = current_date
                # Reset counters on new entry
                self.consecutive_red_30m = 0
                self.consecutive_green_30m = 0


if __name__ == "__main__":
    from quantrex_core.logging import setup_logging

    setup_logging(level="INFO")

    mcb_strategy = MCBStrategy()

    symbol = "RELIANCE"
    provider = ZerodhaDataProvider(
        symbol=symbol,
        exchange_segment="NSE",
        # instrument="EQUITY",
    )
    adapter = ZerodhaDataAdapter(provider)

    instruments = [
        InstrumentSpec(symbol=symbol, adapter=adapter),
    ]
    # Backtest period is specified ONCE in PortfolioConfig
    config = PortfolioConfig(
        initial_cash=1_000_000.0,
        data_start="2025-07-01",
        data_end="2026-06-30",
    )

    engine = BacktestEngine(
        instruments=instruments,
        strategy=mcb_strategy,
        config=config,
    )
    engine.run()
