from quantrex_core import Strategy
from quantrex_core.logging import get_logger
from quantrex_core.models.enums import OrderSide
from quantrex_data.providers.dhan_provider import DhanDataProvider
from quantrex_data.adapters.dhan_adapter import DhanDataAdapter

from quantrex_backtest import BacktestEngine

import pandas as pd
import pandas_ta as ta



logger = get_logger(__name__)

class RsiExampleStrategy(Strategy):
    def compute_indicators(self, candles):
        df = pd.DataFrame(candles)
        df['rsi'] = ta.rsi(df['close'], length=14)
        logger.info(f"Computed RSI indicators for {len(df)} candles.")
        return df.to_dict(orient='records')

    def on_candle(self, candle):
        rsi_value = candle.indicators.get('rsi')
        if rsi_value is not None:
            logger.info(f"RSI value for {candle.symbol} at {candle.timestamp}: {rsi_value}")
            if (rsi_value > 70) and (self.ctx.get_position(candle.symbol).quantity == 0):
                self.ctx.submit_order(
                    candle.symbol, OrderSide.BUY, 1)  # Buy signal
            elif (rsi_value < 30) and (self.ctx.get_position(candle.symbol).quantity > 0):
                self.ctx.submit_order(
                    candle.symbol, OrderSide.SELL, 1)  # Sell signal


if __name__ == "__main__":
    symbol = "TCS"
    provider = DhanDataProvider(symbol=symbol, exchange_segment="NSE_EQ", instrument="EQUITY",
                                from_date="2026-01-01", to_date="2026-06-30", timeframe="1minute")
    adapter = DhanDataAdapter(provider)
    
    strategy = RsiExampleStrategy()
    
    engine = BacktestEngine(strategy=strategy, adapter=adapter, symbol=symbol)
    engine.run()
    