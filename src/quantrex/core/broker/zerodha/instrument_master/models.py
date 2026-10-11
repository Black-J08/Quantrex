"""Zerodha instrument master models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(slots=True, frozen=True)
class ZerodhaInstrument:
    """Zerodha instrument from the instrument master CSV.

    CSV columns: instrument_token, exchange_token, tradingsymbol, name, last_price,
    expiry, strike, tick_size, lot_size, instrument_type, segment, exchange
    """

    instrument_token: int
    exchange_token: int
    tradingsymbol: str
    name: str
    last_price: Decimal
    expiry: date | None
    strike: Decimal | None
    tick_size: Decimal
    lot_size: int
    instrument_type: str
    segment: str
    exchange: str

    @property
    def symbol(self) -> str:
        """Full symbol in format 'EXCHANGE:TRADINGSYMBOL'."""
        return f"{self.exchange}:{self.tradingsymbol}"

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> ZerodhaInstrument:
        """Create ZerodhaInstrument from CSV row dictionary."""
        # Parse expiry date if present
        expiry = None
        if row.get("expiry"):
            try:
                expiry = date.fromisoformat(row["expiry"])
            except ValueError:
                pass  # Invalid date, leave as None

        # Parse numeric fields
        last_price = Decimal(row["last_price"]) if row.get("last_price") else Decimal(0)
        strike = Decimal(row["strike"]) if row.get("strike") else None
        tick_size = Decimal(row["tick_size"]) if row.get("tick_size") else Decimal(0)
        lot_size = int(row["lot_size"]) if row.get("lot_size") else 0
        instrument_token = int(row["instrument_token"]) if row.get("instrument_token") else 0
        exchange_token = int(row["exchange_token"]) if row.get("exchange_token") else 0

        return cls(
            instrument_token=instrument_token,
            exchange_token=exchange_token,
            tradingsymbol=row.get("tradingsymbol", ""),
            name=row.get("name", ""),
            last_price=last_price,
            expiry=expiry,
            strike=strike,
            tick_size=tick_size,
            lot_size=lot_size,
            instrument_type=row.get("instrument_type", ""),
            segment=row.get("segment", ""),
            exchange=row.get("exchange", ""),
        )