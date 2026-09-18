"""Multi-timeframe RSI strategy demonstrating all implemented multi-timeframe features."""

from quantrex_core import Strategy
from quantrex_core.logging import get_logger
from quantrex_core.models.enums import OrderSide
from quantrex_core.strategy.base import on_timeframe
from quantrex_data.providers.dhan_provider import DhanDataProvider
from quantrex_data.adapters.dhan_adapter import DhanDataAdapter
from quantrex_backtest import BacktestEngine, InstrumentSpec, PortfolioConfig

import pandas as pd
import pandas_ta_classic as ta


logger = get_logger(__name__)


class MultiTimeframeRsiStrategy(Strategy):
    """RSI strategy with multi-timeframe support.
    
    Demonstrates:
    - @on_timeframe decorator for higher timeframe handlers
    - ctx.timeframe_history() for accessing higher timeframe data
    - Engine manages dispatch automatically (no manual call)
    - compute_indicators with timeframe parameter
    """

    def compute_indicators(self, candles, timeframe=None):
        """Compute RSI indicators for the given timeframe."""
        df = pd.DataFrame(candles)
        df['rsi'] = ta.rsi(df['close'], length=14)
        logger.info(f"Computed RSI indicators for {len(df)} candles (timeframe={timeframe}).")
        return [{"rsi": row["rsi"]} for row in df.to_dict(orient="records")]

    def on_candle(self, candle):
        """Main per-bar logic on base timeframe."""
        # Access base timeframe history
        prev_candle = self.ctx.history[-2] if len(self.ctx.history) >= 2 else None
        
        rsi_value = candle.indicators.get('rsi')
        prev_rsi_value = prev_candle.indicators.get('rsi') if prev_candle else None
        
        if (rsi_value is not None) and (prev_rsi_value is not None):
            if (rsi_value > 70) and (prev_rsi_value <= 70):
                self.ctx.submit_order(
                    candle.symbol, OrderSide.BUY, 1)  # Buy signal
            elif (rsi_value < 30) and (prev_rsi_value >= 30):
                self.ctx.submit_order(
                    candle.symbol, OrderSide.SELL, 1)  # Sell signal

        # Access higher timeframe data via ctx.timeframe_history()
        tf_1h = self.ctx.timeframe_history("1H")
        tf_1d = self.ctx.timeframe_history("1D")
        logger.info(
            "[%s] base_history=%d, timeframe_history(1H)=%d, timeframe_history(1D)=%d",
            candle.timestamp, len(self.ctx.history), len(tf_1h), len(tf_1d)
        )

        # Engine manages timeframe dispatch automatically.
        # Researchers never call dispatch_timeframes() manually.

    @on_timeframe("1H")
    def on_1h_candle(self, candle):
        """Called on each 1H candle boundary."""
        logger.info(
            "[%s] >>> 1H candle: O=%.2f H=%.2f L=%.2f C=%.2f RSI=%.2f",
            candle.timestamp, candle.open, candle.high, candle.low, candle.close,
            candle.indicators.get('rsi', 0)
        )

    @on_timeframe("1D")
    def on_daily_candle(self, candle):
        """Called on each daily candle boundary."""
        logger.info(
            "[%s] >>> 1D candle: O=%.2f H=%.2f L=%.2f C=%.2f RSI=%.2f",
            candle.timestamp, candle.open, candle.high, candle.low, candle.close,
            candle.indicators.get('rsi', 0)
        )


if __name__ == "__main__":
    from quantrex_core.logging import setup_logging
    setup_logging(level="INFO")

    symbol = "TCS"
    provider = DhanDataProvider(
        symbol=symbol,
        exchange_segment="NSE_EQ",
        instrument="EQUITY",
        from_date="2026-01-01",
        to_date="2026-01-30",
    )
    adapter = DhanDataAdapter(provider)
    
    strategy = MultiTimeframeRsiStrategy()
    
    instruments = [
        InstrumentSpec(symbol=symbol, adapter=adapter),
    ]
    config = PortfolioConfig(initial_cash=1_000_000.0)
    
    engine = BacktestEngine(instruments=instruments, strategy=strategy, config=config)
    engine.run()