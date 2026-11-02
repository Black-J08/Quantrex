"""Tests for the Shoonya normalizer."""

from __future__ import annotations

from decimal import Decimal

import pytest

from quantrex.core.data.exceptions.exceptions import NormalizationError
from quantrex.core.data.normalization.shoonya import ShoonyaNormalizer
from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit

# Shoonya TPSeries intraday response: flat list of candle dicts.
TP_SERIES_RESPONSE = [
    {
        "time": "07-12-2022 09:15:00",
        "into": "255.00",
        "inth": "255.65",
        "intl": "254.65",
        "intc": "255.65",
        "intv": "146",
        "v": "146",
        "oi": "0",
    },
    {
        "time": "07-12-2022 09:16:00",
        "into": "255.65",
        "inth": "256.00",
        "intl": "255.50",
        "intc": "255.90",
        "intv": "200",
        "v": "200",
        "oi": "0",
    },
]

# Shoonya EODChartData daily response: flat list of candle dicts.
EOD_RESPONSE = [
    {
        "time": "05-DEC-2022",
        "into": "2145.00",
        "inth": "2168.90",
        "intl": "2130.25",
        "intc": "2160.10",
        "v": "412300",
        "oi": "0",
    },
]


class TestShoonyaNormalizer:
    """Tests for ShoonyaNormalizer."""

    def test_normalize_tp_series_success(self) -> None:
        """Test successful normalization of TPSeries intraday response."""
        normalizer = ShoonyaNormalizer()

        candles = normalizer.normalize_candles(
            TP_SERIES_RESPONSE,
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        )

        assert len(candles) == 2
        assert all(isinstance(c, OHLCVCandle) for c in candles)
        assert candles[0].symbol == "NSE:INFY"
        assert candles[0].open == Decimal("255.00")
        assert candles[0].high == Decimal("255.65")
        assert candles[0].low == Decimal("254.65")
        assert candles[0].close == Decimal("255.65")
        assert candles[0].volume == Decimal(146)

    def test_normalize_eod_chart_data_success(self) -> None:
        """Test successful normalization of EODChartData daily response."""
        normalizer = ShoonyaNormalizer()

        candles = normalizer.normalize_candles(
            EOD_RESPONSE,
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.DAY),
        )

        assert len(candles) == 1
        assert candles[0].symbol == "NSE:INFY"
        assert candles[0].open == Decimal("2145.00")
        assert candles[0].high == Decimal("2168.90")
        assert candles[0].low == Decimal("2130.25")
        assert candles[0].close == Decimal("2160.10")
        assert candles[0].volume == Decimal(412300)

    def test_normalize_preserves_bar_timestamp_intraday(self) -> None:
        """Test that the vendor bar time reaches the canonical candle (intraday)."""
        normalizer = ShoonyaNormalizer()

        candles = normalizer.normalize_candles(
            TP_SERIES_RESPONSE,
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        )

        assert candles[0].timestamp.isoformat() == "2022-12-07T09:15:00+05:30"
        assert candles[1].timestamp.isoformat() == "2022-12-07T09:16:00+05:30"

    def test_normalize_preserves_bar_timestamp_daily(self) -> None:
        """Test that the vendor bar time reaches the canonical candle (daily)."""
        normalizer = ShoonyaNormalizer()

        candles = normalizer.normalize_candles(
            EOD_RESPONSE,
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.DAY),
        )

        assert candles[0].timestamp.isoformat() == "2022-12-05T00:00:00+05:30"

    def test_normalize_empty_response(self) -> None:
        """Test that an empty response returns an empty list."""
        normalizer = ShoonyaNormalizer()

        candles = normalizer.normalize_candles(
            [],
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        )

        assert candles == []

    def test_normalize_skips_invalid_candle(self) -> None:
        """Test that an invalid candle is skipped with a warning."""
        normalizer = ShoonyaNormalizer()

        raw_response = [
            {
                "time": "07-12-2022 09:15:00",
                "into": "255.00",
                "inth": "255.65",
                "intl": "254.65",
                "intc": "255.65",
                "intv": "146",
            },
            # Missing required fields - should be skipped.
            {"time": "bad"},
        ]

        candles = normalizer.normalize_candles(
            raw_response,
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        )

        assert len(candles) == 1

    def test_normalize_invalid_response_type(self) -> None:
        """Test that an invalid response type raises NormalizationError."""
        normalizer = ShoonyaNormalizer()

        with pytest.raises(NormalizationError, match="Expected list or dict"):
            normalizer.normalize_candles(
                "not a list or dict",
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
            )

    def test_normalize_dict_wrapped_response(self) -> None:
        """Test normalization of a dict-wrapped response."""
        normalizer = ShoonyaNormalizer()

        raw_response = {"data": TP_SERIES_RESPONSE}

        candles = normalizer.normalize_candles(
            raw_response,
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        )

        assert len(candles) == 2

    def test_normalize_volume_uses_v_field(self) -> None:
        """Test that volume uses the ``v`` field as the primary volume source."""
        normalizer = ShoonyaNormalizer()

        raw_response = [
            {
                "time": "07-12-2022 09:15:00",
                "into": "255.00",
                "inth": "255.65",
                "intl": "254.65",
                "intc": "255.65",
                "v": "146",
            },
        ]

        candles = normalizer.normalize_candles(
            raw_response,
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        )

        assert len(candles) == 1
        assert candles[0].volume == Decimal(146)

    def test_normalize_uses_positive_volume_when_intv_negative(self) -> None:
        """Regression test: Shoonya may return negative ``intv`` while ``v`` holds the correct volume.

        The normalizer must prefer ``v`` over ``intv`` so that valid candles
        are not rejected by OHLCVCandle's non-negative volume validation.
        """
        normalizer = ShoonyaNormalizer()

        raw_response = [
            {
                "time": "07-12-2022 09:15:00",
                "into": "255.00",
                "inth": "255.65",
                "intl": "254.65",
                "intc": "255.65",
                "intv": "-697",
                "v": "535811",
            },
        ]

        candles = normalizer.normalize_candles(
            raw_response,
            symbol="NSE:INFY",
            timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        )

        assert len(candles) == 1
        assert candles[0].volume == Decimal(535811)
