"""Token persistence for Zerodha authentication."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TokenInfo:
    """Access token information."""

    access_token: str
    user_id: str
    expires_at: datetime
    api_key: str

    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.now(UTC) >= self.expires_at

    def is_valid(self) -> bool:
        """Check if token is valid (not expired and not empty)."""
        return bool(self.access_token) and not self.is_expired()

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "access_token": self.access_token,
            "user_id": self.user_id,
            "expires_at": self.expires_at.isoformat(),
            "api_key": self.api_key,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TokenInfo:
        """Create TokenInfo from dictionary."""
        return cls(
            access_token=data["access_token"],
            user_id=data["user_id"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
            api_key=data["api_key"],
        )


class TokenStore:
    """File-based token persistence for Zerodha access tokens."""

    def __init__(self, token_path: str | Path):
        """Initialize token store.

        Args:
            token_path: Path to token file
        """
        self.token_path = Path(token_path)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, token_info: TokenInfo) -> None:
        """Save token to file.

        Args:
            token_info: Token information to save
        """
        try:
            # Write to temp file first, then rename for atomicity
            temp_path = self.token_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(token_info.to_dict(), f)
            temp_path.replace(self.token_path)
            # Set restrictive permissions
            os.chmod(self.token_path, 0o600)
            logger.debug("Token saved to %s", self.token_path)
        except Exception as e:
            logger.error("Failed to save token: %s", e)
            raise

    def load(self) -> TokenInfo | None:
        """Load token from file.

        Returns:
            TokenInfo if valid token exists, None otherwise
        """
        if not self.token_path.exists():
            logger.debug("Token file does not exist: %s", self.token_path)
            return None

        try:
            with open(self.token_path) as f:
                data = json.load(f)
            token_info = TokenInfo.from_dict(data)
            logger.debug("Token loaded from %s", self.token_path)
            return token_info
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("Invalid token file, will re-authenticate: %s", e)
            return None

    def delete(self) -> None:
        """Delete token file."""
        if self.token_path.exists():
            self.token_path.unlink()
            logger.debug("Token file deleted: %s", self.token_path)

    def compute_expiry(self) -> datetime:
        """Compute token expiry (6 AM next day in UTC)."""
        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=6, minute=0, second=0, microsecond=0, tzinfo=UTC)
