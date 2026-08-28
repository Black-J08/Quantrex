"""Pydantic models for Dhan API requests and responses."""

from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class HistoricalDataRequest(BaseModel):
    """Request model for daily historical data API."""

    security_id: str = Field(..., alias="securityId", description="Exchange standard ID for each scrip")
    exchange_segment: str = Field(..., alias="exchangeSegment", description="Exchange & segment (e.g., NSE_EQ)")
    instrument: str = Field(..., description="Instrument type (e.g., EQUITY)")
    expiry_code: int = Field(0, alias="expiryCode", description="Expiry code for derivatives (0 for equity)")
    oi: bool = Field(False, description="Include open interest data for F&O")
    from_date: str = Field(..., alias="fromDate", description="Start date (YYYY-MM-DD)")
    to_date: str = Field(..., alias="toDate", description="End date (YYYY-MM-DD, non-inclusive)")

    @field_validator("exchange_segment")
    @classmethod
    def validate_exchange_segment(cls, v: str) -> str:
        valid = {"NSE_EQ", "NSE_FNO", "NSE_CURRENCY", "BSE_EQ", "BSE_FNO", "BSE_CURRENCY", "MCX_COMM"}
        if v not in valid:
            raise ValueError(f"Invalid exchange_segment: {v}. Must be one of {valid}")
        return v

    @field_validator("instrument")
    @classmethod
    def validate_instrument(cls, v: str) -> str:
        valid = {"EQUITY", "FUTSTK", "OPTSTK", "FUTIDX", "OPTIDX", "FUTCOM", "OPTFUT", "FUTCUR", "OPTCUR", "INDEX"}
        if v not in valid:
            raise ValueError(f"Invalid instrument: {v}. Must be one of {valid}")
        return v


class IntradayDataRequest(BaseModel):
    """Request model for intraday historical data API."""

    security_id: str = Field(..., alias="securityId", description="Exchange standard ID for each scrip")
    exchange_segment: str = Field(..., alias="exchangeSegment", description="Exchange & segment (e.g., NSE_EQ)")
    instrument: str = Field(..., description="Instrument type (e.g., EQUITY)")
    interval: Literal["1", "5", "15", "30", "60"] = Field(..., description="Minute interval (1, 5, 15, 30, 60)")
    oi: bool = Field(False, description="Include open interest data for F&O")
    from_date: str = Field(..., alias="fromDate", description="Start date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)")
    to_date: str = Field(..., alias="toDate", description="End date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)")

    @field_validator("exchange_segment")
    @classmethod
    def validate_exchange_segment(cls, v: str) -> str:
        valid = {"NSE_EQ", "NSE_FNO", "NSE_CURRENCY", "BSE_EQ", "BSE_FNO", "BSE_CURRENCY", "MCX_COMM"}
        if v not in valid:
            raise ValueError(f"Invalid exchange_segment: {v}. Must be one of {valid}")
        return v

    @field_validator("instrument")
    @classmethod
    def validate_instrument(cls, v: str) -> str:
        valid = {"EQUITY", "FUTSTK", "OPTSTK", "FUTIDX", "OPTIDX", "FUTCOM", "OPTFUT", "FUTCUR", "OPTCUR", "INDEX"}
        if v not in valid:
            raise ValueError(f"Invalid instrument: {v}. Must be one of {valid}")
        return v


class HistoricalDataResponse(BaseModel):
    """Response model for historical data API."""

    open: list[float] = Field(..., description="Open prices")
    high: list[float] = Field(..., description="High prices")
    low: list[float] = Field(..., description="Low prices")
    close: list[float] = Field(..., description="Close prices")
    volume: list[int] = Field(..., description="Volume traded")
    timestamp: list[int] = Field(..., description="Epoch timestamps")
    open_interest: list[int] | None = Field(None, alias="open_interest", description="Open interest (F&O only)")

    def to_dict_list(self) -> list[dict]:
        """Convert response to list of dictionaries for adapter consumption."""
        n = len(self.timestamp)
        result = []
        for i in range(n):
            row = {
                "open": self.open[i],
                "high": self.high[i],
                "low": self.low[i],
                "close": self.close[i],
                "volume": self.volume[i],
                "timestamp": self.timestamp[i],
            }
            if self.open_interest is not None and i < len(self.open_interest):
                row["oi"] = self.open_interest[i]
            result.append(row)
        return result

    def validate_lengths(self) -> None:
        """Validate all array fields have the same length."""
        lengths = {
            "open": len(self.open),
            "high": len(self.high),
            "low": len(self.low),
            "close": len(self.close),
            "volume": len(self.volume),
            "timestamp": len(self.timestamp),
        }
        if self.open_interest is not None:
            lengths["open_interest"] = len(self.open_interest)

        unique_lengths = set(lengths.values())
        if len(unique_lengths) > 1:
            raise ValueError(f"Response array lengths mismatch: {lengths}")


