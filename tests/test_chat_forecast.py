"""Tests for deterministic forecast answers in the chat interface."""

from datetime import date, datetime
from unittest.mock import Mock

import pytest

from src.chat import ChatInterface
from src.database import Database
from src.llm_backend import LLMBackend
from src.forecast import ForecastEngine

TODAY = date(2026, 8, 25)


@pytest.fixture
def fixed_today(monkeypatch):
    """Pin 'today' so projections are deterministic."""
    monkeypatch.setattr("src.forecast._today", lambda: TODAY)


@pytest.fixture
def db(tmp_path, fixed_today):
    """Real database seeded with a recurring debit and salary income."""
    database = Database(tmp_path / "chat_forecast.db")
    statement_id = database.insert_statement(
        filename="chat_seed", bank="investec", account_number="1234"
    )
    rows = []
    for day in ("06-01", "07-01", "08-01"):
        balance = 5000.00 if day == "08-01" else None
        rows.append({
            "date": f"2026-{day}", "description": "NETFLIX",
            "amount": 199.00, "balance": balance,
            "transaction_type": "debit", "category": "entertainment",
            "recipient_or_payer": None, "reference": None, "raw_text": None,
        })
    for day in ("06-25", "07-25", "08-25"):
        rows.append({
            "date": f"2026-{day}", "description": "SALARY ACME",
            "amount": 20000.00, "balance": None,
            "transaction_type": "credit", "category": "salary",
            "recipient_or_payer": None, "reference": None, "raw_text": None,
        })
    database.insert_transactions_batch(statement_id, rows)
    return database


@pytest.fixture
def backend():
    return Mock(spec=LLMBackend)


@pytest.fixture
def chat(db, backend):
    """Chat interface over the seeded database."""
    return ChatInterface(db, backend=backend)


class TestParseAffordTiming:
    """Tests for extracting when an expense happens."""

    def test_in_days(self, chat):
        days, remainder = chat._parse_afford_timing("can i afford r100 in 3 days")
        assert days == 3
        assert "in 3 days" not in remainder

    def test_in_weeks(self, chat):
        days, _ = chat._parse_afford_timing("can i afford r100 in 2 weeks")
        assert days == 14

    def test_next_month(self, chat):
        days, _ = chat._parse_afford_timing("can i afford r100 next month")
        assert days == 30

    def test_next_week(self, chat):
        days, remainder = chat._parse_afford_timing("can i afford r100 next week")
        assert days == 7
        assert "next week" not in remainder

    def test_tomorrow(self, chat):
        days, _ = chat._parse_afford_timing("can i afford r100 tomorrow")
        assert days == 1

    def test_weekday(self, chat):
        days, remainder = chat._parse_afford_timing("can i afford r100 by friday")
        expected = (4 - datetime.now().weekday()) % 7
        assert days == expected
        assert "friday" not in remainder

    def test_no_timing(self, chat):
        days, _ = chat._parse_afford_timing("can i afford r100")
        assert days is None


class TestParseAffordAmount:
    """Tests for extracting the expense amount."""

    def test_currency_prefix(self, chat):
        assert chat._parse_afford_amount("r500") == 500.0

    def test_thousands_separator(self, chat):
        assert chat._parse_afford_amount("r1,500.50") == 1500.50

    def test_plain_number(self, chat):
        assert chat._parse_afford_amount("spend 250") == 250.0

    def test_none_when_absent(self, chat):
        assert chat._parse_afford_amount("can i afford it") is None


class TestAffordAnswers:
    """Tests for 'can I afford' deterministic answers."""

    def test_affordable_purchase(self, chat, backend):
        response, txns, stats = chat.ask("Can I afford R500?")
        assert response.startswith("Yes, you can afford R500.00.")
        assert txns == []
        assert stats is None
        backend.chat_completion.assert_not_called()

    def test_unaffordable_purchase(self, chat):
        response, _, _ = chat.ask("Can I afford R9000 tomorrow?")
        assert response.startswith("No, spending R9,000.00")

    def test_upcoming_debits_listed(self, chat):
        # Netflix debits on Aug 31, before a purchase next week (Sep 1)
        response, _, _ = chat.ask("Can I afford R100 next week?")
        assert "Coming up before then: Netflix" in response

    def test_no_amount_prompts_for_one(self, chat):
        response, txns, _ = chat.ask("Can I afford it?")
        assert "Tell me the amount" in response
        assert txns == []

    def test_no_balance_history_returns_reason(self, tmp_path, fixed_today):
        from src.database import Database as RealDatabase

        empty_db = RealDatabase(tmp_path / "empty.db")
        empty_chat = ChatInterface(empty_db, backend=Mock(spec=LLMBackend))
        response, txns, _ = empty_chat.ask("Can I afford R100?")
        assert "No balance history available" in response
        assert txns == []

    def test_non_afford_queries_ignored(self, chat):
        assert chat._handle_afford_query("how much did I spend?") is None


