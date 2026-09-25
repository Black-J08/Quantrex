"""Forward Return Distribution Example Research Script.

This example demonstrates how to use the ForwardReturnComponent to analyze
forward return distributions for the exact entry condition from
portfolio_intraday_breakout_strategy.py (hourly inside breakout strategy).
"""

from datetime import timedelta, time

import pandas as pd
import pandas_ta_classic as ta
from quantrex_core import Strategy
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.logging import setup_logging, get_logger
from quantrex_core.strategy.timeframe import on_timeframe

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig

from quantrex_data.providers.csv_provider import CSVDataProvider
from quantrex_data.adapters.csv_adapter import CSVDataAdapter

from quantrex_backtest import InstrumentSpec, BacktestConfig

from quantrex_data.adapters.zerodha_adapter import ZerodhaDataAdapter
from quantrex_data.providers.zerodha_provider.provider import ZerodhaDataProvider


logger = get_logger(__name__)


class HourlyInsideBreakoutResearch(ForwardReturnComponent):
    """Research component that detects hourly inside breakout patterns
    and analyzes forward returns - using the EXACT entry logic from
    portfolio_intraday_breakout_strategy.py.
    """

    def __init__(self):
        config = ForwardReturnConfig(
            horizons=[
                timedelta(minutes=5),
                timedelta(minutes=15),
                timedelta(minutes=60),
                timedelta(minutes=120),
                timedelta(minutes=180),
                timedelta(minutes=240),
                timedelta(minutes=360),
            ],
            boundary_handling="nan",
            missing_data_handling="skip",
        )
        super().__init__(config)
        self._mother_candle: dict[str, Candle | None] = {}
        self._inside_candle: dict[str, Candle | None] = {}
        self._entry_pre_setup_condition_met: dict[str, bool] = {}

    def reset_state(self, symbol: str):
        self._mother_candle[symbol] = None
        self._inside_candle[symbol] = None
        self._entry_pre_setup_condition_met[symbol] = False
        
    # def compute_indicators(self, candles, timeframe="1H"):
    #     df = pd.DataFrame(candles)
    #     df['rsi'] = ta.rsi(df['close'], length=14)
    #     logger.info(f"Computed RSI indicators for {len(df)} candles (timeframe={timeframe}).")
    #     # Return only the calculated RSI indicator, not raw OHLCV columns.
    #     return [{"rsi": row["rsi"]} for row in df.to_dict(orient="records")]


    @on_timeframe("1H")
    def on_hour_candle(self, candle: Candle):
        """EXACT logic from portfolio_intraday_breakout_strategy.py"""
        symbol = candle.symbol
        prev_1h_candle = self.ctx.timeframe_history("1H")[-2] if len(self.ctx.timeframe_history("1H")) >= 2 else None
        logger.info(f"[{symbol}] Received 1H candle: {candle}")
        logger.info(f"[{symbol}] Previous 1H candle: {prev_1h_candle}")

        if prev_1h_candle is not None:
            if candle.high < prev_1h_candle.high and candle.low > prev_1h_candle.low:
                self._mother_candle[symbol] = prev_1h_candle
                self._inside_candle[symbol] = candle
                self._entry_pre_setup_condition_met[symbol] = True
                logger.info(
                    f"[{symbol}] Mother candle detected: {self._mother_candle[symbol]}")
                logger.info(
                    f"[{symbol}] Inside candle detected: {self._inside_candle[symbol]}")
            else:
                self.reset_state(symbol)

    def on_candle(self, candle: Candle):
        """EXACT logic from portfolio_intraday_breakout_strategy.py"""
        symbol = candle.symbol

        # Initialize state for new symbols
        if symbol not in self._entry_pre_setup_condition_met:
            self.reset_state(symbol)

        prev_candle = self.ctx.history[-2] if len(self.ctx.history) >= 2 else None
        if prev_candle is not None:
            if prev_candle.timestamp.date() != candle.timestamp.date():
                self.reset_state(symbol)
                

        position = self.ctx.get_position(symbol)

        # Breakout entry logic - EXACT from portfolio_intraday_breakout_strategy.py
        if self._entry_pre_setup_condition_met.get(symbol, False) and position.quantity == 0:
            inside_candle = self._inside_candle.get(symbol)
            if inside_candle is None:
                return

            if (candle.close > inside_candle.high):
                logger.info(
                    f"[{symbol}] Breakout BUY detected at {candle.close} on {candle.timestamp}")
                self.emit_event(symbol, OrderSide.BUY, candle.timestamp, {
                    "reason": "breakout_up",
                    "inside_high": inside_candle.high,
                    "close": candle.close,
                })
                self.reset_state(symbol)
            elif (candle.close < inside_candle.low):
                logger.info(
                    f"[{symbol}] Breakout SELL detected at {candle.close} on {candle.timestamp}")
                self.emit_event(symbol, OrderSide.SELL, candle.timestamp, {
                    "reason": "breakout_down",
                    "inside_low": inside_candle.low,
                    "close": candle.close,
                })
                self.reset_state(symbol)


if __name__ == "__main__":
    setup_logging(level="INFO")
    
    # Create research component
    research = HourlyInsideBreakoutResearch()
    
    # Define instruments using CSV data (for testing)
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
        # InstrumentSpec(
        #     symbol="HDFCBANK",
        #     adapter=ZerodhaDataAdapter(
        #         ZerodhaDataProvider(
        #             symbol="HDFCBANK",
        #             exchange_segment="NSE",
        #         )
        #     ),
        # ),
        # InstrumentSpec(
        #     symbol="SUNPHARMA",
        #     adapter=ZerodhaDataAdapter(
        #         ZerodhaDataProvider(
        #             symbol="SUNPHARMA",
        #             exchange_segment="NSE",
        #         )
        #     ),
        # ),
    ]
    
    # Create and run engine
    engine = ResearchEngine(
        instruments=instruments,
        research_components=[research],
        data_start="2024-09-01",
        data_end="2025-08-31",
    )
    
    results = engine.run()
    
    # Print summary
    for component_name, result in results.items():
        print(f"\n=== {component_name} Results ===")
        if hasattr(result, 'horizon_stats'):
            for horizon, stats in result.horizon_stats.items():
                print(f"  Horizon {horizon}:")
                print(f"    Count: {stats.get('count', 0)}")
                print(f"    Mean: {stats.get('mean', 0):.4f}%")
                print(f"    Median: {stats.get('median', 0):.4f}%")
                print(f"    Std: {stats.get('std', 0):.4f}%")
                print(f"    Positive Prob: {stats.get('positive_prob', 0):.2%}")
                print(f"    VaR 95%: {stats.get('VaR_95', 0):.4f}%")
                print(f"    CVaR 95%: {stats.get('CVaR_95', 0):.4f}%")
