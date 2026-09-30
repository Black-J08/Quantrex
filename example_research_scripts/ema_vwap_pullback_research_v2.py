
from datetime import timedelta, time
from typing import Dict, List

import pandas as pd
import pandas_ta_classic as ta

from quantrex_core import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.strategy.timeframe import on_timeframe
from quantrex_core.logging import setup_logging, get_logger

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig

from quantrex_backtest import InstrumentSpec

from quantrex_data.adapters.zerodha_adapter import ZerodhaDataAdapter
from quantrex_data.providers.zerodha_provider.provider import ZerodhaDataProvider

logger = get_logger(__name__)


class EMAVWAPPullbackResearch(ForwardReturnComponent):
    """Research component that detects 20 EMA + VWAP pullback patterns
    and analyzes forward returns for intraday equities strategy.
    """

    def __init__(self):
        # Configure forward return horizons for intraday analysis
        config = ForwardReturnConfig(
            horizons=[
                timedelta(minutes=5),
                timedelta(minutes=15),
                timedelta(minutes=30),
                timedelta(minutes=60),
                timedelta(minutes=120),
                timedelta(minutes=180),
            ],
            boundary_handling="nan",
            missing_data_handling="skip",
        )
        super().__init__(config)

        # Per-symbol state
        self.breakout_direction: Dict[str, int | None] = {}
        self.in_pullback: Dict[str, bool] = {}
        self.trade_count_per_day: Dict[str, int] = {}
        # Per-symbol 5min dataframes (compute_indicators must be pure - no self mutation)
        self._dfs_5min: Dict[str, pd.DataFrame] = {}

    def compute_indicators(self, candles: List[Candle], timeframe: str = "5min", symbol: str | None = None) -> List[Dict]:
        """Pre-compute 20 EMA and VWAP indicators for all candles.

        Args:
            candles: List of Candle objects
            timeframe: Timeframe of candles (default: "5min")

        Returns:
            List of dicts with 'ema_20' and 'vwap' for each candle
        """
        # Convert candles to DataFrame
        df = pd.DataFrame(candles)

        # Calculate 20-period EMA on Close
        df['ema_20'] = ta.ema(df['close'], length=20)
        df_stoch = ta.stoch(df['high'], df['low'], df['close'])
        df['stoch_k'], df['stoch_d'] = df_stoch['STOCHk_14_3_3'], df_stoch['STOCHd_14_3_3']

        # Calculate session-based VWAP (resets daily at market open)
        # VWAP = cumulative(typical_price * volume) / cumulative(volume) per session
        # Typical Price = (High + Low + Close) / 3 (HLC3) - industry standard
        df['date'] = pd.to_datetime(df['datetime']).dt.date

        # Manual VWAP calculation per date to avoid groupby apply issues
        vwap_values = []
        for date, group in df.groupby('date'):
            typical_price = (group['high'] + group['low'] + group['close']) / 3
            cum_pv = (typical_price * group['volume']).cumsum()
            cum_vol = group['volume'].cumsum()
            vwap_values.extend((cum_pv / cum_vol).tolist())

        df['vwap'] = vwap_values

        # Store per-symbol dataframe for use in on_5min_candle
        # Symbol is provided by the engine
        if timeframe == "5M" and symbol is not None:
            self._dfs_5min[symbol] = df.copy()
            self._dfs_5min[symbol]['index'] = self._dfs_5min[symbol]['datetime']
            self._dfs_5min[symbol]['datetime'] = pd.to_datetime(df['datetime'])
            self._dfs_5min[symbol].set_index('index', inplace=True)

        # Return list of indicator dicts
        return [
            {"ema_20": row["ema_20"], "vwap": row["vwap"]}
            for _, row in df.iterrows()
        ]

    def reset_state(self, symbol: str):
        self.breakout_direction[symbol] = None
        self.in_pullback[symbol] = False
        self.trade_count_per_day[symbol] = 0
        
    def get_last_regime_split(self, timestamp, symbol):
        df_5min = self._dfs_5min.get(symbol)
        if df_5min is None:
            return pd.DataFrame()
        current_day_df = df_5min[(df_5min["date"] == timestamp.date()) & (
            df_5min['datetime'] <= timestamp)]
        crossovers = current_day_df[((current_day_df['ema_20'] > current_day_df['vwap']) & (current_day_df['ema_20'].shift(1) < current_day_df['vwap'].shift(1))) |
                                    ((current_day_df['ema_20'] < current_day_df['vwap']) & (current_day_df['ema_20'].shift(1) > current_day_df['vwap'].shift(1)))]
        if crossovers.empty:
            return current_day_df

        return current_day_df[current_day_df.index >= crossovers.index[-1]]

    def check_stochastic_conditions(self, regime_df, regime_direction):
        if len(regime_df) < 2:
            return None

        # last_stoch_bull_cross_df = regime_df[(30 > regime_df['stoch_d']) & (
        #     regime_df['stoch_k'] > regime_df['stoch_d']) & (regime_df['stoch_k'].shift(1) < regime_df['stoch_d'].shift(1))]
        # last_stoch_bear_cross_df = regime_df[(70 < regime_df['stoch_d']) & (
        #     regime_df['stoch_k'] < regime_df['stoch_d']) & (regime_df['stoch_k'].shift(1) > regime_df['stoch_d'].shift(1))]

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
        else:
            return None

    def check_close_cross_ema(self, regime_df):
        if len(regime_df) < 2:
            return None

        if (regime_df.loc[regime_df.index[-1], 'close'] > regime_df.loc[regime_df.index[-1], 'ema_20']) and (regime_df.loc[regime_df.index[-2], 'close'] < regime_df.loc[regime_df.index[-2], 'ema_20']):
            return 1
        elif (regime_df.loc[regime_df.index[-1], 'close'] < regime_df.loc[regime_df.index[-1], 'ema_20']) and (regime_df.loc[regime_df.index[-2], 'close'] > regime_df.loc[regime_df.index[-2], 'ema_20']):
            return -1
        else:
            return None

    @on_timeframe("5M")
    def on_5min_candle(self, candle: Candle):
        timestamp = candle.timestamp
        symbol = candle.symbol
        indicators = candle.indicators
        logger.debug(
            f"[{symbol}] 5min candle: {candle}")

        if timestamp.time() > time(13, 0):
            return

        # Initialize per-symbol state if not already initialized
        if symbol not in self.breakout_direction:
            self.breakout_direction[symbol] = None
            self.in_pullback[symbol] = False
            self.trade_count_per_day[symbol] = 0


        last_regime_df = self.get_last_regime_split(timestamp, symbol)
        if last_regime_df.empty:
            logger.warning(f"[{symbol}] No regime data available for {timestamp}. Skipping.")
            return
        regime_direction = 1 if last_regime_df.loc[last_regime_df.index[-1],
                                                   'ema_20'] > last_regime_df.loc[last_regime_df.index[-1], 'vwap'] else -1

        stoch_cond = self.check_stochastic_conditions(
            last_regime_df, regime_direction)
        close_cross_ema = self.check_close_cross_ema(last_regime_df)

        if (stoch_cond == 1) and (close_cross_ema == 1) and (self.trade_count_per_day[symbol] < 1):
            self.emit_event(symbol, OrderSide.BUY,
                            timestamp, {"direction": "LONG"}, emission_candle=candle)
            logger.info("LONG")
            self.trade_count_per_day[symbol] += 1
        elif (stoch_cond == -1) and (close_cross_ema == -1) and (self.trade_count_per_day[symbol] < 1):
            self.emit_event(symbol, OrderSide.SELL,
                            timestamp, {"direction": "SHORT"}, emission_candle=candle)
            logger.info("SHORT")
            self.trade_count_per_day[symbol] += 1
            
    def on_candle(self, candle):
        symbol = candle.symbol
        prev_1m_candle = self.ctx.history[-2] if len(
            self.ctx.history) >= 2 else None
        logger.info("======TEST=======")
        logger.info(prev_1m_candle)
        logger.info(candle)
        if (prev_1m_candle is not None) and (prev_1m_candle.timestamp.date() != candle.timestamp.date()):
            logger.info(
                f"[{symbol}] New trading day detected. Resetting state.")
            self.reset_state(symbol)


if __name__ == "__main__":
    setup_logging(level="DEBUG")

    # Define instruments using Zerodha data (NSE equities)
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
            symbol="MARUTI",
            adapter=ZerodhaDataAdapter(
                ZerodhaDataProvider(
                    symbol="MARUTI",
                    exchange_segment="NSE",
                )
            ),
        ),
        InstrumentSpec(
            symbol="BAJAJFINSV",
            adapter=ZerodhaDataAdapter(
                ZerodhaDataProvider(
                    symbol="BAJAJFINSV",
                    exchange_segment="NSE",
                )
            ),
        ),
        InstrumentSpec(
            symbol="HDFCBANK",
            adapter=ZerodhaDataAdapter(
                ZerodhaDataProvider(
                    symbol="HDFCBANK",
                    exchange_segment="NSE",
                )
            ),
        ),
    ]

    # Create research component
    research = EMAVWAPPullbackResearch()

    # Create and run engine
    engine = ResearchEngine(
        instruments=instruments,
        research_components=[research],
        data_start="2026-09-01",
        data_end="2026-09-30",
        script_path=__file__,
    )

    results = engine.run()
