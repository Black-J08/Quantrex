"""Backtest engine exceptions."""


class BacktestError(Exception):
    """Base exception for backtest engine errors."""
    pass


class ProviderError(BacktestError):
    """Raised when a data provider/feeder is invalid or missing."""
    pass