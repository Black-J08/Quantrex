"""Tests for ZerodhaAuth login flow and token management."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from quantrex_data.providers.zerodha_provider.auth import ZerodhaAuth
from quantrex_data.providers.zerodha_provider.config import ZerodhaProviderConfig
from quantrex_data.providers.zerodha_provider.exceptions import ZerodhaAuthenticationError
from quantrex_test_support.zerodha import MOCK_AUTH_SUCCESS_RESPONSE, MOCK_USER_PROFILE_RESPONSE


class TestZerodhaAuth:
    """Tests for ZerodhaAuth."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create a test config."""
        return ZerodhaProviderConfig(
            api_key="test_key",
            api_secret="test_secret",
            token_file=tmp_path / "access_token",
            instrument_token="5633",
            exchange="NSE",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

    @pytest.fixture
    def mock_client(self):
        """Create a mock ZerodhaAPIClient."""
        client = Mock()
        client._request = Mock()
        client.update_access_token = Mock()
        return client

    def test_get_login_url(self, config):
        """Auth should generate correct login URL."""
        auth = ZerodhaAuth(config)
        url = auth.get_login_url()
        assert url == "https://kite.zerodha.com/connect/login?v=3&api_key=test_key"

    def test_calculate_checksum(self, config):
        """Auth should calculate correct SHA256 checksum."""
        auth = ZerodhaAuth(config)
        request_token = "test_request_token"
        checksum = auth.calculate_checksum(request_token)
        # Verify it's a valid hex string of correct length (SHA256 = 64 hex chars)
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_exchange_request_token_success(self, config, mock_client):
        """Auth should exchange request_token for access_token successfully."""
        auth = ZerodhaAuth(config)
        mock_client._request.return_value = MOCK_AUTH_SUCCESS_RESPONSE

        access_token = auth.exchange_request_token("test_request_token", mock_client)

        assert access_token == "test_access_token_12345"
        mock_client._request.assert_called_once()
        # Verify the payload contains api_key, request_token, and checksum
        call_args = mock_client._request.call_args
        assert call_args[1]["data"]["api_key"] == "test_key"
        assert call_args[1]["data"]["request_token"] == "test_request_token"
        assert "checksum" in call_args[1]["data"]

    def test_exchange_request_token_failure(self, config, mock_client):
        """Auth should raise on failed token exchange."""
        auth = ZerodhaAuth(config)
        mock_client._request.return_value = {"status": "error", "message": "Invalid request_token"}

        with pytest.raises(ZerodhaAuthenticationError):
            auth.exchange_request_token("bad_token", mock_client)

    def test_save_and_load_access_token(self, config):
        """Auth should save and load access token from file."""
        auth = ZerodhaAuth(config)
        token = "test_access_token_12345"

        auth.save_access_token(token)
        loaded = auth.load_access_token()

        assert loaded == token
        assert config.token_file.read_text().strip() == token

    def test_load_access_token_missing_file(self, config):
        """Auth should return None for missing token file."""
        auth = ZerodhaAuth(config)
        # Don't create the file
        loaded = auth.load_access_token()
        assert loaded is None

    def test_validate_token_success(self, config, mock_client):
        """Auth should validate token successfully."""
        auth = ZerodhaAuth(config)
        mock_client.get_profile.return_value = MOCK_USER_PROFILE_RESPONSE["data"]

        result = auth.validate_token(mock_client)

        assert result is True
        mock_client.get_profile.assert_called_once()

    def test_validate_token_failure(self, config, mock_client):
        """Auth should return False for invalid token."""
        auth = ZerodhaAuth(config)
        from quantrex_data.providers.zerodha_provider.exceptions import ZerodhaAuthenticationError
        mock_client.get_profile.side_effect = ZerodhaAuthenticationError("Token expired")

        result = auth.validate_token(mock_client)

        assert result is False

    def test_ensure_valid_token_loads_existing(self, config, mock_client):
        """Auth should load and validate existing token."""
        auth = ZerodhaAuth(config)
        # Pre-save a token
        auth.save_access_token("existing_token")
        mock_client.get_profile.return_value = MOCK_USER_PROFILE_RESPONSE["data"]

        token = auth.ensure_valid_token(mock_client)

        assert token == "existing_token"
        mock_client.update_access_token.assert_called_with("existing_token")
        mock_client.get_profile.assert_called_once()

    def test_ensure_valid_token_triggers_login_flow(self, config, mock_client):
        """Auth should trigger login flow when no valid token exists."""
        auth = ZerodhaAuth(config)
        # No token file exists
        mock_client.get_profile.side_effect = ZerodhaAuthenticationError("Token expired")
        mock_client._request.return_value = MOCK_AUTH_SUCCESS_RESPONSE

        with patch("builtins.input", return_value="test_request_token"):
            token = auth.ensure_valid_token(mock_client)

        assert token == "test_access_token_12345"
        # Should have saved the new token
        assert config.token_file.read_text().strip() == "test_access_token_12345"