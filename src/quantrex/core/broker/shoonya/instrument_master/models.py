"""Shoonya instrument master models."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ShoonyaInstrument:
    """Shoonya instrument from the symbol master.

    Parsed from segment-specific symbol master .txt files (pipe/comma-delimited).
    Column order varies by segment, so parsing is handled by the InstrumentMaster.
    """

    instrument_token: str
    exchange_token: str
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
