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
from quantrex_backtest.core.context import BacktestStrategyContext
from quantrex_backtest.core.timeframe import calculate_close_time

logger = get_logger(__name__)


class BacktestPortfolioContext(PortfolioContext):
    """Backtest implementation of PortfolioContext.

    Composes a BacktestStrategyContext and adds portfolio-level state tracking.
    """

    def __init__(
        self,
        position_manager: PositionManager,
        oms: OrderManagementSystem,
        current_time: datetime,
        instruments: List[str],
        initial_cash: float = 1_000_000.0,
        margin_requirement: float = 1.0,
        raw_data_by_timeframe: Optional[Dict[str, List[Dict]]] = None,
        indicators_by_timeframe: Optional[Dict[str, List[Dict]]] = None,
        base_timeframe: str = "1M",
        origin_time: Optional[datetime] = None,
    ) -> None:
        # Create the underlying strategy context
        self._strategy_context = BacktestStrategyContext(
            position_manager=position_manager,
            oms=oms,
            current_time=current_time,
            raw_data_by_timeframe=raw_data_by_timeframe,
            indicators_by_timeframe=indicators_by_timeframe,
            base_timeframe=base_timeframe,
            origin_time=origin_time if origin_time else None,
        )

        # Portfolio state
        self._instruments = instruments
        self._initial_cash = initial_cash
        self._cash = initial_cash
        self._margin_requirement = margin_requirement
        self._realized_pnl = 0.0

        # Track position values for equity calculation
        self._position_values: Dict[str, float] = {}

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
                timestamp=self._strategy_context.current_time,
            )
            return rejected

        # Check if we have a current candle (required for order submission)
        if self._strategy_context._current_candle is None:
            logger.warning("Cannot submit order: no current candle available")
            rejected = Order(
                id="0",
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                status=OrderStatus.REJECTED,
                timestamp=self._strategy_context.current_time,
            )
            return rejected

        return self._strategy_context.submit_order(symbol, side, quantity, order_type)

    def get_position(self, symbol: str) -> Position:
        return self._strategy_context.get_position(symbol)

    @property
    def current_time(self) -> datetime:
        return self._strategy_context.current_time

    @property
    def history(self):
        return self._strategy_context.history

    def timeframe_history(self, interval: str):
        return self._strategy_context.timeframe_history(interval)

    def update_time(self, timestamp: datetime) -> None:
        self._strategy_context.update_time(timestamp)

    def update_candle(self, candle: Candle) -> None:
        self._strategy_context.update_candle(candle)

    def record_candle(self, candle: Candle) -> None:
        self._strategy_context.record_candle(candle)
        # Update position values after recording candle
        self._update_position_values(candle)

    def reset(self) -> None:
        self._strategy_context.reset()
        self._cash = self._initial_cash
        self._realized_pnl = 0.0
        self._position_values.clear()

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

    def _check_margin(self, symbol: str, side: OrderSide, quantity: float) -> bool:
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
        return self._strategy_context

    # PortfolioContext is implemented by this class, so portfolio returns self
    @property
    def portfolio(self) -> 'PortfolioContext':
        """Return self as the portfolio context."""
        return self