class IntradayDataResponse(HistoricalDataResponse):
    """Response model for intraday historical data API (same structure as daily)."""
    pass


class InstrumentMasterRow(BaseModel):
    """Single row from instrument master CSV."""

    exch_id: str = Field(..., alias="EXCH_ID")
    segment: str = Field(..., alias="SEGMENT")
    isin: str | None = Field(None, alias="ISIN")
    instrument: str = Field(..., alias="INSTRUMENT")
    expiry_code: int | None = Field(None, alias="SEM_EXPIRY_CODE")
    underlying_security_id: str | None = Field(None, alias="UNDERLYING_SECURITY_ID")
    underlying_symbol: str | None = Field(None, alias="UNDERLYING_SYMBOL")
    symbol_name: str = Field(..., alias="SYMBOL_NAME")
    trading_symbol: str = Field(..., alias="SEM_TRADING_SYMBOL")
    display_name: str | None = Field(None, alias="DISPLAY_NAME")
    instrument_type: str = Field(..., alias="INSTRUMENT_TYPE")
    series: str | None = Field(None, alias="SERIES")
    lot_size: int | None = Field(None, alias="LOT_SIZE")
    expiry_date: str | None = Field(None, alias="SM_EXPIRY_DATE")
    strike_price: float | None = Field(None, alias="STRIKE_PRICE")
    option_type: str | None = Field(None, alias="OPTION_TYPE")
    tick_size: float | None = Field(None, alias="TICK_SIZE")
    expiry_flag: str | None = Field(None, alias="EXPIRY_FLAG")
    bracket_flag: str | None = Field(None, alias="BRACKET_FLAG")
    cover_flag: str | None = Field(None, alias="COVER_FLAG")
    asm_gsm_flag: str | None = Field(None, alias="ASM_GSM_FLAG")
    asm_gsm_category: str | None = Field(None, alias="ASM_GSM_CATEGORY")
    buy_sell_indicator: str | None = Field(None, alias="BUY_SELL_INDICATOR")
    buy_co_min_margin_per: float | None = Field(None, alias="BUY_CO_MIN_MARGIN_PER")
    sell_co_min_margin_per: float | None = Field(None, alias="SELL_CO_MIN_MARGIN_PER")
    buy_co_sl_range_max_perc: float | None = Field(None, alias="BUY_CO_SL_RANGE_MAX_PERC")
    sell_co_sl_range_max_perc: float | None = Field(None, alias="SELL_CO_SL_RANGE_MAX_PERC")
    buy_co_sl_range_min_perc: float | None = Field(None, alias="BUY_CO_SL_RANGE_MIN_PERC")
    sell_co_sl_range_min_perc: float | None = Field(None, alias="SELL_CO_SL_RANGE_MIN_PERC")
    buy_bo_min_margin_per: float | None = Field(None, alias="BUY_BO_MIN_MARGIN_PER")
    sell_bo_min_margin_per: float | None = Field(None, alias="SELL_BO_MIN_MARGIN_PER")
    buy_bo_sl_range_max_perc: float | None = Field(None, alias="BUY_BO_SL_RANGE_MAX_PERC")
    sell_bo_sl_range_max_perc: float | None = Field(None, alias="SELL_BO_SL_RANGE_MAX_PERC")
    buy_bo_sl_range_min_perc: float | None = Field(None, alias="BUY_BO_SL_RANGE_MIN_PERC")
    sell_bo_sl_range_min_perc: float | None = Field(None, alias="SELL_BO_SL_RANGE_MIN_PERC")
    buy_bo_profit_range_max_perc: float | None = Field(None, alias="BUY_BO_PROFIT_RANGE_MAX_PERC")
    sell_bo_profit_range_max_perc: float | None = Field(None, alias="SELL_BO_PROFIT_RANGE_MAX_PERC")
    buy_bo_profit_range_min_perc: float | None = Field(None, alias="BUY_BO_PROFIT_RANGE_MIN_PERC")
    sell_bo_profit_range_min_perc: float | None = Field(None, alias="SELL_BO_PROFIT_RANGE_MIN_PERC")
    mtf_leverage: float | None = Field(None, alias="MTF_LEVERAGE")

    def get_security_id(self) -> str:
        """Get the security ID from the row (EXCH_ID + SEM_EXM_EXCH_ID or similar)."""
        # The security ID is typically in a field not directly mapped
        # For compact CSV, it's the third column
        return self.exch_id  # This will be overridden by parser


# Type aliases for convenience
Timeframe = Literal["day", "1minute", "5minute", "15minute", "30minute", "60minute"]
ExchangeSegment = Literal["NSE_EQ", "NSE_FNO", "NSE_CURRENCY", "BSE_EQ", "BSE_FNO", "BSE_CURRENCY", "MCX_COMM"]
InstrumentType = Literal["EQUITY", "FUTSTK", "OPTSTK", "FUTIDX", "OPTIDX", "FUTCOM", "OPTFUT", "FUTCUR", "OPTCUR", "INDEX"]