"""EMA VWAP Pullback Strategy.

Entry conditions (from research):
- Regime: EMA 20 vs VWAP crossover (bullish if EMA > VWAP, bearish if EMA < VWAP)
- Stochastic: bull cross after bear cross (bullish) or bear cross after bull cross (bearish)
- Close crosses EMA 20 in regime direction
- Max 1 trade per day per symbol
- No new entries after 13:00

Exit: All positions closed at 15:15
"""

from datetime import time

import pandas as pd
import pandas_ta_classic as ta

from quantrex_core import Strategy
from quantrex_core.models import Candle
from quantrex_core.logging import get_logger
from quantrex_core.models.enums import OrderSide
from quantrex_core.strategy.timeframe import on_timeframe

from quantrex_backtest import BacktestEngine, InstrumentSpec, BacktestConfig

from quantrex_data.providers.zerodha_provider import ZerodhaDataProvider
from quantrex_data.adapters.zerodha_adapter import ZerodhaDataAdapter


logger = get_logger(__name__)


class EMAVWAPPullbackStrategy(Strategy):
    """Minimal EMA VWAP Pullback strategy for intraday trading."""

    def __init__(self):
        super().__init__()
        self._trade_count_per_day: dict[str, int] = {}
        self._dfs_5min: dict[str, pd.DataFrame] = {}
        # Fixed target price at entry
        self._target_price: dict[str, float] = {}
        # Fixed stop-loss price at entry
        self._stop_price: dict[str, float] = {}

    def compute_indicators(self, candles, timeframe=None, symbol=None):
        df = pd.DataFrame(candles)

        # Calculate 20-period EMA on Close
        df['ema_20'] = ta.ema(df['close'], length=20)
        df_stoch = ta.stoch(df['high'], df['low'], df['close'])
        df['stoch_k'], df['stoch_d'] = df_stoch['STOCHk_14_3_3'], df_stoch['STOCHd_14_3_3']

        # Calculate ATR (14-period) for target/stop-loss
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)

        # Calculate session-based VWAP (resets daily at market open)
        df['date'] = pd.to_datetime(df['datetime']).dt.date

        vwap_values = []
        for date, group in df.groupby('date'):
            typical_price = (group['high'] + group['low'] + group['close']) / 3
            cum_pv = (typical_price * group['volume']).cumsum()
            cum_vol = group['volume'].cumsum()
            vwap_values.extend((cum_pv / cum_vol).tolist())

        df['vwap'] = vwap_values

        # Store per-symbol dataframe for use in on_5min_candle
        if timeframe == "5M" and symbol is not None:
            self._dfs_5min[symbol] = df.copy()
            self._dfs_5min[symbol]['index'] = self._dfs_5min[symbol]['datetime']
            self._dfs_5min[symbol]['datetime'] = pd.to_datetime(df['datetime'])
            self._dfs_5min[symbol].set_index('index', inplace=True)

        return [
            {"ema_20": row["ema_20"], "vwap": row["vwap"], "stoch_k": row["stoch_k"],
                "stoch_d": row["stoch_d"], "atr": row["atr"]}
            for _, row in df.iterrows()
        ]

    def _reset_daily_state(self, symbol: str):
        logger.info("NEW DAY RESET")
        self._trade_count_per_day[symbol] = 0
        self._target_price.pop(symbol, None)
        self._stop_price.pop(symbol, None)

    def _get_last_regime_split(self, timestamp, symbol):
        df_5min = self._dfs_5min[symbol]
        if df_5min is None:
            return pd.DataFrame()
        current_day_df = df_5min[(df_5min["date"] == timestamp.date()) & (
            df_5min['datetime'] <= timestamp)]
        crossovers = current_day_df[((current_day_df['ema_20'] > current_day_df['vwap']) & (current_day_df['ema_20'].shift(1) < current_day_df['vwap'].shift(1))) |
                                    ((current_day_df['ema_20'] < current_day_df['vwap']) & (current_day_df['ema_20'].shift(1) > current_day_df['vwap'].shift(1)))]
        if crossovers.empty:
            return current_day_df
        return current_day_df[current_day_df.index >= crossovers.index[-1]]

    def _check_stochastic_conditions(self, regime_df, regime_direction):
        if len(regime_df) < 2:
            return None

        last_stoch_bull_cross_df = regime_df[(
            regime_df['stoch_k'] > regime_df['stoch_d']) & (regime_df['stoch_k'].shift(1) < regime_df['stoch_d'].shift(1))]
        last_stoch_bear_cross_df = regime_df[(
            regime_df['stoch_k'] < regime_df['stoch_d']) & (regime_df['stoch_k'].shift(1) > regime_df['stoch_d'].shift(1))]

        if last_stoch_bull_cross_df.empty or last_stoch_bear_cross_df.empty:
            return None

        last_stoch_bull_cross = last_stoch_bull_cross_df.index[-1]
        last_stoch_bear_cross = last_stoch_bear_cross_df.index[-1]

        if (regime_direction == 1) and (last_stoch_bull_cross > last_stoch_bear_cross):
            return 1
        elif (regime_direction == -1) and (last_stoch_bull_cross < last_stoch_bear_cross):
            return -1
        return None

    def _check_close_cross_ema(self, regime_df):
        if len(regime_df) < 2:
            return None

        if (regime_df.loc[regime_df.index[-1], 'close'] > regime_df.loc[regime_df.index[-1], 'ema_20']) and (regime_df.loc[regime_df.index[-2], 'close'] < regime_df.loc[regime_df.index[-2], 'ema_20']):
            return 1
        elif (regime_df.loc[regime_df.index[-1], 'close'] < regime_df.loc[regime_df.index[-1], 'ema_20']) and (regime_df.loc[regime_df.index[-2], 'close'] > regime_df.loc[regime_df.index[-2], 'ema_20']):
            return -1
        return None

    @on_timeframe("5M")
    def on_5min_candle(self, candle: Candle):
        timestamp = candle.timestamp
        symbol = candle.symbol
        indicators = candle.indicators

        # Initialize per-symbol state
        if symbol not in self._trade_count_per_day:
            self._trade_count_per_day[symbol] = 0

        last_regime_df = self._get_last_regime_split(timestamp, symbol)
        if last_regime_df.empty:
            return

        regime_direction = 1 if (last_regime_df.at[last_regime_df.index[-1],
                                                   'ema_20'] > last_regime_df.at[last_regime_df.index[-1], 'vwap']) else -1

        stoch_cond = self._check_stochastic_conditions(
            last_regime_df, regime_direction)
        close_cross_ema = self._check_close_cross_ema(last_regime_df)

        # No new entries after 13:00
        if timestamp.time() > time(13, 0):
            return

        position = self.ctx.get_position(symbol)
        atr = indicators.get('atr')

        # Entry logic - set target/stop immediately after entry
        if (stoch_cond == 1) and (close_cross_ema == 1) and (self._trade_count_per_day[symbol] < 1) and position.quantity == 0:
            self.ctx.submit_order(symbol, OrderSide.BUY, 100000//candle.close)
            logger.info(
                f"[{symbol}] LONG entry at {candle.close} on {timestamp}")
            self._trade_count_per_day[symbol] += 1
            self._target_price[symbol] = candle.close + 2 * atr
            self._stop_price[symbol] = candle.low - 1 * atr
        elif (stoch_cond == -1) and (close_cross_ema == -1) and (self._trade_count_per_day[symbol] < 1) and position.quantity == 0:
            self.ctx.submit_order(symbol, OrderSide.SELL, 100000//candle.close)
            logger.info(
                f"[{symbol}] SHORT entry at {candle.close} on {timestamp}")
            self._trade_count_per_day[symbol] += 1
            self._target_price[symbol] = candle.close - 2 * atr
            self._stop_price[symbol] = candle.high + 1 * atr

    def _exit_position(self, symbol: str, position, candle: Candle, reason: str):
        """Helper to exit position and log."""
        if position.quantity > 0:
            logger.info(
                f"[{symbol}] Exiting LONG at {candle.close} on {candle.timestamp} ({reason})")
            self.ctx.submit_order(symbol, OrderSide.SELL, position.quantity)
        elif position.quantity < 0:
            logger.info(
                f"[{symbol}] Exiting SHORT at {candle.close} on {candle.timestamp} ({reason})")
            self.ctx.submit_order(symbol, OrderSide.BUY,
                                  abs(position.quantity))
        # self._target_price.pop(symbol, None)
        # self._stop_price.pop(symbol, None)

    def on_candle(self, candle: Candle):
        symbol = candle.symbol
        indicators = candle.indicators

        # Initialize state for new symbols
        if symbol not in self._trade_count_per_day:
            self._trade_count_per_day[symbol] = 0

        # Reset daily state on new trading day
        prev_candle = self.ctx.history[-2] if len(
            self.ctx.history) >= 2 else None
        if prev_candle is not None and prev_candle.timestamp.date() != candle.timestamp.date():
            self._reset_daily_state(symbol)

        position = self.ctx.get_position(symbol)

        # Exit logic - simplified with early returns
        if position.quantity == 0:
            pass  # No position, check entries below
            # self._target_price.pop(symbol, None)
            # self._stop_price.pop(symbol, None)
        elif (candle.timestamp.time() >= time(14, 49)):
            # Intraday exit
            self._exit_position(symbol, position, candle, "EOD")
        elif position.quantity > 0:
            # Long position exits
            if candle.close >= self._target_price[symbol]:
                self._exit_position(symbol, position, candle, "ATR_TARGET_3X")
            elif candle.close <= self._stop_price[symbol]:
                self._exit_position(symbol, position, candle, "ATR_SL_1X")
        elif position.quantity < 0:
            # Short position exits
            if candle.close <= self._target_price[symbol]:
                self._exit_position(symbol, position, candle, "ATR_TARGET_3X")
            elif candle.close >= self._stop_price[symbol]:
                self._exit_position(symbol, position, candle, "ATR_SL_1X")


if __name__ == "__main__":
    from quantrex_core.logging import setup_logging

    setup_logging(level="INFO")

    strategy = EMAVWAPPullbackStrategy()

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
            symbol="BHARTIARTL",
            adapter=ZerodhaDataAdapter(
                ZerodhaDataProvider(
                    symbol="BHARTIARTL",
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
        InstrumentSpec(
            symbol="ICICIBANK",
            adapter=ZerodhaDataAdapter(
                ZerodhaDataProvider(
                    symbol="ICICIBANK",
                    exchange_segment="NSE",
                )
            ),
        ),
    ]

    config = BacktestConfig(
        initial_cash=1_000_000.0,
        data_start="2025-01-01",
        data_end="2026-09-30",
    )
    engine = BacktestEngine(instruments, strategy, config)
    engine.run()
