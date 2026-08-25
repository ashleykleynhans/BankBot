"""Tests for the forecast, recurring, and afford CLI commands."""

import argparse
from datetime import date

import pytest

from src import main
from src.database import Database


TODAY = date(2026, 8, 25)


@pytest.fixture
def fixed_today(monkeypatch):
    """Pin 'today' so projections are deterministic."""
    monkeypatch.setattr("src.forecast._today", lambda: TODAY)


@pytest.fixture
def seeded_db(tmp_path, fixed_today):
    """Database with a recurring debit, salary income, and balance anchor."""
    database = Database(tmp_path / "cli_forecast.db")
    statement_id = database.insert_statement(
        filename="cli_seed", bank="investec", account_number="1234"
    )
    rows = []
    for day in ("06-01", "07-01", "08-01"):
        rows.append({
            "date": f"2026-{day}", "description": "NETFLIX",
            "amount": 199.00, "balance": 5000.00 if day == "08-01" else None,
            "transaction_type": "debit", "category": "entertainment",
            "recipient_or_payer": None, "reference": None, "raw_text": None,
        })
    database.insert_transactions_batch(statement_id, rows)
    return database


@pytest.fixture
def patch_db(monkeypatch, seeded_db):
    """Point the CLI's Database constructor at the seeded temp database."""
    monkeypatch.setattr(
        "src.main.Database", lambda _path: seeded_db, raising=True
    )
    return seeded_db


