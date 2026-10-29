"""Resampler for deriving higher timeframe candles from canonical source data."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]

from quantrex.core.data.resampling.exceptions import (
    InvalidDerivedTimeframeError,
    ResamplingError,
)
from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe, TimeframeUnit
from quantrex.core.models.timezone import IST

# NSE India market session: 9:15 AM – 3:30 PM IST
_NSE_OPEN_HOUR = 9
_NSE_OPEN_MINUTE = 15
_NSE_CLOSE_HOUR = 15
_NSE_CLOSE_MINUTE = 30


class Resampler:
    """Resamples canonical OHLCV candles to higher timeframes.

    Converts 1-minute candles to arbitrary intraday timeframes (e.g., 45m, 1h)
    and 1-day candles to multi-day timeframes (e.g., 1w, 1M) using Pandas
    resampling with OHLC aggregation.

    Bar boundaries are aligned to the NSE India market session
    (9:15 AM – 3:30 PM IST).
    """

    def resample(
        self,
        candles: list[OHLCVCandle],
        target_timeframe: Timeframe,
    ) -> list[OHLCVCandle]:
        """Resample candles to a higher timeframe.

        Args:
            candles: Source candles, all at the same timeframe (1m or 1d).
            target_timeframe: Target timeframe to resample to.

        Returns:
            List of resampled OHLCVCandle objects at the target timeframe.

        Raises:
            ResamplingError: If resampling fails.
            InvalidDerivedTimeframeError: If target cannot be derived from source.
        """
        if not candles:
            raise ResamplingError("Cannot resample empty candle list")

        source_timeframe = candles[0].timeframe
        source_symbol = candles[0].symbol
        if not all(c.timeframe == source_timeframe for c in candles):
            raise ResamplingError("All candles must have the same timeframe")
        if not all(c.symbol == source_symbol for c in candles):
            raise ResamplingError("All candles must have the same symbol")

        if not target_timeframe.is_derivable_from(source_timeframe):
            raise InvalidDerivedTimeframeError(
                timeframe=str(target_timeframe),
                source=str(source_timeframe),
            )

        try:
            return self._resample_with_pandas(
                candles, source_timeframe, target_timeframe
            )
        except InvalidDerivedTimeframeError:
            raise
        except Exception as e:
            raise ResamplingError(
                f"Resampling failed: {e}",
                details={"source": str(source_timeframe), "target": str(target_timeframe)},
            ) from e

    def _resample_with_pandas(
        self,
        candles: list[OHLCVCandle],
        source_timeframe: Timeframe,
        target_timeframe: Timeframe,
    ) -> list[OHLCVCandle]:
        """Perform the actual Pandas resampling."""
        df = pd.DataFrame({
            "timestamp": [c.timestamp for c in candles],
            "open": [float(c.open) for c in candles],
            "high": [float(c.high) for c in candles],
            "low": [float(c.low) for c in candles],
            "close": [float(c.close) for c in candles],
            "volume": [float(c.volume) for c in candles],
        })
        df.set_index("timestamp", inplace=True)

        freq = target_timeframe.to_pandas_freq()

        # For intraday resampling, align to NSE market session and filter
        # to market hours (9:15 AM – 3:30 PM IST, weekdays).
        if source_timeframe.unit == TimeframeUnit.MINUTE:
            df = self._filter_to_nse_session(df)
            origin = self._nse_origin()
            resampled = df.resample(
                freq,
                origin=origin,
                closed="left",
                label="left",
            ).agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            })
        else:
            # Multi-day resampling from daily data (no session filtering needed)
            resampled = df.resample(
                freq,
                closed="left",
                label="left",
            ).agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            })

        # Drop bins with no data (NaN open)
        resampled = resampled.dropna(subset=["open"])

        if resampled.empty:
            return []

        symbol = candles[0].symbol
        candles_out: list[OHLCVCandle] = []
        for timestamp, row in resampled.iterrows():
            candles_out.append(
                OHLCVCandle(
                    symbol=symbol,
                    timeframe=target_timeframe,
                    timestamp=timestamp.to_pydatetime(),
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                    volume=Decimal(str(row["volume"])),
                )
            )

        return candles_out

    @staticmethod
    def _filter_to_nse_session(df: pd.DataFrame) -> pd.DataFrame:
        """Filter DataFrame to NSE market hours (9:15 AM – 3:30 PM IST, weekdays)."""
        # Convert index to IST for filtering
        ist_index = df.index.tz_convert(IST)

        # Market hours: 9:15 AM – 3:30 PM IST
        market_open = ist_index.time >= time(_NSE_OPEN_HOUR, _NSE_OPEN_MINUTE)
        market_close = ist_index.time <= time(_NSE_CLOSE_HOUR, _NSE_CLOSE_MINUTE)

        # Weekdays only (Monday=0, Friday=4)
        is_weekday = ist_index.weekday < 5

        return df[market_open & market_close & is_weekday]

    @staticmethod
    def _nse_origin() -> datetime:
        """Return an origin timestamp aligned to NSE market open (9:15 IST)."""
        return datetime(2000, 1, 1, 9, 15, tzinfo=IST)
