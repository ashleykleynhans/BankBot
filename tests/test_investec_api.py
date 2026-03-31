"""Tests for Investec API client."""

import time
from unittest.mock import patch, MagicMock

import pytest

from src.investec_api import InvestecAPI
from src.parsers.base import StatementData


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


class TestGetAccounts:
    """Tests for listing accounts."""

    def test_get_accounts(self, api):
        """Test fetching accounts list."""
        api._token = "test_token"
        api._token_expires_at = time.time() + 600

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "accounts": [
                    {
                        "accountId": "abc123",
                        "accountNumber": "10014670887",
                        "accountName": "Private Bank Account",
                        "referenceName": "My Account",
                        "productName": "Private Bank Account",
                    }
                ]
            }
        }

        with patch.object(api, "_request", return_value=mock_response):
            accounts = api.get_accounts()

        assert len(accounts) == 1
        assert accounts[0]["accountId"] == "abc123"
        assert accounts[0]["accountNumber"] == "10014670887"


class TestGetTransactions:
    """Tests for fetching transactions."""

    def test_get_transactions(self, api):
        """Test fetching transactions for an account."""
        api._token = "test_token"
        api._token_expires_at = time.time() + 600

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "transactions": [
                    {
                        "accountId": "abc123",
                        "type": "DEBIT",
                        "description": "KEANU PAYMENT",
                        "transactionDate": "2026-01-13",
                        "amount": 502.00,
                        "runningBalance": 3042.00,
                    },
                    {
                        "accountId": "abc123",
                        "type": "CREDIT",
                        "description": "TRANSFER FNB",
                        "transactionDate": "2026-01-13",
                        "amount": 3544.00,
                        "runningBalance": 3544.00,
                    },
                ]
            }
        }

        with patch.object(api, "_request", return_value=mock_response):
            transactions = api.get_transactions("abc123", "2026-01-01", "2026-01-31")

        assert len(transactions) == 2
        assert transactions[0]["description"] == "KEANU PAYMENT"


class TestFetchAsStatementData:
    """Tests for converting API response to StatementData."""

    def test_fetch_as_statement_data(self, api):
        """Test conversion to StatementData format."""
        api._token = "test_token"
        api._token_expires_at = time.time() + 600

        mock_tx_response = MagicMock()
        mock_tx_response.status_code = 200
        mock_tx_response.json.return_value = {
            "data": {
                "transactions": [
                    {
                        "accountId": "abc123",
                        "type": "DEBIT",
                        "description": "KEANU PAYMENT",
                        "transactionDate": "2026-01-13",
                        "amount": 502.00,
                        "runningBalance": 3042.00,
                    },
                ]
            }
        }

        with patch.object(api, "_request", return_value=mock_tx_response):
            result = api.fetch_as_statement_data(
                "abc123", "2026-01-01", "2026-01-31", account_number="10014670887"
            )

        assert isinstance(result, StatementData)
        assert result.account_number == "10014670887"
        assert result.statement_date == "2026-01-31"
        assert result.statement_number == "2026-01"
        assert len(result.transactions) == 1

        tx = result.transactions[0]
        assert tx.date == "2026-01-13"
        assert tx.description == "KEANU PAYMENT"
        assert tx.amount == -502.00
        assert tx.balance == 3042.00