class TestRecurringAnswers:
    """Tests for recurring payment questions."""

    def test_lists_detected_items(self, chat):
        response, _, stats = chat.ask("What are my recurring payments?")
        assert "Netflix" in response
        assert "199.00" in response
        assert "monthly" in response
        assert stats is None

    def test_mentions_regular_income(self, chat):
        response, _, _ = chat.ask("What regular payments do I have?")
        assert "Regular income detected" in response
        # Monthly-equivalent: 20,000 * 30.44 / 30
        assert "20,293.33" in response

    def test_empty_history(self, db, backend):
        empty_chat = ChatInterface(Database(db.db_path.parent / "empty.db"), backend=backend)
        response, txns, _ = empty_chat.ask("What are my recurring payments?")
        assert "couldn't find any recurring payments" in response
        assert txns == []


class TestForecastSummaryAnswers:
    """Tests for balance forecast questions."""

    def test_summary_includes_key_numbers(self, chat):
        response, _, stats = chat.ask("What does my balance forecast look like?")
        assert "R5,000.00" in response
        assert "31 days" in response
        assert stats is None

    def test_warning_surfaced_when_overdrawn(self, tmp_path, fixed_today):
        from src.database import Database as RealDatabase

        db = RealDatabase(tmp_path / "tight.db")
        statement_id = db.insert_statement(
            filename="tight_seed", bank="investec", account_number="1234"
        )
        rows = [
            {
                "date": "2026-06-01", "description": "NETFLIX", "amount": 199.00,
                "balance": None, "transaction_type": "debit",
                "category": "entertainment", "recipient_or_payer": None,
                "reference": None, "raw_text": None,
            },
            {
                "date": "2026-07-01", "description": "NETFLIX", "amount": 199.00,
                "balance": None, "transaction_type": "debit",
                "category": "entertainment", "recipient_or_payer": None,
                "reference": None, "raw_text": None,
            },
            {
                "date": "2026-08-01", "description": "NETFLIX", "amount": 199.00,
                "balance": 150.00, "transaction_type": "debit",
                "category": "entertainment", "recipient_or_payer": None,
                "reference": None, "raw_text": None,
            },
        ]
        db.insert_transactions_batch(statement_id, rows)
        tight_chat = ChatInterface(db, backend=Mock(spec=LLMBackend))
        response, _, _ = tight_chat.ask("Will I run out of money?")
        assert "Warning:" in response
        assert "drops below zero" in response

    def test_no_balance_history_returns_risk_message(self, tmp_path, fixed_today):
        from src.database import Database as RealDatabase

        empty_db = RealDatabase(tmp_path / "empty2.db")
        empty_chat = ChatInterface(empty_db, backend=Mock(spec=LLMBackend))
        response, txns, _ = empty_chat.ask("What is my forecast?")
        assert "No balance history available" in response
        assert txns == []


class TestHandlerOrdering:
    """Forecast handlers run before transaction search and the LLM."""

    def test_backend_never_called_for_forecast_intents(self, chat, backend):
        for query in (
            "Can I afford R300?",
            "what are my debit orders",
            "balance forecast please",
        ):
            chat.ask(query)
        assert backend.chat_completion.call_count == 0

    def test_interactive_loop_uses_deterministic_answers(self, chat, backend):
        """The interactive _process_query path also bypasses search and LLM."""
        chat._process_query("Can I afford R500?")
        assert chat._last_transactions == []
        backend.chat_completion.assert_not_called()

    def test_format_date_words_invalid_date(self, chat):
        assert chat._format_date_words("not-a-date") == "not-a-date"

    def test_recurring_more_than_eight_listed(self, chat, fixed_today):
        """Recurring answers summarize when more than eight items exist."""
        items = [
            {
                "key": f"merchant{i}", "merchant": f"Merchant {i}",
                "description_sample": f"Merchant {i}", "category": None,
                "direction": "out", "cadence": "monthly", "interval_days": 30,
                "typical_amount": 100.00 + i, "last_amount": 100.00 + i,
                "last_date": "2026-08-01", "next_date": "2026-09-01",
                "occurrences": 4, "confidence": "high", "active": True,
                "monthly_equivalent": 100.00 + i,
            }
            for i in range(10)
        ]

        class StubEngine:
            def detect_recurring(self, **kwargs):
                return items

        chat._forecast_engine = StubEngine()
        response, txns, _ = chat.ask("What are my recurring payments?")
        assert "... and 2 more." in response
        assert txns == []
