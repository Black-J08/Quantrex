"""Backtest Portfolio Context implementation."""

from datetime import datetime
from typing import Dict, List, Optional

from quantrex_core import PortfolioContext, Position
from quantrex_core.logging import get_logger
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide, OrderType, OrderStatus
from quantrex_core.models.order import Order
from quantrex_core.order import OrderManagementSystem
from quantrex_core.position.manager import PositionManager
from quantrex_backtest.core.strategy_context import BacktestStrategyContext

logger = get_logger(__name__)


class BacktestPortfolioContext(PortfolioContext):
    """Backtest implementation of PortfolioContext.

    Composes per-symbol BacktestStrategyContext instances and adds portfolio-level state tracking.
    Each symbol gets its own strategy context with its own data slice for correct multi-timeframe dispatch.
    
    Supports both single-symbol and multi-symbol data formats:
    - Single-symbol: {timeframe: list} (from SingleInstrumentExecution)
    - Multi-symbol: {symbol: {timeframe: list}} (from SequentialMultiExecution/ParallelMultiExecution)
    """

    def __init__(
        self,
        position_manager: PositionManager,
        oms: OrderManagementSystem,
        current_time: datetime,
        instruments: List[str],
        initial_cash: float = 1_000_000.0,
        margin_requirement: float = 1.0,
        raw_data_by_timeframe: Optional[Dict[str, Dict[str, List[Dict]]]] = None,
        indicators_by_timeframe: Optional[Dict[str, Dict[str, List[Dict]]]] = None,
        base_timeframe: str = "1M",
        origin_time: Optional[datetime] = None,
    ) -> None:
        # Create per-symbol strategy contexts
        self._contexts: Dict[str, BacktestStrategyContext] = {}
        self._current_symbol: str = ""
        
        # Detect data format: single-symbol {timeframe: list} vs multi-symbol {symbol: {timeframe: list}}
        is_multi_symbol = False
        if raw_data_by_timeframe:
            # Check if first key is a symbol (multi-symbol) or timeframe (single-symbol)
            first_key = next(iter(raw_data_by_timeframe))
            # If the value is a dict with timeframe-like keys, it's multi-symbol
            if isinstance(raw_data_by_timeframe[first_key], dict):
                first_inner_key = next(iter(raw_data_by_timeframe[first_key]))
                # Timeframe keys typically contain letters like M, H, D
                if any(c in first_inner_key for c in ['M', 'H', 'D', 'W']):
                    is_multi_symbol = True
        
        for symbol in instruments:
            if is_multi_symbol:
                # Multi-symbol format: extract symbol's data slice
                symbol_raw_data = raw_data_by_timeframe.get(symbol, {}) if raw_data_by_timeframe else {}
                symbol_indicators = indicators_by_timeframe.get(symbol, {}) if indicators_by_timeframe else {}
            else:
                # Single-symbol format: use the entire data for this symbol
                symbol_raw_data = raw_data_by_timeframe or {}
                symbol_indicators = indicators_by_timeframe or {}
            
            ctx = BacktestStrategyContext(
                position_manager=position_manager,
                oms=oms,
                current_time=current_time,
                raw_data_by_timeframe=symbol_raw_data,
                indicators_by_timeframe=symbol_indicators,
                base_timeframe=base_timeframe,
                origin_time=origin_time if origin_time else None,
            )
            # Set symbol and datetime format for this context
            # We need the adapter's datetime_format - get it from the first timeframe's data
            datetime_format = "%Y%m%d %H:%M"  # default
            if symbol_raw_data:
                for tf_data in symbol_raw_data.values():
                    if tf_data and isinstance(tf_data[0].get("datetime"), str):
                        # Infer format from first row
                        dt_str = tf_data[0]["datetime"]
                        # Check for ISO-like format with dashes FIRST (more specific)
                        if "-" in dt_str and ":" in dt_str and dt_str.count("-") >= 2:
                            datetime_format = "%Y-%m-%d %H:%M:%S"
                        elif " " in dt_str and ":" in dt_str:
                            datetime_format = "%Y%m%d %H:%M"
                        break
            ctx.set_symbol_and_format(symbol, datetime_format)
            self._contexts[symbol] = ctx

        # Portfolio state
        self._instruments = instruments
        self._initial_cash = initial_cash
        self._cash = initial_cash
        self._margin_requirement = margin_requirement
        self._realized_pnl = 0.0

        # Track position values for equity calculation
        self._position_values: Dict[str, float] = {}

    def _get_current_context(self) -> BacktestStrategyContext:
        """Get the strategy context for the current symbol."""
        if not self._current_symbol:
            # Fallback to first instrument if no current symbol set
            self._current_symbol = self._instruments[0] if self._instruments else ""
        return self._contexts.get(self._current_symbol)

    # Delegate to strategy context for order/position operations
    def submit_order(self, symbol: str, side: OrderSide, quantity: float,
                     order_type: OrderType = OrderType.MARKET) -> Order:
        """Submit order with portfolio-level margin checks."""
        # Check margin availability before submitting
        if not self._check_margin(symbol, side, quantity):
            logger.warning("Margin check failed for %s %s %s", symbol, side, quantity)
            rejected = Order(
                id="0",
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                status=OrderStatus.REJECTED,
                timestamp=self.current_time,
            )
            return rejected

        # Check if we have a current candle (required for order submission)
        ctx = self._contexts.get(symbol)
        if ctx is None or ctx._current_candle is None:
            logger.warning("Cannot submit order: no current candle available for %s", symbol)
            rejected = Order(
                id="0",
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                status=OrderStatus.REJECTED,
                timestamp=self.current_time,
            )
            return rejected

        return ctx.submit_order(symbol, side, quantity, order_type)

    def get_position(self, symbol: str) -> Position:
        ctx = self._contexts.get(symbol)
        if ctx is None:
            # Return empty position if context doesn't exist
            from quantrex_core.models.position import Position
            return Position(symbol=symbol, quantity=0.0, entry_price=0.0)
        return ctx.get_position(symbol)

    @property
    def current_time(self) -> datetime:
        # All contexts share the same current_time (updated via update_time)
        ctx = self._get_current_context()
        return ctx.current_time if ctx else datetime.min

    @property
    def history(self):
        ctx = self._get_current_context()
        return ctx.history if ctx else ()

    def timeframe_history(self, interval: str):
        ctx = self._get_current_context()
        return ctx.timeframe_history(interval) if ctx else ()

    def update_time(self, timestamp: datetime) -> None:
        # Update time for all contexts
        for ctx in self._contexts.values():
            ctx.update_time(timestamp)

    def update_candle(self, candle: Candle) -> None:
        # Update current symbol and delegate to that symbol's context
        self._current_symbol = candle.symbol
        ctx = self._contexts.get(candle.symbol)
        if ctx:
            ctx.update_candle(candle)

    def record_candle(self, candle: Candle) -> None:
        # Update current symbol and delegate to that symbol's context
        self._current_symbol = candle.symbol
        ctx = self._contexts.get(candle.symbol)
        if ctx:
            ctx.record_candle(candle)
        # Update position values after recording candle
        self._update_position_values(candle)

    def reset(self) -> None:
        for ctx in self._contexts.values():
            ctx.reset()
        self._cash = self._initial_cash
        self._realized_pnl = 0.0
        self._position_values.clear()
        self._current_symbol = ""

    # PortfolioContext interface
    @property
    def cash(self) -> float:
        return self._cash

    @property
    def equity(self) -> float:
        return self._cash + sum(self._position_values.values())

    @property
    def margin_used(self) -> float:
        used = 0.0
        for symbol in self._instruments:
            pos = self.get_position(symbol)
            if pos.quantity != 0:
                value = abs(pos.quantity) * self._position_values.get(symbol, pos.entry_price)
                used += value / self._margin_requirement
        return used

    @property
    def margin_available(self) -> float:
        return self.equity - self.margin_used

    @property
    def positions(self) -> Dict[str, Position]:
        return {symbol: self.get_position(symbol) for symbol in self._instruments}

    @property
    def unrealized_pnl(self) -> float:
        pnl = 0.0
        for symbol in self._instruments:
            pos = self.get_position(symbol)
            if pos.quantity != 0:
                current_price = self._position_values.get(symbol, pos.entry_price)
                if pos.position_side.value == "LONG":
                    pnl += (current_price - pos.entry_price) * pos.quantity
                else:
                    pnl += (pos.entry_price - current_price) * abs(pos.quantity)
        return pnl

    @property
    def realized_pnl(self) -> float:
        return self._realized_pnl

    def _check_margin(self, symbol: str, _side: OrderSide, quantity: float) -> bool:
        """Check if order would exceed available margin."""
        # Simplified margin check - in production would be more sophisticated
        current_price = self._position_values.get(symbol, 0.0)
        if current_price == 0.0:
            # No price yet, allow order
            return True

        order_value = quantity * current_price
        required_margin = order_value / self._margin_requirement

        return required_margin <= self.margin_available

    def _update_position_values(self, candle: Candle) -> None:
        """Update position values based on current candle."""
        self._position_values[candle.symbol] = candle.close

    def _update_realized_pnl(self, trade_pnl: float) -> None:
        """Update realized P&L from closed trades."""
        self._realized_pnl += trade_pnl
        self._cash += trade_pnl

    # Expose strategy context for direct access if needed
    @property
    def strategy_context(self) -> BacktestStrategyContext:
        return self._get_current_context()

    # PortfolioContext is implemented by this class, so portfolio returns self
    @property
    def portfolio(self) -> 'PortfolioContext':
        """Return self as the portfolio context."""
        return self