def make_args(**kwargs):
    """Build an argparse.Namespace with forecast command defaults."""
    defaults = {
        "command": "forecast",
        "days": 31,
        "no_burn": True,
        "buffer": 0.0,
        "account": None,
        "min_count": 3,
        "amount": None,
        "in_days": 0,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestCmdForecast:
    """Tests for the 'forecast' command."""

    def test_empty_database_exits(self, patch_db, capsys):
        empty = Database(patch_db.db_path.parent / "none.db")

        def use_empty(_path):
            return empty

        # Re-patch so the command sees an empty database
        import src.main as main_module
        original = main_module.Database
        main_module.Database = staticmethod(use_empty)
        try:
            with pytest.raises(SystemExit) as excinfo:
                main.cmd_forecast(make_args(), {"paths": {"database": "x"}})
            assert excinfo.value.code == 1
        finally:
            main_module.Database = original

    def test_no_balance_history(self, tmp_path, fixed_today, capsys):
        db = Database(tmp_path / "nobal.db")
        statement_id = db.insert_statement(filename="s", bank="fnb")
        db.insert_transactions_batch(statement_id, [{
            "date": "2026-08-01", "description": "Shop", "amount": 100.00,
            "balance": None, "transaction_type": "debit", "category": "other",
            "recipient_or_payer": None, "reference": None, "raw_text": None,
        }])
        import src.main as main_module
        original = main_module.Database
        main_module.Database = staticmethod(lambda _path: db)
        try:
            main.cmd_forecast(make_args(), {"paths": {"database": "x"}})
            out = capsys.readouterr().out
            assert "Cannot project balances" in out
            assert "No balance history available" in out
        finally:
            main_module.Database = original

    def test_happy_path_with_account_and_risks(self, patch_db, capsys):
        main.cmd_forecast(make_args(account=None), {"paths": {"database": "x"}})
        out = capsys.readouterr().out
        assert "Balance Forecast (31 days)" in out
        assert "Account: 1234" in out
        assert "End of horizon" in out
        assert "Committed monthly inflow" in out
        assert "Risk Alerts" in out

    def test_critical_risk_displayed(self, tmp_path, fixed_today, capsys):
        db = Database(tmp_path / "critical.db")
        statement_id = db.insert_statement(filename="s", bank="fnb")
        rows = [
            {
                "date": f"2026-{day}", "description": "RENT MARCH",
                "amount": 4000.00, "balance": 150.00 if day == "08-01" else None,
                "transaction_type": "debit", "category": "rent",
                "recipient_or_payer": None, "reference": None, "raw_text": None,
            }
            for day in ("06-01", "07-01", "08-01")
        ]
        db.insert_transactions_batch(statement_id, rows)
        import src.main as main_module
        original = main_module.Database
        main_module.Database = staticmethod(lambda _path: db)
        try:
            main.cmd_forecast(make_args(days=10), {"paths": {"database": "x"}})
            out = capsys.readouterr().out
            assert "drops below zero" in out
        finally:
            main_module.Database = original

    def test_buffer_warning_displayed(self, tmp_path, fixed_today, capsys):
        db = Database(tmp_path / "warn.db")
        statement_id = db.insert_statement(filename="s", bank="fnb")
        rows = [
            {
                "date": f"2026-{day}", "description": "GYM FEE",
                "amount": 200.00, "balance": 250.00 if day == "08-01" else None,
                "transaction_type": "debit", "category": "gym",
                "recipient_or_payer": None, "reference": None, "raw_text": None,
            }
            for day in ("06-01", "07-01", "08-01")
        ]
        db.insert_transactions_batch(statement_id, rows)
        import src.main as main_module
        original = main_module.Database
        main_module.Database = staticmethod(lambda _path: db)
        try:
            main.cmd_forecast(
                make_args(days=10, buffer=500.00), {"paths": {"database": "x"}}
            )
            out = capsys.readouterr().out
            assert "safety buffer" in out
        finally:
            main_module.Database = original


class TestCmdRecurring:
    """Tests for the 'recurring' command."""

    def test_empty_database_exits(self, tmp_path, fixed_today, capsys):
        db = Database(tmp_path / "empty.db")
        import src.main as main_module
        original = main_module.Database
        main_module.Database = staticmethod(lambda _path: db)
        try:
            with pytest.raises(SystemExit) as excinfo:
                main.cmd_recurring(make_args(), {"paths": {"database": "x"}})
            assert excinfo.value.code == 1
        finally:
            main_module.Database = original

    def test_no_items_found(self, tmp_path, fixed_today, capsys):
        db = Database(tmp_path / "one.db")
        statement_id = db.insert_statement(filename="s", bank="fnb")
        db.insert_transactions_batch(statement_id, [{
            "date": "2026-08-01", "description": "Shop", "amount": 100.00,
            "balance": None, "transaction_type": "debit", "category": "other",
            "recipient_or_payer": None, "reference": None, "raw_text": None,
        }])
        import src.main as main_module
        original = main_module.Database
        main_module.Database = staticmethod(lambda _path: db)
        try:
            main.cmd_recurring(make_args(), {"paths": {"database": "x"}})
            out = capsys.readouterr().out
            assert "No recurring payments detected" in out
        finally:
            main_module.Database = original

    def test_items_listed_with_totals(self, patch_db, capsys):
        main.cmd_recurring(make_args(), {"paths": {"database": "x"}})
        out = capsys.readouterr().out
        assert "Netflix" in out
        assert "monthly" in out
        assert "Estimated monthly committed outflow" in out


class TestCmdAfford:
    """Tests for the 'afford' command."""

    def test_empty_database_exits(self, tmp_path, fixed_today, capsys):
        db = Database(tmp_path / "empty.db")
        import src.main as main_module
        original = main_module.Database
        main_module.Database = staticmethod(lambda _path: db)
        try:
            with pytest.raises(SystemExit) as excinfo:
                main.cmd_afford(make_args(amount=100.00), {"paths": {"database": "x"}})
            assert excinfo.value.code == 1
        finally:
            main_module.Database = original

    def test_insufficient_data_message(self, tmp_path, fixed_today, capsys):
        db = Database(tmp_path / "nobalance.db")
        statement_id = db.insert_statement(filename="s", bank="fnb")
        db.insert_transactions_batch(statement_id, [{
            "date": "2026-08-01", "description": "Shop", "amount": 100.00,
            "balance": None, "transaction_type": "debit", "category": "other",
            "recipient_or_payer": None, "reference": None, "raw_text": None,
        }])
        import src.main as main_module
        original = main_module.Database
        main_module.Database = staticmethod(lambda _path: db)
        try:
            main.cmd_afford(make_args(amount=100.00), {"paths": {"database": "x"}})
            out = capsys.readouterr().out
            assert "No balance history available" in out
        finally:
            main_module.Database = original

    def test_affordable_verdict(self, patch_db, capsys):
        main.cmd_afford(make_args(amount=500.00), {"paths": {"database": "x"}})
        out = capsys.readouterr().out
        assert "Yes, you can afford R500.00" in out

    def test_unaffordable_verdict_lists_debits(self, patch_db, capsys):
        # R9000 overdraws even from R5,000
        main.cmd_afford(make_args(amount=9000.00), {"paths": {"database": "x"}})
        out = capsys.readouterr().out
        assert "would overdraw your account" in out

    def test_future_purchase_lists_upcoming_debits(self, patch_db, capsys):
        # Netflix debits Aug 31, before a purchase seven days out
        main.cmd_afford(
            make_args(amount=6000.00, in_days=7), {"paths": {"database": "x"}}
        )
        out = capsys.readouterr().out
        assert "Debits scheduled before the purchase" in out
        assert "Netflix" in out
