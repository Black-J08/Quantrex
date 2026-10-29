"""Tests for the abstract Normalizer base class."""

from __future__ import annotations

from typing import Any

import pytest

from quantrex.core.data.normalization.base import Normalizer
from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit


class ConcreteNormalizer(Normalizer):
    """Concrete implementation for testing the abstract base class."""

    def normalize_candles(
        self,
        raw_response: Any,
        symbol: str,
        timeframe: Timeframe,
    ) -> list[OHLCVCandle]:
        return []


class TestNormalizer:
    """Tests for Normalizer abstract base class."""

    def test_cannot_instantiate_abstract(self) -> None:
        """Test that the abstract class cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Normalizer()  # type: ignore[abstract]

    def test_concrete_implementation(self) -> None:
        """Test that a concrete implementation can be instantiated."""
        normalizer = ConcreteNormalizer()
        assert isinstance(normalizer, Normalizer)

    def test_normalize_candles_returns_list(self) -> None:
        """Test that normalize_candles returns a list of candles."""
        normalizer = ConcreteNormalizer()
        candles = normalizer.normalize_candles(
            raw_response={},
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        )
        assert isinstance(candles, list)
