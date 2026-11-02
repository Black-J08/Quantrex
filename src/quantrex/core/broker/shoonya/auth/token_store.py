"""Token persistence for Shoonya authentication."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TokenInfo:
    """Access token information for Shoonya.

    Shoonya tokens have no automatic expiry (valid until logout/revocation),
    so is_valid() checks only that the token is non-empty and is_expired()
    always returns False.
    """

    access_token: str
    user_id: str
    expires_at: datetime
    api_key: str

    def is_expired(self) -> bool:
        """Check if token is expired.

        Shoonya tokens do not auto-expire, so this always returns False.
        """
        return False

    def is_valid(self) -> bool:
        """Check if token is valid (not empty and not expired)."""
        return bool(self.access_token) and not self.is_expired()

    def to_dict(self) -> dict[str, str]:
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
    """File-based token persistence for Shoonya access tokens."""

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

        Raises:
            OSError: If the token cannot be written to disk.
        """
        try:
            # Write to temp file first, then rename for atomicity
            temp_path = self.token_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(token_info.to_dict(), f)
            temp_path.replace(self.token_path)
            # Set restrictive permissions
            os.chmod(self.token_path, 0o600)
            logger.debug("Saved token to %s", self.token_path)
        except Exception:
            logger.exception("Failed to save token to %s", self.token_path)
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
            logger.debug("Loaded token from %s", self.token_path)
            return token_info
        except (json.JSONDecodeError, KeyError, ValueError, OSError) as e:
            logger.warning("Failed to load token from %s: %s", self.token_path, e)
            return None

    def delete(self) -> None:
        """Delete the token file if it exists."""
        if self.token_path.exists():
            self.token_path.unlink()
            logger.debug("Deleted token file: %s", self.token_path)

    def compute_expiry(self) -> datetime:
        """Compute token expiry.

        Shoonya tokens have no automatic expiry, so this returns a
        far-future sentinel (1 year from now).
        """
        return datetime.now(UTC).replace(
            year=datetime.now(UTC).year + 1
        )
