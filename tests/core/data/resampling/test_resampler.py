"""Tests for the Resampler."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from quantrex.core.data.resampling.exceptions import (
    InvalidDerivedTimeframeError,
    ResamplingError,
)
from quantrex.core.data.resampling.resampler import Resampler
from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit
from quantrex.core.models.timezone import IST


def _make_1m_candle(
    minute_offset: int,
    symbol: str = "NSE:INFY",
    open_price: float = 1500.0,
    high: float = 1510.0,
    low: float = 1495.0,
    close: float = 1505.0,
    volume: float = 100000.0,
) -> OHLCVCandle:
    """Create a 1-minute candle at 9:15 AM IST + offset minutes on a weekday."""
    base = datetime(2024, 1, 15, 9, 15, tzinfo=IST)  # Monday
    return OHLCVCandle(
        symbol=symbol,
        timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
        timestamp=base + timedelta(minutes=minute_offset),
        open=Decimal(str(open_price)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
    )


class TestResampler:
    """Tests for Resampler."""

    def test_resample_1m_to_5m(self) -> None:
        """Five 1-minute candles aggregate into one 5-minute candle."""
        resampler = Resampler()
        candles = [
            _make_1m_candle(0, open_price=1500.0, high=1510.0, low=1495.0, close=1505.0, volume=100000),
            _make_1m_candle(1, open_price=1505.0, high=1515.0, low=1500.0, close=1510.0, volume=80000),
            _make_1m_candle(2, open_price=1510.0, high=1520.0, low=1505.0, close=1515.0, volume=90000),
            _make_1m_candle(3, open_price=1515.0, high=1525.0, low=1510.0, close=1520.0, volume=70000),
            _make_1m_candle(4, open_price=1520.0, high=1530.0, low=1515.0, close=1525.0, volume=60000),
        ]

        result = resampler.resample(
            candles, Timeframe(value=5, unit=TimeframeUnit.MINUTE)
        )

        assert len(result) == 1
        assert result[0].timeframe == Timeframe(value=5, unit=TimeframeUnit.MINUTE)
        assert result[0].open == Decimal("1500.0")
        assert result[0].high == Decimal("1530.0")
        assert result[0].low == Decimal("1495.0")
        assert result[0].close == Decimal("1525.0")
        assert result[0].volume == Decimal(400000)

    def test_resample_1m_to_45m(self) -> None:
        """Forty-five 1-minute candles aggregate into one 45-minute candle."""
        resampler = Resampler()
        candles = [
            _make_1m_candle(i, open_price=1500.0 + i, high=1510.0 + i, low=1495.0 + i, close=1505.0 + i, volume=100000 + i * 1000)
            for i in range(45)
        ]

        result = resampler.resample(
            candles, Timeframe(value=45, unit=TimeframeUnit.MINUTE)
        )

        assert len(result) == 1
        assert result[0].timeframe == Timeframe(value=45, unit=TimeframeUnit.MINUTE)
        assert result[0].open == Decimal("1500.0")
        assert result[0].high == Decimal("1554.0")
        assert result[0].low == Decimal("1495.0")
        assert result[0].close == Decimal("1549.0")
        # Sum of volumes: 100000 + 101000 + ... + 144000
        expected_volume = sum(100000 + i * 1000 for i in range(45))
        assert result[0].volume == Decimal(str(expected_volume))

    def test_resample_1m_to_1h(self) -> None:
        """Sixty 1-minute candles aggregate into one 1-hour candle."""
        resampler = Resampler()
        candles = [
            _make_1m_candle(i, open_price=1500.0, high=1510.0, low=1495.0, close=1505.0, volume=100000)
            for i in range(60)
        ]

        result = resampler.resample(
            candles, Timeframe(value=1, unit=TimeframeUnit.HOUR)
        )

        assert len(result) == 1
        assert result[0].timeframe == Timeframe(value=1, unit=TimeframeUnit.HOUR)
        assert result[0].open == Decimal("1500.0")
        assert result[0].high == Decimal("1510.0")
        assert result[0].low == Decimal("1495.0")
        assert result[0].close == Decimal("1505.0")
        assert result[0].volume == Decimal(6000000)

    def test_resample_multiple_bars(self) -> None:
        """100 one-minute candles produce multiple 15-minute bars."""
        resampler = Resampler()
        candles = [
            _make_1m_candle(i, open_price=1500.0, high=1510.0, low=1495.0, close=1505.0, volume=100000)
            for i in range(100)
        ]

        result = resampler.resample(
            candles, Timeframe(value=15, unit=TimeframeUnit.MINUTE)
        )

        # 100 minutes / 15 minutes per bar = 6 full bars + 10 minutes remainder
        # The last partial bin (10 minutes) still produces a bar
        assert len(result) == 7
        for bar in result:
            assert bar.timeframe == Timeframe(value=15, unit=TimeframeUnit.MINUTE)
            assert bar.open == Decimal("1500.0")
            assert bar.high == Decimal("1510.0")
            assert bar.low == Decimal("1495.0")
            assert bar.close == Decimal("1505.0")

    def test_ohlc_relationships_preserved(self) -> None:
        """Every resampled bar satisfies OHLC relationships."""
        resampler = Resampler()
        candles = [
            _make_1m_candle(i, open_price=1500.0 + i * 0.5, high=1510.0 + i, low=1495.0 - i * 0.5, close=1505.0 + i * 0.3, volume=100000)
            for i in range(30)
        ]

        result = resampler.resample(
            candles, Timeframe(value=10, unit=TimeframeUnit.MINUTE)
        )

        for bar in result:
            assert bar.high >= bar.open
            assert bar.high >= bar.close
            assert bar.low <= bar.open
            assert bar.low <= bar.close
            assert bar.high >= bar.low

    def test_empty_input_raises(self) -> None:
        """Resampling an empty list raises ResamplingError."""
        resampler = Resampler()

        with pytest.raises(ResamplingError, match="Cannot resample empty candle list"):
            resampler.resample(
                [], Timeframe(value=5, unit=TimeframeUnit.MINUTE)
            )

    def test_mixed_source_timeframes_raises(self) -> None:
        """Candles with different source timeframes raise ResamplingError."""
        resampler = Resampler()
        candles = [
            _make_1m_candle(0),
            OHLCVCandle(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=5, unit=TimeframeUnit.MINUTE),
                timestamp=datetime(2024, 1, 15, 9, 15, tzinfo=IST),
                open=Decimal("1500.0"),
                high=Decimal("1510.0"),
                low=Decimal("1495.0"),
                close=Decimal("1505.0"),
                volume=Decimal(100000),
            ),
        ]

        with pytest.raises(ResamplingError, match="All candles must have the same timeframe"):
            resampler.resample(
                candles, Timeframe(value=10, unit=TimeframeUnit.MINUTE)
            )

    def test_non_derivable_timeframe_raises(self) -> None:
        """A timeframe not derivable from 1m raises InvalidDerivedTimeframeError."""
        resampler = Resampler()
        candles = [_make_1m_candle(0)]

        # 30 seconds cannot be derived from 1 minute
        with pytest.raises(InvalidDerivedTimeframeError):
            resampler.resample(
                candles, Timeframe(value=30, unit=TimeframeUnit.SECOND)
            )

    def test_same_timeframe_passthrough(self) -> None:
        """Resampling 1m to 1m returns the same candles."""
        resampler = Resampler()
        candles = [_make_1m_candle(0), _make_1m_candle(1)]

        result = resampler.resample(
            candles, Timeframe(value=1, unit=TimeframeUnit.MINUTE)
        )

        assert len(result) == 2
        assert result[0].symbol == candles[0].symbol
        assert result[0].timeframe == candles[0].timeframe
        assert result[0].timestamp == candles[0].timestamp
        assert result[0].open == candles[0].open
        assert result[0].high == candles[0].high
        assert result[0].low == candles[0].low
        assert result[0].close == candles[0].close
        assert result[0].volume == candles[0].volume
        assert result[1].symbol == candles[1].symbol
        assert result[1].timeframe == candles[1].timeframe
        assert result[1].timestamp == candles[1].timestamp
        assert result[1].open == candles[1].open
        assert result[1].high == candles[1].high
        assert result[1].low == candles[1].low
        assert result[1].close == candles[1].close
        assert result[1].volume == candles[1].volume

    def test_nse_session_alignment(self) -> None:
        """Resampled bars align to NSE market open (9:15 IST)."""
        resampler = Resampler()
        # Create 1m candles starting at 9:15 IST on a Monday
        candles = [
            _make_1m_candle(i, open_price=1500.0, high=1510.0, low=1495.0, close=1505.0, volume=100000)
            for i in range(90)
        ]

        result = resampler.resample(
            candles, Timeframe(value=45, unit=TimeframeUnit.MINUTE)
        )

        assert len(result) == 2
        # First bar starts at 9:15 IST
        assert result[0].timestamp == datetime(2024, 1, 15, 9, 15, tzinfo=IST)
        # Second bar starts at 10:00 IST (45 minutes later)
        assert result[1].timestamp == datetime(2024, 1, 15, 10, 0, tzinfo=IST)

    def test_weekend_candles_filtered(self) -> None:
        """Candles on weekends are excluded from resampling."""
        resampler = Resampler()
        # Saturday 2024-01-20 and Sunday 2024-01-21
        saturday = datetime(2024, 1, 20, 10, 0, tzinfo=IST)
        sunday = datetime(2024, 1, 21, 10, 0, tzinfo=IST)
        monday = datetime(2024, 1, 22, 10, 0, tzinfo=IST)

        candles = [
            OHLCVCandle(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                timestamp=saturday,
                open=Decimal("1500.0"),
                high=Decimal("1510.0"),
                low=Decimal("1495.0"),
                close=Decimal("1505.0"),
                volume=Decimal(100000),
            ),
            OHLCVCandle(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                timestamp=sunday,
                open=Decimal("1500.0"),
                high=Decimal("1510.0"),
                low=Decimal("1495.0"),
                close=Decimal("1505.0"),
                volume=Decimal(100000),
            ),
            OHLCVCandle(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                timestamp=monday,
                open=Decimal("1500.0"),
                high=Decimal("1510.0"),
                low=Decimal("1495.0"),
                close=Decimal("1505.0"),
                volume=Decimal(100000),
            ),
        ]

        result = resampler.resample(
            candles, Timeframe(value=5, unit=TimeframeUnit.MINUTE)
        )

        # Only Monday's candle should produce a bar
        assert len(result) == 1
        assert result[0].timestamp == monday

    def test_custom_interval_45m_boundary_alignment(self) -> None:
        """45-minute bars align to NSE open (9:15, 10:00, 10:45, ...)."""
        resampler = Resampler()
        # 3 hours of 1m candles from 9:15 to 12:14 IST on Monday
        candles = [
            _make_1m_candle(i, open_price=1500.0, high=1510.0, low=1495.0, close=1505.0, volume=100000)
            for i in range(180)
        ]

        result = resampler.resample(
            candles, Timeframe(value=45, unit=TimeframeUnit.MINUTE)
        )

        # 180 minutes / 45 minutes = 4 bars
        assert len(result) == 4
        expected_starts = [
            datetime(2024, 1, 15, 9, 15, tzinfo=IST),
            datetime(2024, 1, 15, 10, 0, tzinfo=IST),
            datetime(2024, 1, 15, 10, 45, tzinfo=IST),
            datetime(2024, 1, 15, 11, 30, tzinfo=IST),
        ]
        for bar, expected_start in zip(result, expected_starts):
            assert bar.timestamp == expected_start

    def test_incomplete_final_bin_produces_bar(self) -> None:
        """A partial final bin (fewer candles than the target interval) still produces a bar."""
        resampler = Resampler()
        # 10 one-minute candles for a 15-minute target: one full bar + one partial
        candles = [
            _make_1m_candle(i, open_price=1500.0, high=1510.0, low=1495.0, close=1505.0, volume=100000)
            for i in range(10)
        ]

        result = resampler.resample(
            candles, Timeframe(value=15, unit=TimeframeUnit.MINUTE)
        )

        assert len(result) == 1
        assert result[0].timeframe == Timeframe(value=15, unit=TimeframeUnit.MINUTE)
        assert result[0].volume == Decimal(1000000)

    def test_missing_data_gap(self) -> None:
        """A gap in source data does not break resampling; bins with no data are dropped."""
        resampler = Resampler()
        candles = [
            _make_1m_candle(0, open_price=1500.0, high=1510.0, low=1495.0, close=1505.0, volume=100000),
            _make_1m_candle(1, open_price=1505.0, high=1515.0, low=1500.0, close=1510.0, volume=80000),
            # Gap: minutes 2-9 missing
            _make_1m_candle(10, open_price=1520.0, high=1530.0, low=1515.0, close=1525.0, volume=90000),
        ]

        result = resampler.resample(
            candles, Timeframe(value=5, unit=TimeframeUnit.MINUTE)
        )

        # Two bins: 9:15-9:19 (2 candles) and 9:25-9:29 (1 candle)
        assert len(result) == 2
        assert result[0].open == Decimal("1500.0")
        assert result[0].high == Decimal("1515.0")
        assert result[0].low == Decimal("1495.0")
        assert result[0].close == Decimal("1510.0")
        assert result[0].volume == Decimal(180000)
        assert result[1].open == Decimal("1520.0")
        assert result[1].high == Decimal("1530.0")
        assert result[1].low == Decimal("1515.0")
        assert result[1].close == Decimal("1525.0")
        assert result[1].volume == Decimal(90000)

    def test_single_candle_resample(self) -> None:
        """A single source candle resamples to a single target candle."""
        resampler = Resampler()
        candles = [_make_1m_candle(0)]

        result = resampler.resample(
            candles, Timeframe(value=5, unit=TimeframeUnit.MINUTE)
        )

        assert len(result) == 1
        assert result[0].open == Decimal("1500.0")
        assert result[0].high == Decimal("1510.0")
        assert result[0].low == Decimal("1495.0")
        assert result[0].close == Decimal("1505.0")
        assert result[0].volume == Decimal(100000)

    def test_daily_to_weekly_resampling(self) -> None:
        """Daily candles resample to weekly candles."""
        resampler = Resampler()
        # 5 daily candles (Monday-Friday)
        base = datetime(2024, 1, 15, 9, 15, tzinfo=IST)  # Monday
        candles = []
        for i in range(5):
            candles.append(
                OHLCVCandle(
                    symbol="NSE:INFY",
                    timeframe=Timeframe(value=1, unit=TimeframeUnit.DAY),
                    timestamp=base + timedelta(days=i),
                    open=Decimal("1500.0"),
                    high=Decimal("1510.0"),
                    low=Decimal("1495.0"),
                    close=Decimal("1505.0"),
                    volume=Decimal(1000000),
                )
            )

        result = resampler.resample(
            candles, Timeframe(value=1, unit=TimeframeUnit.WEEK)
        )

        assert len(result) == 1
        assert result[0].timeframe == Timeframe(value=1, unit=TimeframeUnit.WEEK)
        assert result[0].open == Decimal("1500.0")
        assert result[0].high == Decimal("1510.0")
        assert result[0].low == Decimal("1495.0")
        assert result[0].close == Decimal("1505.0")
        assert result[0].volume == Decimal(5000000)

    def test_daily_to_monthly_resampling(self) -> None:
        """Daily candles resample to monthly candles."""
        resampler = Resampler()
        base = datetime(2024, 1, 15, 9, 15, tzinfo=IST)
        candles = []
        for i in range(20):
            candles.append(
                OHLCVCandle(
                    symbol="NSE:INFY",
                    timeframe=Timeframe(value=1, unit=TimeframeUnit.DAY),
                    timestamp=base + timedelta(days=i),
                    open=Decimal("1500.0"),
                    high=Decimal("1510.0"),
                    low=Decimal("1495.0"),
                    close=Decimal("1505.0"),
                    volume=Decimal(1000000),
                )
            )

        result = resampler.resample(
            candles, Timeframe(value=1, unit=TimeframeUnit.MONTH)
        )

        # 20 days from Jan 15 to Feb 3 span two calendar months
        assert len(result) == 2
        assert result[0].timeframe == Timeframe(value=1, unit=TimeframeUnit.MONTH)
        # Bin 1: Jan 15-30 (16 days), Bin 2: Jan 31-Feb 3 (4 days)
        assert result[0].volume == Decimal(16000000)
        assert result[1].volume == Decimal(4000000)

    def test_session_boundary_excludes_pre_market(self) -> None:
        """Candles before market open (9:15 IST) are excluded from resampling."""
        resampler = Resampler()
        pre_market = datetime(2024, 1, 15, 9, 0, tzinfo=IST)  # 15 min before open
        market_open = datetime(2024, 1, 15, 9, 15, tzinfo=IST)

        candles = [
            OHLCVCandle(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                timestamp=pre_market,
                open=Decimal("1490.0"),
                high=Decimal("1495.0"),
                low=Decimal("1485.0"),
                close=Decimal("1490.0"),
                volume=Decimal(50000),
            ),
            _make_1m_candle(0),
        ]

        result = resampler.resample(
            candles, Timeframe(value=5, unit=TimeframeUnit.MINUTE)
        )

        # Pre-market candle excluded; only the 9:15 candle produces a bar
        assert len(result) == 1
        assert result[0].timestamp == market_open
        assert result[0].open == Decimal("1500.0")

    def test_session_boundary_excludes_post_market(self) -> None:
        """Candles after market close (3:30 PM IST) are excluded from resampling."""
        resampler = Resampler()
        market_close = datetime(2024, 1, 15, 15, 30, tzinfo=IST)
        post_market = datetime(2024, 1, 15, 15, 31, tzinfo=IST)

        candles = [
            _make_1m_candle(375, open_price=1500.0, high=1510.0, low=1495.0, close=1505.0, volume=100000),  # 15:30
            OHLCVCandle(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.MINUTE),
                timestamp=post_market,
                open=Decimal("1510.0"),
                high=Decimal("1515.0"),
                low=Decimal("1505.0"),
                close=Decimal("1510.0"),
                volume=Decimal(50000),
            ),
        ]

        result = resampler.resample(
            candles, Timeframe(value=5, unit=TimeframeUnit.MINUTE)
        )

        # Post-market candle excluded; only the 15:30 candle produces a bar
        assert len(result) == 1
        assert result[0].timestamp == market_close

    def test_different_symbols_raises(self) -> None:
        """Candles for different symbols raise ResamplingError."""
        resampler = Resampler()
        candles = [
            _make_1m_candle(0, symbol="NSE:INFY"),
            _make_1m_candle(0, symbol="NSE:RELIANCE"),
        ]

        with pytest.raises(ResamplingError, match="All candles must have the same symbol"):
            resampler.resample(
                candles, Timeframe(value=5, unit=TimeframeUnit.MINUTE)
            )

    def test_decimal_precision_preserved(self) -> None:
        """Decimal precision is preserved through resampling (within float64 limits)."""
        resampler = Resampler()
        candles = [
            _make_1m_candle(
                0,
                open_price=1500.1234567890123456,
                high=1510.9876543210987654,
                low=1495.1111111111111111,
                close=1505.2222222222222222,
                volume=100000.5,
            ),
            _make_1m_candle(
                1,
                open_price=1505.2222222222222222,
                high=1515.3333333333333333,
                low=1500.1234567890123456,
                close=1510.4444444444444444,
                volume=80000.5,
            ),
        ]

        result = resampler.resample(
            candles, Timeframe(value=5, unit=TimeframeUnit.MINUTE)
        )

        assert len(result) == 1
        # Float64 conversion loses some precision; check approximate equality
        assert abs(result[0].open - Decimal("1500.1234567890124")) < Decimal("0.0000000000001")
        assert abs(result[0].high - Decimal("1515.3333333333333")) < Decimal("0.0000000000001")
        assert abs(result[0].low - Decimal("1495.111111111111")) < Decimal("0.0000000000001")
        assert abs(result[0].close - Decimal("1510.4444444444443")) < Decimal("0.0000000000001")
        assert result[0].volume == Decimal("180001.0")

    def test_2h_from_1m(self) -> None:
        """2-hour bars (120 × 1m) are derivable and resample correctly."""
        resampler = Resampler()
        candles = [
            _make_1m_candle(i, open_price=1500.0, high=1510.0, low=1495.0, close=1505.0, volume=100000)
            for i in range(120)
        ]

        result = resampler.resample(
            candles, Timeframe(value=2, unit=TimeframeUnit.HOUR)
        )

        assert len(result) == 1
        assert result[0].timeframe == Timeframe(value=2, unit=TimeframeUnit.HOUR)
        assert result[0].volume == Decimal(12000000)

    def test_3d_from_1d(self) -> None:
        """3-day bars (3 × 1d) are derivable and resample correctly."""
        resampler = Resampler()
        base = datetime(2024, 1, 15, 9, 15, tzinfo=IST)
        candles = []
        for i in range(3):
            candles.append(
                OHLCVCandle(
                    symbol="NSE:INFY",
                    timeframe=Timeframe(value=1, unit=TimeframeUnit.DAY),
                    timestamp=base + timedelta(days=i),
                    open=Decimal("1500.0"),
                    high=Decimal("1510.0"),
                    low=Decimal("1495.0"),
                    close=Decimal("1505.0"),
                    volume=Decimal(1000000),
                )
            )

        result = resampler.resample(
            candles, Timeframe(value=3, unit=TimeframeUnit.DAY)
        )

        assert len(result) == 1
        assert result[0].timeframe == Timeframe(value=3, unit=TimeframeUnit.DAY)
        assert result[0].volume == Decimal(3000000)

    def test_7m_from_1m(self) -> None:
        """7-minute bars (unusual but valid) are derivable from 1m."""
        resampler = Resampler()
        candles = [
            _make_1m_candle(i, open_price=1500.0, high=1510.0, low=1495.0, close=1505.0, volume=100000)
            for i in range(7)
        ]

        result = resampler.resample(
            candles, Timeframe(value=7, unit=TimeframeUnit.MINUTE)
        )

        # 7 candles span 9:15-9:21; with origin at 9:15, bins are [9:12,9:19) and [9:19,9:26)
        # First bin has 4 candles (9:15-9:18), second bin has 3 candles (9:19-9:21)
        assert len(result) == 2
        assert result[0].timeframe == Timeframe(value=7, unit=TimeframeUnit.MINUTE)
        assert result[0].volume == Decimal(400000)
        assert result[1].volume == Decimal(300000)

    def test_1m_from_5m_raises(self) -> None:
        """Resampling from 5m to 1m (downsampling to lower timeframe) is not supported."""
        resampler = Resampler()
        candles = [
            OHLCVCandle(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=5, unit=TimeframeUnit.MINUTE),
                timestamp=datetime(2024, 1, 15, 9, 15, tzinfo=IST),
                open=Decimal("1500.0"),
                high=Decimal("1510.0"),
                low=Decimal("1495.0"),
                close=Decimal("1505.0"),
                volume=Decimal(500000),
            ),
        ]

        with pytest.raises(InvalidDerivedTimeframeError):
            resampler.resample(
                candles, Timeframe(value=1, unit=TimeframeUnit.MINUTE)
            )

    def test_1m_from_1d_raises(self) -> None:
        """Resampling from 1d to 1m (downsampling to lower timeframe) is not supported."""
        resampler = Resampler()
        candles = [
            OHLCVCandle(
                symbol="NSE:INFY",
                timeframe=Timeframe(value=1, unit=TimeframeUnit.DAY),
                timestamp=datetime(2024, 1, 15, 9, 15, tzinfo=IST),
                open=Decimal("1500.0"),
                high=Decimal("1510.0"),
                low=Decimal("1495.0"),
                close=Decimal("1505.0"),
                volume=Decimal(1000000),
            ),
        ]

        with pytest.raises(InvalidDerivedTimeframeError):
            resampler.resample(
                candles, Timeframe(value=1, unit=TimeframeUnit.MINUTE)
            )
