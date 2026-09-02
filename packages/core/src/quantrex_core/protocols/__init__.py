"""Quantrex Core Protocols.

Structural protocols for cross-package data-source contracts. Engine
internals (e.g. :class:`quantrex_core.strategy.context.StrategyContext`)
are defined as ABCs alongside their primary collaborators rather than
here, so this module only contains Protocols with genuine third-party
duck-typing use cases.
"""

from .data_provider import DataProvider
from .data_adapter import DataAdapter

__all__ = ["DataProvider", "DataAdapter"]