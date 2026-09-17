"""Portfolio context interface for Quantrex."""

from abc import ABC, abstractmethod
from typing import Dict

from ..models.position import Position


class PortfolioContext(ABC):
    """Abstract portfolio-level view interface.

    Composed onto StrategyContext via the ``portfolio`` property.
    Concrete implementations provided by execution environments
    (BacktestPortfolioContext, LivePortfolioContext).
    """

    @property
    @abstractmethod
    def cash(self) -> float:
        """Available cash balance."""
        ...

    @property
    @abstractmethod
    def equity(self) -> float:
        """Total portfolio value (cash + position market values)."""
        ...

    @property
    @abstractmethod
    def margin_used(self) -> float:
        """Margin currently allocated to open positions."""
        ...

    @property
    @abstractmethod
    def margin_available(self) -> float:
        """Margin available for new positions."""
        ...

    @property
    @abstractmethod
    def positions(self) -> Dict[str, Position]:
        """All open positions keyed by symbol."""
        ...

    @property
    @abstractmethod
    def unrealized_pnl(self) -> float:
        """Unrealized P&L across all open positions."""
        ...

    @property
    @abstractmethod
    def realized_pnl(self) -> float:
        """Realized P&L from closed trades."""
        ...

    @abstractmethod
    def get_position(self, symbol: str) -> Position:
        """Get position for a specific symbol.

        Returns a zero position if no position exists for the symbol.
        """
        ...


class EmptyPortfolioContext(PortfolioContext):
    """Default empty portfolio context for single-instrument backtests."""

    @property
    def cash(self) -> float:
        return 0.0

    @property
    def equity(self) -> float:
        return 0.0

    @property
    def margin_used(self) -> float:
        return 0.0

    @property
    def margin_available(self) -> float:
        return 0.0

    @property
    def positions(self) -> Dict[str, Position]:
        return {}

    @property
    def unrealized_pnl(self) -> float:
        return 0.0

    @property
    def realized_pnl(self) -> float:
        return 0.0

    def get_position(self, symbol: str) -> Position:
        return Position.zero(symbol)