from quantrex_core import Strategy
from quantrex_core.logging import get_logger
from quantrex_core.models.enums import OrderSide
from quantrex_data.providers.dhan_provider import DhanDataProvider
from quantrex_data.adapters.dhan_adapter import DhanDataAdapter

from quantrex_backtest import BacktestEngine

import pandas as pd
import pandas_ta_classic as ta



logger = get_logger(__name__)

class RsiExampleStrategy(Strategy):
    def compute_indicators(self, candles, timeframe=None):
        df = pd.DataFrame(candles)
        df['rsi'] = ta.rsi(df['close'], length=14)
        logger.info(f"Computed RSI indicators for {len(df)} candles (timeframe={timeframe}).")
        # Return only the calculated RSI indicator, not raw OHLCV columns.
        return [{"rsi": row["rsi"]} for row in df.to_dict(orient="records")]

    def on_candle(self, candle):
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


if __name__ == "__main__":
    symbol = "TCS"
    provider = DhanDataProvider(symbol=symbol, exchange_segment="NSE_EQ", instrument="EQUITY",
                                from_date="2026-01-01", to_date="2026-01-30", timeframe="1minute")
    adapter = DhanDataAdapter(provider)
    
    strategy = RsiExampleStrategy()
    
    engine = BacktestEngine(strategy=strategy, adapter=adapter, symbol=symbol)
    engine.run()
    