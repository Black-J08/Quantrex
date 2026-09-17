"""Portfolio position sizing protocol for Quantrex."""

from typing import Dict, Protocol

from ..models.portfolio import PortfolioState


class PositionSizer(Protocol):
    """Protocol for portfolio-level position sizing.

    Implementations compute target weights for each symbol based on
    the current portfolio state and strategy signals. The sum of
    returned weights should equal 1.0 (fully invested) or less
    (cash reserve).
    """

    def compute_target_weights(
        self,
        portfolio: PortfolioState,
        signals: Dict[str, float],
    ) -> Dict[str, float]:
        """Return target weight per symbol (sum <= 1.0).

        Args:
            portfolio: Current portfolio state (cash, equity, positions).
            signals: Strategy signals per symbol (e.g., 1.0 = long, -1.0 = short, 0 = flat).

        Returns:
            Dictionary mapping symbol to target portfolio weight.
            Sum of weights should be <= 1.0.
        """
        ...