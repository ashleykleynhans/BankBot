"""Tests for the forecast REST endpoints."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.database import Database
from src.forecast import ForecastEngine

TODAY = date(2026, 8, 25)


def seed_transactions(db: Database, rows: list[dict]) -> None:
    """Insert transaction rows under a single synthetic statement."""
    statement_id = db.insert_statement(
        filename="forecast_api_test", bank="investec", account_number="1234"
    )
    prepared = [
        {
            "date": row["date"],
            "description": row["description"],
            "amount": abs(row["amount"]),
            "balance": row.get("balance"),
            "transaction_type": row["transaction_type"],
            "category": row.get("category"),
            "recipient_or_payer": None,
            "reference": None,
            "raw_text": None,
        }
        for row in rows
    ]
    db.insert_transactions_batch(statement_id, prepared)


@pytest.fixture
def fixed_today(monkeypatch):
    """Pin 'today' so projections are deterministic."""
    monkeypatch.setattr("src.forecast._today", lambda: TODAY)


@pytest.fixture
def seeded_db(tmp_path, fixed_today):
    """Database with recurring debit and salary, plus a balance anchor.

    Every transaction belongs to a recurring group, so the daily burn rate
    is exactly zero and projections stay deterministic.
    """
    db = Database(tmp_path / "api_forecast.db")
    rows = [
        {"date": "2026-06-01", "description": "NETFLIX", "amount": 199.00,
         "transaction_type": "debit", "category": "entertainment"},
        {"date": "2026-07-01", "description": "NETFLIX", "amount": 199.00,
         "transaction_type": "debit", "category": "entertainment"},
        {"date": "2026-08-01", "description": "NETFLIX", "amount": 199.00,
         "transaction_type": "debit", "category": "entertainment", "balance": 5000.00},
        {"date": "2026-06-25", "description": "SALARY ACME", "amount": 20000.00,
         "transaction_type": "credit", "category": "salary"},
        {"date": "2026-07-25", "description": "SALARY ACME", "amount": 20000.00,
         "transaction_type": "credit", "category": "salary"},
        {"date": "2026-08-25", "description": "SALARY ACME", "amount": 20000.00,
         "transaction_type": "credit", "category": "salary"},
    ]
    seed_transactions(db, rows)
    return db


@pytest.fixture
def client(seeded_db):
    """Test client backed by a real temp database."""
    app = create_app()
    app.state.db = seeded_db
    app.state.config = {"paths": {"database": str(seeded_db.db_path)}}
    return TestClient(app)


class TestRecurringEndpoint:
    """Tests for GET /api/v1/forecast/recurring."""

    def test_lists_recurring_items(self, client):
        response = client.get("/api/v1/forecast/recurring")
        assert response.status_code == 200
        data = response.json()
        keys = [item["key"] for item in data["items"]]
        assert "netflix" in keys
        netflix = next(i for i in data["items"] if i["key"] == "netflix")
        assert netflix["cadence"] == "monthly"
        assert netflix["direction"] == "out"
        assert netflix["next_date"] > TODAY.isoformat()

    def test_totals_are_summed(self, client):
        response = client.get("/api/v1/forecast/recurring")
        data = response.json()
        assert data["total_monthly_outflow"] > 0

    def test_min_count_validation(self, client):
        response = client.get("/api/v1/forecast/recurring?min_count=1")
        assert response.status_code == 422


class TestBalanceForecastEndpoint:
    """Tests for GET /api/v1/forecast/balance."""

    def test_returns_projection(self, client):
        response = client.get("/api/v1/forecast/balance?days=14&include_burn=false")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 14
        assert data["start_balance"] == 5000.00
        # Anchor point + catch-up days (anchor Aug 1 -> today Aug 25) + horizon
        assert len(data["points"]) == 39
        # Netflix lands 2026-09-01 within the horizon
        dropped = [p for p in data["points"] if p["date"] >= "2026-09-01"]
        assert all(p["balance"] == pytest.approx(4801.00) for p in dropped)

    def test_risks_present(self, client):
        response = client.get("/api/v1/forecast/balance?days=7&include_burn=false")
        data = response.json()
        assert len(data["risks"]) >= 1

    def test_days_validation(self, client):
        assert client.get("/api/v1/forecast/balance?days=0").status_code == 422
        assert client.get("/api/v1/forecast/balance?days=401").status_code == 422

    def test_empty_database(self, tmp_path):
        db = Database(tmp_path / "empty.db")
        app = create_app()
        app.state.db = db
        test_client = TestClient(app)
        response = test_client.get("/api/v1/forecast/balance")
        assert response.status_code == 200
        data = response.json()
        assert data["start_balance"] is None
        assert data["risks"][0]["severity"] == "info"


class TestAffordabilityEndpoint:
    """Tests for GET /api/v1/forecast/afford."""

    def test_affordable(self, client):
        response = client.get("/api/v1/forecast/afford?amount=1000&days_ahead=0")
        assert response.status_code == 200
        data = response.json()
        assert data["affordable"] is True
        assert data["amount"] == 1000.0
        assert data["lowest_balance_after"] == pytest.approx(3801.00)

    def test_not_affordable(self, client):
        response = client.get("/api/v1/forecast/afford?amount=6000&days_ahead=0")
        data = response.json()
        assert data["affordable"] is False
        assert "short" in data["reason"]

    def test_future_date(self, client):
        target = (TODAY + timedelta(days=3)).isoformat()
        response = client.get("/api/v1/forecast/afford?amount=50&days_ahead=3")
        data = response.json()
        assert data["target_date"] == target
        assert data["affordable"] is True

    def test_amount_must_be_positive(self, client):
        response = client.get("/api/v1/forecast/afford?amount=-5")
        assert response.status_code == 422
