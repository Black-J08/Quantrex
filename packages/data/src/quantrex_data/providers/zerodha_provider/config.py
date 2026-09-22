"""Configuration for Zerodha Data Provider."""

import hashlib
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from quantrex_core.logging import get_logger

from .exceptions import ZerodhaInstrumentMasterError

logger = get_logger(__name__)

# Default token file location
DEFAULT_TOKEN_FILE = Path("~/.quantrex/zerodha/access_token").expanduser()
# Default cache directory
DEFAULT_CACHE_DIR = Path("~/.quantrex/cache/zerodha").expanduser()

# Default callback configuration
DEFAULT_REDIRECT_URL = "http://localhost:8765/callback"
DEFAULT_CALLBACK_TIMEOUT = 120.0


def _parse_redirect_url(redirect_url: str) -> tuple[str, int, str]:
    """Parse redirect URL into host, port, and path.

    Args:
        redirect_url: Full redirect URL (e.g., http://localhost:8765/callback)

    Returns:
        Tuple of (host, port, path)

    Raises:
        ValueError: If URL is invalid or missing required components.
    """
    parsed = urlparse(redirect_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid redirect URL: {redirect_url}. Must include scheme and host.")

    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/callback"

    return host, port, path


def _resolve_access_token(
    explicit_token: str | None,
    token_file: Path,
    api_key: str | None,
    api_secret: str | None,
) -> str | None:
    """Resolve access token from explicit value, token file, or trigger login flow.

    Resolution order:
        1. Explicit token passed to config
        2. Token file at ~/.quantrex/zerodha/access_token
        3. None (will trigger login flow in provider initialization)

    Args:
        explicit_token: Explicitly provided access token
        token_file: Path to token file
        api_key: API key (for login flow)
        api_secret: API secret (for login flow)

    Returns:
        Access token string or None if not available
    """
    if explicit_token:
        logger.debug("Using explicit access token")
        return explicit_token

    # Try to load from token file
    if token_file.exists():
        try:
            token = token_file.read_text().strip()
            if token:
                logger.debug("Loaded access token from %s", token_file)
                return token
        except Exception as e:
            logger.warning("Failed to read token file %s: %s", token_file, e)

    logger.debug("No access token found; will trigger login flow on first request")
    return None


def _validate_exchange(exchange: str) -> None:
    """Validate exchange segment."""
    valid_exchanges = {"NSE", "NFO", "BSE", "BFO", "CDS", "MCX", "BCD", "MF"}
    if exchange not in valid_exchanges:
        raise ValueError(f"Invalid exchange: {exchange}. Must be one of {valid_exchanges}")


def _validate_interval(interval: str) -> None:
    """Validate interval."""
    valid_intervals = {
        "minute",
        "3minute",
        "5minute",
        "10minute",
        "15minute",
        "30minute",
        "60minute",
        "day",
    }
    if interval not in valid_intervals:
        raise ValueError(f"Invalid interval: {interval}. Must be one of {valid_intervals}")


def _normalize_date_input(value: date | datetime | str) -> str:
    """Normalize date/datetime/str input to string for config storage.

    Args:
        value: Date input in various formats.

    Returns:
        String representation (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
    """
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    raise ValueError(f"Unsupported date type: {type(value)}. Use date, datetime, or str.")


@dataclass(frozen=True, slots=True)
class ZerodhaProviderConfig:
    """Configuration for ZerodhaDataProvider.

    Attributes:
        api_key: Zerodha API key. If None, loads from ZERODHA_API_KEY env var.
        api_secret: Zerodha API secret. If None, loads from ZERODHA_API_SECRET env var.
        access_token: Access token for API calls. If None, loads from token_file or triggers login flow.
        token_file: Path to access token file. Default: ~/.quantrex/zerodha/access_token
        symbol: User-friendly trading symbol (e.g., "RELIANCE"). Mutually exclusive with instrument_token.
        instrument_token: Zerodha's numeric instrument token (e.g., "408065"). Mutually exclusive with symbol.
        exchange: Exchange segment (NSE, NFO, BSE, BFO, CDS, MCX, BCD, MF).
        from_date: Optional start date (date, datetime, or str in YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
                  If not provided, must be passed to fetch() at runtime.
        to_date: Optional end date (date, datetime, or str in YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
                If not provided, must be passed to fetch() at runtime.
        interval: Data interval (minute, 3minute, 5minute, 10minute, 15minute, 30minute, 60minute, day).
        continuous: Whether to get continuous data for futures (default: False).
        oi: Include open interest data (default: False).
        base_url: API base URL (default: https://api.kite.trade).
        timeout: Request timeout in seconds (default: 30.0).
        max_retries: Maximum retry attempts for failed requests (default: 3).
        chunk_size_days: Custom chunk sizes per interval (days per request).
        cache_dir: Directory for caching instrument master CSV.
        cache_ttl_hours: Cache TTL for instrument master in hours (default: 24).
        redirect_url: Full callback URL for OAuth redirect. Default: http://localhost:8765/callback.
                     Can be set via ZERODHA_REDIRECT_URL env var.
        callback_timeout: Timeout in seconds for waiting for callback. Default: 120.
                         Can be set via ZERODHA_CALLBACK_TIMEOUT env var.
    """

    api_key: str | None = None
    api_secret: str | None = None
    access_token: str | None = None
    token_file: Path = field(default_factory=lambda: DEFAULT_TOKEN_FILE)
    symbol: str | None = None
    instrument_token: str | None = None
    exchange: str = ""
    from_date: str | None = None
    to_date: str | None = None
    interval: Literal[
        "minute",
        "3minute",
        "5minute",
        "10minute",
        "15minute",
        "30minute",
        "60minute",
        "day",
    ] = "day"
    continuous: bool = False
    oi: bool = False
    base_url: str = "https://api.kite.trade"
    timeout: float = 30.0
    max_retries: int = 3
    chunk_size_days: dict[str, int] = field(default_factory=dict)
    cache_dir: Path = field(default_factory=lambda: DEFAULT_CACHE_DIR)
    cache_ttl_hours: int = 24

    # Callback server configuration (single source of truth: redirect_url)
    redirect_url: str = DEFAULT_REDIRECT_URL
    callback_timeout: float = DEFAULT_CALLBACK_TIMEOUT

    # Parsed callback components (set in __post_init__)
    _callback_host: str = field(default="", init=False, repr=False)
    _callback_port: int = field(default=0, init=False, repr=False)
    _callback_path: str = field(default="", init=False, repr=False)

    @property
    def callback_host(self) -> str:
        """Host for local callback server (parsed from redirect_url)."""
        return self._callback_host

    @property
    def callback_port(self) -> int:
        """Port for local callback server (parsed from redirect_url)."""
        return self._callback_port

    @property
    def callback_path(self) -> str:
        """Path for local callback server (parsed from redirect_url)."""
        return self._callback_path

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        # Resolve api_key from explicit kwarg or env var
        resolved_api_key = self.api_key or os.getenv("ZERODHA_API_KEY")
        if not resolved_api_key:
            raise ValueError(
                "api_key is required. Provide it explicitly or set ZERODHA_API_KEY environment variable."
            )
        object.__setattr__(self, "api_key", resolved_api_key)

        # Resolve api_secret from explicit kwarg or env var
        resolved_api_secret = self.api_secret or os.getenv("ZERODHA_API_SECRET")
        if not resolved_api_secret:
            raise ValueError(
                "api_secret is required. Provide it explicitly or set ZERODHA_API_SECRET environment variable."
            )
        object.__setattr__(self, "api_secret", resolved_api_secret)

        # Validate mutually exclusive symbol/instrument_token
        if self.symbol is not None and self.instrument_token is not None:
            raise ValueError("Provide either 'symbol' or 'instrument_token', not both")
        if self.symbol is None and self.instrument_token is None:
            raise ValueError("Must provide either 'symbol' or 'instrument_token'")

        # Validate required fields
        if not self.exchange:
            raise ValueError("exchange is required")

        # Validate exchange
        _validate_exchange(self.exchange)

        # Validate interval
        _validate_interval(self.interval)

        # Normalize dates if provided
        if self.from_date is not None:
            object.__setattr__(self, "from_date", _normalize_date_input(self.from_date))
        if self.to_date is not None:
            object.__setattr__(self, "to_date", _normalize_date_input(self.to_date))

        # Validate chunk_size_days has all required intervals (only if explicitly provided)
        if self.chunk_size_days:
            valid_intervals = {
                "minute",
                "3minute",
                "5minute",
                "10minute",
                "15minute",
                "30minute",
                "60minute",
                "day",
            }
            for interval in valid_intervals:
                if interval not in self.chunk_size_days:
                    raise ValueError(f"chunk_size_days missing required interval: {interval}")
                if self.chunk_size_days[interval] <= 0:
                    raise ValueError(f"chunk_size_days[{interval}] must be positive")

        # Validate cache_dir
        if self.cache_dir is None:
            object.__setattr__(self, "cache_dir", DEFAULT_CACHE_DIR)
        elif not isinstance(self.cache_dir, Path):
            object.__setattr__(self, "cache_dir", Path(self.cache_dir).expanduser())

        # Validate token_file
        if self.token_file is None:
            object.__setattr__(self, "token_file", DEFAULT_TOKEN_FILE)
        elif not isinstance(self.token_file, Path):
            object.__setattr__(self, "token_file", Path(self.token_file).expanduser())

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Ensure token file directory exists
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

        # Resolve callback configuration from env vars
        # Single source of truth: ZERODHA_REDIRECT_URL
        explicit_redirect_url = os.getenv("ZERODHA_REDIRECT_URL") or DEFAULT_REDIRECT_URL
        object.__setattr__(self, "redirect_url", explicit_redirect_url)

        # Parse redirect URL to get host, port, and path for callback server
        try:
            callback_host, callback_port, callback_path = _parse_redirect_url(explicit_redirect_url)
        except ValueError as e:
            raise ValueError(f"Invalid ZERODHA_REDIRECT_URL: {e}") from e

        # Store parsed components for callback server
        object.__setattr__(self, "_callback_host", callback_host)
        object.__setattr__(self, "_callback_port", callback_port)
        object.__setattr__(self, "_callback_path", callback_path)

        # Resolve callback timeout
        resolved_callback_timeout = DEFAULT_CALLBACK_TIMEOUT
        env_timeout = os.getenv("ZERODHA_CALLBACK_TIMEOUT")
        if env_timeout:
            try:
                resolved_callback_timeout = float(env_timeout)
            except ValueError:
                raise ValueError(f"ZERODHA_CALLBACK_TIMEOUT must be a number, got: {env_timeout}")
        if resolved_callback_timeout <= 0:
            raise ValueError(f"callback_timeout must be positive, got: {resolved_callback_timeout}")
        object.__setattr__(self, "callback_timeout", resolved_callback_timeout)

        # Resolve access token (may be None if not yet available)
        resolved_token = _resolve_access_token(
            self.access_token,
            self.token_file,
            self.api_key,
            self.api_secret,
        )
        object.__setattr__(self, "access_token", resolved_token)

        logger.debug(
            "ZerodhaProviderConfig initialized: exchange=%s, interval=%s, symbol=%s, instrument_token=%s, redirect_url=%s",
            self.exchange,
            self.interval,
            self.symbol,
            self.instrument_token,
            self.redirect_url,
        )