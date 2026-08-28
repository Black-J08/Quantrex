"""Configuration for Dhan Data Provider."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class DhanProviderConfig:
    """Configuration for DhanDataProvider.

    Attributes:
        access_token: JWT access token for DhanHQ API. If None, loads from DHAN_ACCESS_TOKEN env var.
        symbol: User-friendly trading symbol (e.g., "RELIANCE"). Mutually exclusive with security_id.
        security_id: Dhan's numeric security ID (e.g., "1333"). Mutually exclusive with symbol.
        exchange_segment: Exchange segment (NSE_EQ, NSE_FNO, NSE_CURRENCY, BSE_EQ, BSE_FNO, BSE_CURRENCY, MCX_COMM).
        instrument: Instrument type (EQUITY, FUTSTK, OPTSTK, FUTIDX, OPTIDX, FUTCOM, OPTFUT, FUTCUR, OPTCUR, INDEX).
        expiry_code: Expiry code for derivatives (0 for equity/index).
        from_date: Start date (date, datetime, or str in YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
        to_date: End date (date, datetime, or str in YYYY-MM-DD or YYYY-MM-DD HH:MM:SS). Non-inclusive for daily.
        timeframe: Data timeframe (day, 1minute, 5minute, 15minute, 30minute, 60minute).
        include_oi: Include open interest data (F&O only).
        base_url: API base URL (supports sandbox: https://sandbox.dhan.co).
        timeout: Request timeout in seconds.
        max_retries: Maximum retry attempts for failed requests.
        chunk_size_days: Custom chunk sizes per timeframe (days per request).
        cache_dir: Directory for caching instrument master CSV.
        cache_ttl_hours: Cache TTL for instrument master in hours.
    """

    access_token: str | None = None
    symbol: str | None = None
    security_id: str | None = None
    exchange_segment: str = ""
    instrument: str = ""
    expiry_code: int = 0
    from_date: str = ""
    to_date: str = ""
    timeframe: Literal["day", "1minute", "5minute", "15minute", "30minute", "60minute"] = "day"
    include_oi: bool = False
    base_url: str = "https://api.dhan.co"
    timeout: float = 30.0
    max_retries: int = 3
    chunk_size_days: dict[str, int] = field(default_factory=dict)
    cache_dir: Path = field(default_factory=lambda: Path("~/.quantrex/cache/dhan").expanduser())
    cache_ttl_hours: int = 24

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        # Validate mutually exclusive symbol/security_id
        if self.symbol is not None and self.security_id is not None:
            raise ValueError("Provide either 'symbol' or 'security_id', not both")
        if self.symbol is None and self.security_id is None:
            raise ValueError("Must provide either 'symbol' or 'security_id'")

        # Validate required fields
        if not self.exchange_segment:
            raise ValueError("exchange_segment is required")
        if not self.instrument:
            raise ValueError("instrument is required")
        if not self.from_date:
            raise ValueError("from_date is required")
        if not self.to_date:
            raise ValueError("to_date is required")

        # Validate exchange_segment
        valid_segments = {
            "NSE_EQ", "NSE_FNO", "NSE_CURRENCY",
            "BSE_EQ", "BSE_FNO", "BSE_CURRENCY",
            "MCX_COMM"
        }
        if self.exchange_segment not in valid_segments:
            raise ValueError(f"Invalid exchange_segment: {self.exchange_segment}. Must be one of {valid_segments}")

        # Validate instrument
        valid_instruments = {
            "EQUITY", "FUTSTK", "OPTSTK", "FUTIDX", "OPTIDX",
            "FUTCOM", "OPTFUT", "FUTCUR", "OPTCUR", "INDEX"
        }
        if self.instrument not in valid_instruments:
            raise ValueError(f"Invalid instrument: {self.instrument}. Must be one of {valid_instruments}")

        # Validate timeframe
        valid_timeframes = {"day", "1minute", "5minute", "15minute", "30minute", "60minute"}
        if self.timeframe not in valid_timeframes:
            raise ValueError(f"Invalid timeframe: {self.timeframe}. Must be one of {valid_timeframes}")

        # Validate chunk_size_days has all required timeframes (only if explicitly provided)
        if self.chunk_size_days:
            for tf in valid_timeframes:
                if tf not in self.chunk_size_days:
                    raise ValueError(f"chunk_size_days missing required timeframe: {tf}")
                if self.chunk_size_days[tf] <= 0:
                    raise ValueError(f"chunk_size_days[{tf}] must be positive")

        # Validate cache_dir
        if not isinstance(self.cache_dir, Path):
            object.__setattr__(self, "cache_dir", Path(self.cache_dir).expanduser())

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)