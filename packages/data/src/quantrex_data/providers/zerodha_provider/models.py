"""Pydantic models for Zerodha API requests and responses."""

from typing import Any

from pydantic import BaseModel, Field


class HistoricalDataRequest(BaseModel):
    """Request parameters for historical data API.

    Note: The actual API uses query parameters, not JSON body.
    This model is used for validation and documentation.
    """

    instrument_token: str = Field(..., description="Instrument token from instrument master")
    interval: str = Field(..., description="Candle interval (minute, 3minute, 5minute, etc.)")
    from_date: str = Field(..., alias="from", description="Start date in YYYY-MM-DD HH:MM:SS format")
    to_date: str = Field(..., alias="to", description="End date in YYYY-MM-DD HH:MM:SS format")
    continuous: int = Field(default=0, description="1 for continuous futures data, 0 otherwise")
    oi: int = Field(default=0, description="1 to include open interest, 0 otherwise")

    class Config:
        populate_by_name = True


class HistoricalDataResponse(BaseModel):
    """Response from historical data API."""

    status: str = Field(..., description="Response status (success/error)")
    data: dict[str, Any] = Field(default_factory=dict, description="Response data containing candles")
    message: str | None = Field(default=None, description="Error message if status is error")
    error_type: str | None = Field(default=None, description="Error type if status is error")

    def get_candles(self) -> list[list]:
        """Extract candles array from response data.

        Returns:
            List of candles, each candle is [timestamp, open, high, low, close, volume, oi?]
        """
        if self.status != "success":
            return []
        return self.data.get("candles", [])

    def validate_lengths(self) -> None:
        """Validate that all candle arrays have consistent lengths."""
        candles = self.get_candles()
        if not candles:
            return
        # Each candle should have 6 or 7 elements (with OI)
        expected_len = len(candles[0])
        for i, candle in enumerate(candles):
            if len(candle) != expected_len:
                raise ValueError(f"Candle {i} has {len(candle)} elements, expected {expected_len}")


class InstrumentMasterRow(BaseModel):
    """Single row from instrument master CSV."""

    instrument_token: str
    exchange_token: str
    tradingsymbol: str
    name: str
    last_price: float
    expiry: str | None = None
    strike: float | None = None
    tick_size: float
    lot_size: int
    instrument_type: str
    segment: str
    exchange: str


class UserProfileResponse(BaseModel):
    """Response from user profile API (used for token validation)."""

    status: str
    data: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None
    error_type: str | None = None


class SessionTokenResponse(BaseModel):
    """Response from session/token API (login flow)."""

    status: str
    data: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None
    error_type: str | None = None


class InstrumentsResponse(BaseModel):
    """Response from instruments API (CSV content)."""

    # This is raw CSV text, not JSON
    pass