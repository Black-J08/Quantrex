#!/usr/bin/env python3
"""
Test script to run both strategies with CSV data for profiling.
This avoids the need for Zerodha authentication.
Uses quantrex-test-support package for CSV generation.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from quantrex_core.logging import get_logger, setup_logging
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.strategy.base import Strategy
from quantrex_core.strategy.timeframe import on_timeframe
from quantrex_data.providers.csv_provider import CSVDataProvider
from quantrex_data.adapters.csv_adapter import CSVDataAdapter
from quantrex_backtest import BacktestEngine
from quantrex_test_support.csv import make_ohlc_series, csv_rows_to_string, create_temp_csv

logger = get_logger(__name__)


class MCBStrategyCSV(Strategy):
    """MCB Breakout Strategy adapted for CSV data."""

    def __init__(self):
        super().__init__()
        self.current_breakout_high = None
        self.current_breakout_low = None
        self.breakout_check_date = None
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
            self.consecutive_red_30m = 0
            self.consecutive_green_30m = 0

        is_red = candle.close < candle.open
        is_green = candle.close >= candle.open
        
        position = self.ctx.get_position(candle.symbol)
        
        if position.quantity > 0:  # long position
            if is_red:
                self.consecutive_red_30m += 1
                self.consecutive_green_30m = 0
            else:
                self.consecutive_red_30m = 0
                self.consecutive_green_30m += 1
        elif position.quantity < 0:  # short position
            if is_green:
                self.consecutive_green_30m += 1
                self.consecutive_red_30m = 0
            else:
                self.consecutive_green_30m = 0
                self.consecutive_red_30m += 1
                
        position = self.ctx.get_position(candle.symbol)
        current_date = candle.timestamp.date()

        if hasattr(self, '_last_candle_date') and current_date != self._last_candle_date:
            self.consecutive_red_30m = 0
            self.consecutive_green_30m = 0
        self._last_candle_date = current_date

        if position.quantity > 0:  # long
            if (self.consecutive_red_30m >= 2 and 
                self.entry_date is not None and 
                current_date != self.entry_date):
                logger.info(f"Exiting long after 2 consecutive red 30-minute candles: {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(
                    symbol=candle.symbol,
                    side=OrderSide.SELL,
                    quantity=position.quantity
                )
                self.entry_date = None
                self.consecutive_red_30m = 0
                self.consecutive_green_30m = 0
        elif position.quantity < 0:  # short
            if (self.consecutive_green_30m >= 2 and 
                self.entry_date is not None and 
                current_date != self.entry_date):
                logger.info(f"Exiting short after 2 consecutive green 30-minute candles: {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(
                    symbol=candle.symbol,
                    side=OrderSide.BUY,
                    quantity=-position.quantity
                )
                self.entry_date = None
                self.consecutive_red_30m = 0
                self.consecutive_green_30m = 0

    def on_candle(self, candle: Candle):
        """Handle all candles."""
        position = self.ctx.get_position(candle.symbol)
        current_date = candle.timestamp.date()

        if position.quantity == 0:
            if (self.current_breakout_high is not None) and (candle.close > self.current_breakout_high):
                logger.info(f"Breakout high hit at {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(
                    symbol=candle.symbol,
                    side=OrderSide.BUY,
                    quantity=10.0
                )
                self.entry_date = current_date
                self.consecutive_red_30m = 0
                self.consecutive_green_30m = 0
            elif (self.current_breakout_low is not None) and (candle.close < self.current_breakout_low):
                logger.info(f"Breakout low hit at {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(
                    symbol=candle.symbol,
                    side=OrderSide.SELL,
                    quantity=10.0
                )
                self.entry_date = current_date
                self.consecutive_red_30m = 0
                self.consecutive_green_30m = 0


class HourlyInsideBreakoutStrategyCSV(Strategy):
    """Intraday Breakout Strategy adapted for CSV data."""

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
        prev_1h_candle = self.ctx.timeframe_history("1H")[-2] if len(self.ctx.timeframe_history("1H")) >= 2 else None

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
        prev_candle = self.ctx.history[-2] if len(self.ctx.history) >= 2 else None
        if prev_candle is not None:
            if (prev_candle.timestamp.date() != candle.timestamp.date()):
                self.reset_state()

        position = self.ctx.get_position(candle.symbol)

        if (candle.timestamp.time() >= __import__("datetime").time(15, 15)):
            if position.quantity > 0:
                logger.info(f"Exiting long position at {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(candle.symbol, OrderSide.SELL, position.quantity)
                self.reset_state()
            elif position.quantity < 0:
                logger.info(f"Exiting short position at {candle.close} on {candle.timestamp}")
                self.ctx.submit_order(candle.symbol, OrderSide.BUY, abs(position.quantity))
                self.reset_state()

        if self._entry_pre_setup_condition_met and position.quantity == 0:
            if candle.close > self._inside_candle.high:
                self.ctx.submit_order(candle.symbol, OrderSide.BUY, 8)
                logger.info(f"Breakout BUY order placed at {candle.close} on {candle.timestamp}")
                self.reset_state()
            elif candle.close < self._inside_candle.low:
                self.ctx.submit_order(candle.symbol, OrderSide.SELL, 8)
                logger.info(f"Breakout SELL order placed at {candle.close} on {candle.timestamp}")
                self.reset_state()


def run_strategy(strategy_class, strategy_name, num_rows=5000):
    """Run a strategy with generated CSV data."""
    print(f"\n{'='*60}")
    print(f"Running {strategy_name} with {num_rows} generated rows")
    print(f"{'='*60}")
    
    setup_logging(level="INFO")
    
    # Generate synthetic OHLC data using test-support helpers
    rows = make_ohlc_series(
        num_rows=num_rows,
        start_datetime=__import__("datetime").datetime(2024, 1, 1, 9, 15),
        interval_minutes=1,
        start_price=737.20,
        volatility=0.015,
        drift=0.0001,
        volume_range=(1, 100),
        seed=42,
    )
    csv_content = csv_rows_to_string(rows)
    
    # Create temporary CSV file and configure data source
    with create_temp_csv(csv_content) as temp_path:
        provider = CSVDataProvider(temp_path, has_header=False)
        adapter = CSVDataAdapter(
            provider,
            column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            },
            datetime_format="%Y%m%d %H:%M",
        )
        
        strategy = strategy_class()
        engine = BacktestEngine(adapter, strategy, symbol="COPPER")
        
        try:
            engine.run()
            print(f"✓ {strategy_name} completed successfully")
        except Exception as e:
            logger.exception(f"Error running {strategy_name}")
            print(f"✗ {strategy_name} failed: {e}")
        finally:
            adapter.close()


if __name__ == "__main__":
    print("Quantrex Strategy Profiling Test Run")
    print("Using generated CSV data from quantrex-test-support")
    
    # Run MCB strategy with 5000 rows (~3.5 trading days of 1-minute data)
    run_strategy(MCBStrategyCSV, "MCB Breakout Strategy", num_rows=5000)
    
    # Run Intraday Breakout strategy with 5000 rows
    run_strategy(HourlyInsideBreakoutStrategyCSV, "Intraday Breakout Strategy", num_rows=5000)
    
    print("\nAll strategies completed!")