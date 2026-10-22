"""Cache key generation and parsing utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from quantrex.core.models.timeframe import Timeframe


@dataclass(slots=True, frozen=True)
class CacheKey:
    """Structured cache key for OHLCV data."""

    symbol: str
    timeframe: Timeframe
    from_date: date
    to_date: date
    version: int = 1

    def to_filename(self) -> str:
        """Convert to filename format: {symbol}_{timeframe}_{from_date}_{to_date}_v{version}.feather"""
        tf_str = str(self.timeframe)
        from_str = self.from_date.isoformat()
        to_str = self.to_date.isoformat()
        # Sanitize symbol for filesystem (replace : and / with _)
        safe_symbol = self.symbol.replace(":", "_").replace("/", "_")
        return f"{safe_symbol}_{tf_str}_{from_str}_{to_str}_v{self.version}.feather"

    def to_path(self, base_dir: Path) -> Path:
        """Get full path for this cache key."""
        safe_symbol = self.symbol.replace(":", "_").replace("/", "_")
        tf_str = str(self.timeframe)
        return base_dir / safe_symbol / tf_str / self.to_filename()

    @classmethod
    def from_filename(cls, filename: str) -> CacheKey | None:
        """Parse cache key from filename.
        
        Expected format: {symbol}_{timeframe}_{from_date}_{to_date}_v{version}.feather
        """
        if not filename.endswith(".feather"):
            return None
        
        stem = filename[:-8]  # Remove .feather
        parts = stem.split("_")
        
        if len(parts) < 5:
            return None
        
        # Last part is version (vN)
        version_part = parts[-1]
        if not version_part.startswith("v"):
            return None
        try:
            version = int(version_part[1:])
        except ValueError:
            return None
        
        # Date parts are the last two before version
        to_date_str = parts[-2]
        from_date_str = parts[-3]
        
        # Timeframe is the part before from_date
        tf_str = parts[-4]
        
        # Symbol is everything before timeframe (may contain underscores)
        symbol_parts = parts[:-4]
        safe_symbol = "_".join(symbol_parts)
        # Restore original symbol format (replace _ with : for exchange:symbol)
        symbol = safe_symbol.replace("_", ":", 1) if "_" in safe_symbol else safe_symbol
        
        try:
            from_date = date.fromisoformat(from_date_str)
            to_date = date.fromisoformat(to_date_str)
            timeframe = Timeframe.from_string(tf_str)
        except (ValueError, IndexError):
            return None
        
        return cls(
            symbol=symbol,
            timeframe=timeframe,
            from_date=from_date,
            to_date=to_date,
            version=version,
        )

    @classmethod
    def create(
        cls,
        symbol: str,
        timeframe: Timeframe,
        from_date: date | datetime,
        to_date: date | datetime,
        version: int = 1,
    ) -> CacheKey:
        """Create a cache key from components."""
        if isinstance(from_date, datetime):
            from_date = from_date.date()
        if isinstance(to_date, datetime):
            to_date = to_date.date()
        
        return cls(
            symbol=symbol,
            timeframe=timeframe,
            from_date=from_date,
            to_date=to_date,
            version=version,
        )


def generate_cache_key(
    symbol: str,
    timeframe: Timeframe,
    from_date: date | datetime,
    to_date: date | datetime,
    version: int = 1,
) -> CacheKey:
    """Convenience function to create a cache key."""
    return CacheKey.create(symbol, timeframe, from_date, to_date, version)