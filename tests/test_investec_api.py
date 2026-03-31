"""Tests for Investec API client."""

import time
from unittest.mock import patch, MagicMock

import pytest

from src.investec_api import InvestecAPI


@pytest.fixture
def api():
    """Create an API client with test credentials."""
    return InvestecAPI(
        client_id="test_client_id",
        client_secret="test_client_secret",
        api_key="test_api_key",
    )


class TestAuthentication:
    """Tests for OAuth2 authentication."""

    def test_authenticate_success(self, api):
        """Test successful authentication."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token_123",
            "token_type": "Bearer",
            "expires_in": 1799,
        }

        with patch.object(api._client, "post", return_value=mock_response):
            api.authenticate()

        assert api._token == "test_token_123"

    def test_authenticate_failure(self, api):
        """Test authentication failure raises error."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid credentials"
        mock_response.raise_for_status.side_effect = Exception("401 Unauthorized")

        with patch.object(api._client, "post", return_value=mock_response):
            with pytest.raises(Exception, match="401"):
                api.authenticate()

    def test_token_cached(self, api):
        """Test that token is reused when not expired."""
        api._token = "cached_token"
        api._token_expires_at = time.time() + 600

        with patch.object(api._client, "post") as mock_post:
            api._ensure_authenticated()
            mock_post.assert_not_called()

    def test_token_refreshed_when_expired(self, api):
        """Test that token is refreshed when expired."""
        api._token = "old_token"
        api._token_expires_at = time.time() - 10

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "token_type": "Bearer",
            "expires_in": 1799,
        }

        with patch.object(api._client, "post", return_value=mock_response):
            api._ensure_authenticated()

        assert api._token == "new_token"
