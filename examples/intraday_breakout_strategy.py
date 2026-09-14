"""Intraday Breakout Strategy - Mother Candle / Inside Candle on 1H, entry on 1M breakout."""

from datetime import time

from quantrex_core import Strategy
from quantrex_core.logging import get_logger
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.models.position import Position
from quantrex_core.strategy.timeframe import on_timeframe

from quantrex_backtest import BacktestEngine

from quantrex_data.providers.zerodha_provider import ZerodhaDataProvider
from quantrex_data.adapters.zerodha_adapter import ZerodhaDataAdapter


logger = get_logger(__name__)

# Market hours for Indian exchanges (IST)
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 15)  # Exit all positions at 3:15 PM


class IntradayBreakoutStrategy(Strategy):
    """Intraday breakout strategy using mother/inside candle pattern on 1H timeframe.

    Logic:
    - On 1H timeframe: Identify mother candle (large body) followed by inside candle
      (completely within mother candle's range)
    - On 1M timeframe: Enter on breakout of inside candle's high/low
    - Exit all positions at 3:15 PM
    """

    def __init__(self) -> None:
        super().__init__()
        # 1H timeframe state
        self._prev_1h_candle: Candle | None = None
        self._mother_candle: Candle | None = None
        self._inside_candle: Candle | None = None
        self._setup_ready: bool = False

        # 1M timeframe state
        self._entry_triggered: bool = False

    @on_timeframe("1H")
    def on_1h_candle(self, candle: Candle) -> None:
        """Process 1-hour candles to detect mother/inside candle pattern."""
        # Skip if we already have a valid setup for the day
        if self._setup_ready:
            return

        # Need at least 2 candles to form the pattern
        if self._prev_1h_candle is None:
            self._prev_1h_candle = candle
            return

        # Check if previous candle is a "mother candle" (large body)
        prev_body = abs(self._prev_1h_candle.close - self._prev_1h_candle.open)
        prev_range = self._prev_1h_candle.high - self._prev_1h_candle.low
        body_ratio = prev_body / prev_range if prev_range > 0 else 0

        # Mother candle: body > 50% of range (strong directional candle)
        is_mother = body_ratio > 0.5

        # Check if current candle is an "inside candle" (completely within mother's range)
        is_inside = (
            candle.high <= self._prev_1h_candle.high
            and candle.low >= self._prev_1h_candle.low
        )

        if is_mother and is_inside:
            self._mother_candle = self._prev_1h_candle
            self._inside_candle = candle
            self._setup_ready = True
            logger.info(
                "[%s] Mother/Inside pattern detected: Mother O=%.2f H=%.2f L=%.2f C=%.2f, "
                "Inside O=%.2f H=%.2f L=%.2f C=%.2f",
                candle.timestamp,
                self._mother_candle.open,
                self._mother_candle.high,
                self._mother_candle.low,
                self._mother_candle.close,
                self._inside_candle.open,
                self._inside_candle.high,
                self._inside_candle.low,
                self._inside_candle.close,
            )

        # Update previous candle for next iteration
        self._prev_1h_candle = candle

    def on_candle(self, candle: Candle) -> None:
        """Process 1-minute candles for entry and exit logic."""
        current_time = candle.timestamp.time()
        position = self.ctx.get_position(candle.symbol)

        # Exit all positions at 3:15 PM
        if current_time >= MARKET_CLOSE:
            if position.quantity != 0:
                self._exit_position(candle, position)
            # Reset daily state after market close
            self._reset_daily_state()
            return

        # Only trade during market hours
        if current_time < MARKET_OPEN:
            return

        # Check for entry on inside candle breakout (only if flat and setup ready)
        if position.quantity == 0 and self._setup_ready and not self._entry_triggered:
            self._check_entry(candle)

    def _check_entry(self, candle: Candle) -> None:
        """Check for breakout entry on 1-minute candles."""
        if self._inside_candle is None:
            return

        # Long entry: price breaks above inside candle high
        if candle.close > self._inside_candle.high:
            logger.info(
                "[%s] Long entry: 1M close %.2f > inside high %.2f",
                candle.timestamp,
                candle.close,
                self._inside_candle.high,
            )
            self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.BUY,
                quantity=1.0,
            )
            self._entry_triggered = True

        # Short entry: price breaks below inside candle low
        elif candle.close < self._inside_candle.low:
            logger.info(
                "[%s] Short entry: 1M close %.2f < inside low %.2f",
                candle.timestamp,
                candle.close,
                self._inside_candle.low,
            )
            self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.SELL,
                quantity=1.0,
            )
            self._entry_triggered = True

    def _exit_position(self, candle: Candle, position: Position) -> None:
        """Exit position at market close."""
        if position.quantity > 0:  # Long position
            logger.info(
                "[%s] Exiting long at market close: %.2f",
                candle.timestamp,
                candle.close,
            )
            self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.SELL,
                quantity=position.quantity,
            )
        elif position.quantity < 0:  # Short position
            logger.info(
                "[%s] Exiting short at market close: %.2f",
                candle.timestamp,
                candle.close,
            )
            self.ctx.submit_order(
                symbol=candle.symbol,
                side=OrderSide.BUY,
                quantity=-position.quantity,  # make positive
            )

    def _reset_daily_state(self) -> None:
        """Reset state for next trading day."""
        self._prev_1h_candle = None
        self._mother_candle = None
        self._inside_candle = None
        self._setup_ready = False
        self._entry_triggered = False

    def on_start(self) -> None:
        """Initialize strategy state."""
        self._reset_daily_state()
        logger.info("IntradayBreakoutStrategy started")

    def on_stop(self) -> None:
        """Cleanup on strategy stop."""
        logger.info("IntradayBreakoutStrategy stopped")


if __name__ == "__main__":
    from quantrex_core.logging import setup_logging
    setup_logging(level="INFO")

    symbol = "TCS"
    provider = ZerodhaDataProvider(
        symbol=symbol,
        exchange_segment="NSE",
        from_date="2026-01-01",
        to_date="2026-01-30",
    )
    adapter = ZerodhaDataAdapter(provider)

    strategy = IntradayBreakoutStrategy()
    engine = BacktestEngine(
        adapter=adapter,
        strategy=strategy,
        symbol=symbol,
    )
    engine.run()