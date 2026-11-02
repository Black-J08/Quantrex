"""Shoonya-specific normalizer for vendor responses."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from quantrex.core.data.exceptions.exceptions import NormalizationError
from quantrex.core.data.normalization.base import Normalizer
from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.timeframe import Timeframe
from quantrex.core.models.timezone import IST

logger = logging.getLogger(__name__)

#: Shoonya intraday timestamp format (e.g., "07-12-2022 09:15:00").
_INTRADAY_TS_FORMAT = "%d-%m-%Y %H:%M:%S"

#: Shoonya daily timestamp format (e.g., "05-DEC-2022").
_DAILY_TS_FORMAT = "%d-%b-%Y"

#: Month abbreviations to month numbers for parsing Shoonya daily timestamps.
_MONTH_ABBREVIATIONS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


class ShoonyaNormalizer(Normalizer):
    """Normalizes Shoonya API responses to Quantrex canonical models.

    Shoonya returns a flat list of candle dicts (from TPSeries for intraday
    or EODChartData for daily). Each dict carries fields such as ``time``,
    ``into``, ``inth``, ``intl``, ``intc``, ``intv`` and ``oi``. Timestamps
    are naive wall-clock values in Indian market time and are localized to
    IST.
    """

    def normalize_candles(
        self,
        raw_response: Any,
        symbol: str,
        timeframe: Timeframe,
    ) -> list[OHLCVCandle]:
        """Normalize Shoonya historical data response to OHLCVCandle list.

        Args:
            raw_response: Raw response from Shoonya API — a list of candle
                dicts, or a dict wrapping such a list.
            symbol: Trading symbol (e.g., "NSE:INFY").
            timeframe: Candle timeframe.

        Returns:
            List of normalized OHLCVCandle objects.

        Raises:
            NormalizationError: If the response cannot be normalized.
        """
        candles_data = self._extract_candles(raw_response)

        candles = []
        for i, candle_data in enumerate(candles_data):
            # Skip non-dict entries (e.g., vendor "no data" placeholders).
            if not isinstance(candle_data, dict):
                logger.warning(
                    "Skipping non-dict candle entry %d: %s", i, candle_data
                )
                continue
            try:
                ohlcv = self._dict_to_ohlcv(candle_data, symbol, timeframe)
                candles.append(ohlcv)
            except (ValueError, KeyError, TypeError) as e:
                logger.warning("Failed to parse candle %d: %s, data: %s", i, e, candle_data)
                continue

        logger.debug("Normalized %d candles for %s (%s)", len(candles), symbol, timeframe)
        return candles

    def _extract_candles(self, raw_response: Any) -> list[dict[str, Any]]:
        """Extract the list of candle dicts from a Shoonya response.

        Shoonya returns a flat list of candle dicts. Some endpoints may wrap
        the list in a dict; handle both shapes defensively. Shoonya may also
        return candle entries as JSON-encoded strings (e.g., daily candles),
        which are parsed into dicts here.
        """
        if isinstance(raw_response, list):
            return [self._parse_candle_entry(entry) for entry in raw_response]

        if isinstance(raw_response, dict):
            # Some Shoonya responses wrap data under a "data" key.
            data = raw_response.get("data", raw_response)
            if isinstance(data, list):
                return [self._parse_candle_entry(entry) for entry in data]
            candles = data.get("candles", []) if isinstance(data, dict) else []
            if isinstance(candles, list):
                return [self._parse_candle_entry(entry) for entry in candles]

        raise NormalizationError(
            f"Expected list or dict response, got {type(raw_response).__name__}",
            vendor="shoonya",
            raw_data=raw_response,
        )

    @staticmethod
    def _parse_candle_entry(entry: Any) -> dict[str, Any]:
        """Parse a single candle entry into a dict.

        Shoonya may return candle entries as JSON-encoded strings (e.g.,
        daily candles). Parse them into dicts; return dicts as-is.
        """
        if isinstance(entry, dict):
            return entry
        if isinstance(entry, str):
            try:
                parsed = json.loads(entry)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
        # Return a non-dict placeholder so the caller can skip it.
        return entry

    def _dict_to_ohlcv(
        self,
        candle: dict[str, Any],
        symbol: str,
        timeframe: Timeframe,
    ) -> OHLCVCandle:
        """Convert a single Shoonya candle dict to an OHLCVCandle."""
        timestamp = self._parse_timestamp(candle.get("time"))

        return OHLCVCandle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=timestamp,
            open=self._decimal(candle, "into"),
            high=self._decimal(candle, "inth"),
            low=self._decimal(candle, "intl"),
            close=self._decimal(candle, "intc"),
            volume=self._decimal(candle, "v", fallback="intv"),
        )

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        """Parse a Shoonya timestamp string into a timezone-aware datetime.

        Shoonya timestamps are naive wall-clock values in Indian market time.
        Supported formats:
        - Intraday: ``DD-MM-YYYY HH:MM:SS`` (e.g., ``07-12-2022 09:15:00``)
        - Daily: ``DD-MMM-YYYY`` (e.g., ``05-DEC-2022``)

        Args:
            value: Raw timestamp value from the API.

        Returns:
            Timezone-aware datetime in IST.

        Raises:
            ValueError: If the timestamp cannot be parsed.
        """
        if not isinstance(value, str) or not value:
            raise ValueError(f"Invalid timestamp: {value!r}")

        # Intraday format: DD-MM-YYYY HH:MM:SS
        if " " in value:
            date_part, time_part = value.split(" ", 1)
            day_str, month_str, year_str = date_part.split("-")
            hour_str, minute_str, second_str = time_part.split(":")
            dt = datetime(
                int(year_str),
                int(month_str),
                int(day_str),
                int(hour_str),
                int(minute_str),
                int(second_str),
                tzinfo=IST,
            )
            return dt

        # Daily format: DD-MMM-YYYY
        day_str, month_abbr, year_str = value.split("-")
        month = _MONTH_ABBREVIATIONS[month_abbr.lower()]
        dt = datetime(int(year_str), month, int(day_str), tzinfo=IST)
        return dt

    @staticmethod
    def _decimal(
        candle: dict[str, Any],
        primary: str,
        *,
        fallback: str | None = None,
    ) -> Decimal:
        """Extract a numeric field from a candle dict as a Decimal.

        Shoonya returns numeric fields as strings (e.g., ``"255.00"``).
        Returns a ``Decimal`` so it can be assigned directly to an
        ``OHLCVCandle`` field.

        Args:
            candle: Candle dict from the Shoonya API.
            primary: Primary field name (e.g., ``"into"``).
            fallback: Alternate field name if primary is missing/empty.

        Returns:
            Decimal value of the field.

        Raises:
            ValueError: If the field is missing or not a valid number.
        """
        value = candle.get(primary)
        if value is None or value == "":
            value = candle.get(fallback) if fallback is not None else None
        if value is None or value == "":
            raise ValueError(f"Missing required field: {primary}")
        try:
            return Decimal(str(value))
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid numeric value for {primary}: {value!r}") from e
