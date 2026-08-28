"""Configuration for Dhan Data Provider."""

import base64
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


def _extract_dhan_client_id_from_jwt(jwt_token: str) -> str | None:
    """Extract the ``dhanClientId`` claim from a Dhan JWT access token.

    Dhan JWTs are HS512-signed and contain a ``dhanClientId`` claim that uniquely
    identifies the client. The Dhan v2 API expects this value in the ``client-id``
    HTTP header and the ``dhanClientId`` body field on every request. We extract
    it without verifying the signature (the server does that) — the goal here is
    just to surface the right identifier when callers haven't set
    ``DHAN_CLIENT_ID`` explicitly.

    The JWT format is ``header.payload.signature`` where each segment is
    base64url-encoded. We decode the payload, parse the JSON, and return
    ``payload["dhanClientId"]`` (or ``None`` if the claim is absent / the token
    is malformed).
    """
    if not jwt_token or not isinstance(jwt_token, str):
        return None
    parts = jwt_token.split(".")
    if len(parts) < 2:
        return None
    payload_b64 = parts[1]
    # Pad to a multiple of 4 for base64 decoding.
    padding = "=" * (-len(payload_b64) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_b64 + padding)
        claims = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return None
    client_id = claims.get("dhanClientId")
    return str(client_id) if client_id else None


def _resolve_client_id(explicit: str | None, access_token: str | None) -> str | None:
    """Resolve the Dhan client ID from explicit kwarg, env var, or JWT claim.

    Resolution order:
        1. ``explicit`` value passed to the config.
        2. ``DHAN_CLIENT_ID`` environment variable.
        3. ``dhanClientId`` claim inside the JWT access token — first using
           the explicit ``access_token`` argument, then falling back to
           ``DHAN_ACCESS_TOKEN`` so callers who leave both kwargs at
           ``None`` (the default in the example) still get a working
           client_id via the JWT path.

    Returns ``None`` if none of those sources yield a value (the caller decides
    whether that is an error).
    """
    if explicit:
        return explicit
    env_client_id = os.getenv("DHAN_CLIENT_ID")
    if env_client_id:
        return env_client_id
    token = access_token or os.getenv("DHAN_ACCESS_TOKEN")
    if token:
        return _extract_dhan_client_id_from_jwt(token)
    return None


@dataclass(frozen=True, slots=True)
class DhanProviderConfig:
    """Configuration for DhanDataProvider.

    Attributes:
        access_token: JWT access token for DhanHQ API. If None, loads from DHAN_ACCESS_TOKEN env var.
        client_id: Dhan client ID (e.g., "1112625384"). Required by the Dhan v2 API
            alongside ``access_token``: it must be sent in the ``client-id`` HTTP header
            and as the ``dhanClientId`` field in every request body. If None, the client
            first checks ``DHAN_CLIENT_ID`` env var, then falls back to extracting the
            ``dhanClientId`` claim from the access-token JWT. Raises ``ValueError`` if
            none of those sources yield a value.
        symbol: User-friendly trading symbol (e.g., "RELIANCE"). Mutually exclusive with security_id.
        security_id: Dhan's numeric security ID (e.g., "1333"). Mutually exclusive with symbol.
        exchange_segment: Exchange segment (NSE_EQ, NSE_FNO, NSE_CURRENCY, BSE_EQ, BSE_FNO, BSE_CURRENCY, MCX_COMM).
        instrument: Instrument type (EQUITY, FUTSTK, OPTSTK, FUTIDX, OPTIDX, FUTCOM, OPTFUT, FUTCUR, OPTCUR, INDEX).
        expiry_code: Expiry code for derivatives (0 for equity/index).
        from_date: Start date (date, datetime, or str in YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
        to_date: End date (date, datetime, or str in YYYY-MM-DD or YYYY-MM-DD HH:MM:SS). Non-inclusive for daily.
        timeframe: Data timeframe (day, 1minute, 5minute, 15minute, 30minute, 60minute).
        include_oi: Include open interest data (F&O only).
        base_url: API base URL. The Dhan v2 endpoints are served under the
            ``/v2/`` prefix (verified against https://docs.dhanhq.co/api/v2/
            and the official dhan-oss/DhanHQ-py SDK which uses
            ``API_BASE_URL = 'https://api.dhan.co/v2'``). Requests to
            ``https://api.dhan.co/charts/historical`` are permanently
            redirected (HTTP 301) to ``https://api.dhan.co/v2/``, so the
            default includes the ``/v2`` suffix. For the sandbox
            environment use ``https://sandbox.dhan.co/v2``.
        timeout: Request timeout in seconds.
        max_retries: Maximum retry attempts for failed requests.
        chunk_size_days: Custom chunk sizes per timeframe (days per request).
        cache_dir: Directory for caching instrument master CSV.
        cache_ttl_hours: Cache TTL for instrument master in hours.
    """

    access_token: str | None = None
    client_id: str | None = None
    symbol: str | None = None
    security_id: str | None = None
    exchange_segment: str = ""
    instrument: str = ""
    expiry_code: int = 0
    from_date: str = ""
    to_date: str = ""
    timeframe: Literal["day", "1minute", "5minute", "15minute", "30minute", "60minute"] = "day"
    include_oi: bool = False
    base_url: str = "https://api.dhan.co/v2"
    timeout: float = 30.0
    max_retries: int = 3
    chunk_size_days: dict[str, int] = field(default_factory=dict)
    cache_dir: Path = field(default_factory=lambda: Path("~/.quantrex/cache/dhan").expanduser())
    cache_ttl_hours: int = 24

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        # Resolve client_id from explicit kwarg, env var, or JWT claim.
        # Dhan v2 requires both access_token and client_id on every request
        # (see https://docs.dhanhq.co/api/v2/ and the official
        # dhan-oss/DhanHQ-py SDK: both 'client-id' header and 'dhanClientId'
        # body field are mandatory). Without it, the gateway returns 301 /
        # 400 instead of the expected JSON.
        resolved_client_id = _resolve_client_id(self.client_id, self.access_token)
        object.__setattr__(self, "client_id", resolved_client_id)

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