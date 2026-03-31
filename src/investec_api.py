"""Investec Programmable Banking API client."""

import base64
import logging
import time
from datetime import datetime

import httpx

from .parsers.base import StatementData, Transaction

logger = logging.getLogger(__name__)

BASE_URL = "https://openapi.investec.com"
TOKEN_URL = f"{BASE_URL}/identity/v2/oauth2/token"
API_BASE = f"{BASE_URL}/za/pb/v1"


class InvestecAPI:
    """Client for the Investec Programmable Banking API."""

    def __init__(self, client_id: str, client_secret: str, api_key: str) -> None:
        """Initialise with API credentials.

        Args:
            client_id: OAuth2 client ID.
            client_secret: OAuth2 client secret.
            api_key: Investec API key (sent as x-api-key header).
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._api_key = api_key
        self._token: str | None = None
        self._token_expires_at: float = 0
        self._client = httpx.Client(timeout=30)

    def authenticate(self) -> None:
        """Obtain a bearer token via OAuth2 client credentials grant."""
        credentials = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()

        response = self._client.post(
            TOKEN_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "x-api-key": self._api_key,
            },
            data={"grant_type": "client_credentials"},
        )
        response.raise_for_status()
        data = response.json()

        self._token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 1799) - 60

    def _ensure_authenticated(self) -> None:
        """Ensure we have a valid token, refreshing if expired."""
        if not self._token or time.time() >= self._token_expires_at:
            self.authenticate()

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make an authenticated API request with retry logic.

        Handles:
        - 401: refresh token and retry once
        - 429: honour Retry-After header and retry
        - 5xx: exponential backoff, max 3 attempts
        """
        self._ensure_authenticated()
        headers = {
            "Authorization": f"Bearer {self._token}",
            "x-api-key": self._api_key,
        }
        kwargs.setdefault("headers", {}).update(headers)

        max_retries = 3
        for attempt in range(max_retries):
            response = self._client.request(method, url, **kwargs)

            if response.status_code == 401 and attempt == 0:
                logger.info("Token expired, re-authenticating")
                self.authenticate()
                kwargs["headers"]["Authorization"] = f"Bearer {self._token}"
                continue

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 5))
                logger.warning("Rate limited, retrying after %ds", retry_after)
                time.sleep(retry_after)
                continue

            if response.status_code >= 500:
                wait = 2**attempt
                logger.warning(
                    "Server error %d, retrying in %ds", response.status_code, wait
                )
                time.sleep(wait)
                continue

            response.raise_for_status()
            return response

        response.raise_for_status()
        return response  # pragma: no cover

    def get_accounts(self) -> list[dict]:
        """List all accounts on the profile."""
        response = self._request("GET", f"{API_BASE}/accounts")
        return response.json()["data"]["accounts"]

    def get_transactions(
        self, account_id: str, from_date: str, to_date: str
    ) -> list[dict]:
        """Fetch transactions for an account within a date range."""
        response = self._request(
            "GET",
            f"{API_BASE}/accounts/{account_id}/transactions",
            params={"fromDate": from_date, "toDate": to_date},
        )
        return response.json()["data"]["transactions"]

    def fetch_as_statement_data(
        self,
        account_id: str,
        from_date: str,
        to_date: str,
        account_number: str | None = None,
    ) -> StatementData:
        """Fetch transactions and convert to StatementData format."""
        if account_number is None:
            accounts = self.get_accounts()
            for acc in accounts:
                if acc["accountId"] == account_id:
                    account_number = acc["accountNumber"]
                    break

        raw_transactions = self.get_transactions(account_id, from_date, to_date)

        transactions = []
        for tx in raw_transactions:
            amount = tx["amount"]
            if tx.get("type") == "DEBIT":
                amount = -amount

            transactions.append(Transaction(
                date=tx["transactionDate"],
                description=tx["description"],
                amount=amount,
                balance=tx.get("runningBalance"),
                raw_text=str(tx),
            ))

        statement_number = to_date[:7]

        return StatementData(
            account_number=account_number,
            statement_date=to_date,
            statement_number=statement_number,
            transactions=transactions,
        )
