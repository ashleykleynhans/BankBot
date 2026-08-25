"""Tests for the cashflow forecasting engine."""

from datetime import date, timedelta

import pytest

from src.database import Database
from src.forecast import (
    ForecastEngine,
    _classify_cadence,
    _parse_date,
    display_name,
    normalize_description,
)

TODAY = date(2026, 8, 25)


@pytest.fixture
def db(tmp_path):
    """Create a real database in a temp directory."""
    return Database(tmp_path / "forecast.db")


@pytest.fixture
def fixed_today(monkeypatch):
    """Pin 'today' so projections are deterministic."""
    monkeypatch.setattr("src.forecast._today", lambda: TODAY)
    return TODAY


def tx_row(date_str, description, amount, tx_type, balance=None, category="other"):
    """Build a transaction dict shaped like a database row."""
    return {
        "date": date_str,
        "description": description,
        "amount": amount,
        "balance": balance,
        "transaction_type": tx_type,
        "category": category,
        "recipient_or_payer": None,
        "reference": None,
        "id": 0,
    }


def account_tx(date_str, description, amount, tx_type, account, balance=None):
    """Transaction row tagged with an explicit bank account."""
    row = tx_row(date_str, description, amount, tx_type, balance=balance)
    row["account_number"] = account
    return row


def seed(db, rows, account_number="1234"):
    """Insert rows into the database under one synthetic statement."""
    if not any(
        s.get("account_number") == account_number for s in db.get_all_statements()
    ):
        statement_id = db.insert_statement(
            filename=f"stmt_{account_number}_{len(db.get_all_statements())}",
            bank="investec",
            account_number=account_number,
            statement_date=rows[-1]["date"] if rows else None,
        )
    else:
        statement_id = db.get_all_statements()[0]["id"]
    prepared = []
    for row in rows:
        prepared.append({
            "date": row["date"],
            "description": row["description"],
            "amount": abs(row["amount"]),
            "balance": row["balance"],
            "transaction_type": row["transaction_type"],
            "category": row["category"],
            "recipient_or_payer": None,
            "reference": None,
            "raw_text": None,
        })
    db.insert_transactions_batch(statement_id, prepared)


class TestNormalizeDescription:
    """Tests for description normalization."""

    def test_strips_numbers_and_noise(self):
        assert normalize_description("POS Purchase Netflix.Com 2410") == "netflix"

    def test_case_insensitive_grouping(self):
        assert normalize_description("NETFLIX.COM") == normalize_description("netflix.com")

    def test_removes_digit_tokens(self):
        assert normalize_description("DEBIT ORDER CITY OF CTW 55001234") == "city of ctw"

    def test_empty_description(self):
        assert normalize_description("12345 678") == ""

    def test_display_name(self):
        assert display_name("netflix") == "Netflix"
        assert display_name("city of ctw") == "City Of Ctw"
        assert display_name("") == "Unknown"


class TestParseDate:
    """Tests for ISO date parsing."""

    def test_parses_iso_string(self):
        assert _parse_date("2026-08-25") == TODAY

    def test_truncates_timestamp(self):
        assert _parse_date("2026-08-25T10:30:00") == TODAY

    def test_invalid_string_returns_none(self):
        assert _parse_date("not-a-date") is None

    def test_none_returns_none(self):
        assert _parse_date(None) is None


class TestClassifyCadence:
    """Tests for interval cadence classification."""

    def test_monthly(self):
        result = _classify_cadence([30, 31, 28])
        assert result is not None
        name, interval = result
        assert name == "monthly"
        assert interval in range(25, 39)

    def test_weekly(self):
        result = _classify_cadence([7, 7, 7])
        assert result == ("weekly", 7)

    def test_fortnightly(self):
        result = _classify_cadence([14, 14, 15])
        assert result[0] == "fortnightly"

    def test_irregular_rejected(self):
        assert _classify_cadence([5, 40, 12]) is None

    def test_quarterly_not_classified(self):
        assert _classify_cadence([90, 91, 90]) is None


class TestDetectRecurring:
    """Tests for recurring payment detection."""

    def test_detects_monthly_subscription(self, db, fixed_today):
        rows = [
            tx_row("2026-05-01", "NETFLIX.COM 8801", 199.00, "debit"),
            tx_row("2026-06-01", "Netflix.Com", 199.00, "debit"),
            tx_row("2026-07-01", "NETFLIX COM", 209.00, "debit"),
            tx_row("2026-08-03", "POS Purchase Netflix.Com", 209.00, "debit"),
        ]
        seed(db, rows)
        items = ForecastEngine(db).detect_recurring()

        netflix = [i for i in items if i["key"] == "netflix"]
        assert len(netflix) == 1
        item = netflix[0]
        assert item["cadence"] == "monthly"
        assert item["direction"] == "out"
        # median of [199, 199, 209, 209]
        assert item["typical_amount"] == 204.00
        assert item["last_amount"] == 209.00
        assert item["occurrences"] == 4
        assert item["next_date"] == "2026-09-03"

    def test_detects_monthly_salary_as_income(self, db, fixed_today):
        rows = [
            tx_row("2026-06-25", "SALARY CHEMCORP", 32000.00, "credit", category="salary"),
            tx_row("2026-07-27", "SALARY CHEMCORP", 32000.00, "credit", category="salary"),
            tx_row("2026-08-25", "SALARY CHEMCORP", 33000.00, "credit", category="salary"),
        ]
        seed(db, rows)
        items = ForecastEngine(db).detect_recurring()

        salary = [i for i in items if i["direction"] == "in"]
        assert len(salary) == 1
        assert salary[0]["cadence"] == "monthly"
        assert salary[0]["next_date"] > fixed_today.isoformat()

    def test_next_date_rolls_past_today(self, db, fixed_today):
        # Last payment was over a month ago; prediction must land after today
        rows = [
            tx_row("2026-04-01", "Gym Monthly", 350.00, "debit", category="gym"),
            tx_row("2026-05-01", "Gym Monthly", 350.00, "debit", category="gym"),
            tx_row("2026-06-01", "Gym Monthly", 350.00, "debit", category="gym"),
        ]
        seed(db, rows)
        items = ForecastEngine(db).detect_recurring()
        assert items[0]["next_date"] > TODAY.isoformat()
        assert date.fromisoformat(items[0]["next_date"]) <= TODAY + timedelta(days=35)

    def test_irregular_transactions_not_detected(self, db, fixed_today):
        rows = [
            tx_row("2026-03-02", "Woolworths Food", 450.00, "debit"),
            tx_row("2026-03-19", "Woolworths Food", 220.00, "debit"),
            tx_row("2026-06-11", "Woolworths Food", 680.00, "debit"),
            tx_row("2026-08-14", "Woolworths Food", 310.00, "debit"),
        ]
        seed(db, rows)
        assert ForecastEngine(db).detect_recurring() == []

    def test_min_occurrences_respected(self, db, fixed_today):
        rows = [
            tx_row("2026-07-01", "Streaming Service", 99.00, "debit"),
            tx_row("2026-08-01", "Streaming Service", 99.00, "debit"),
        ]
        seed(db, rows)
        assert ForecastEngine(db).detect_recurring(min_occurrences=3) == []

    def test_weekly_cadence(self, db, fixed_today):
        rows = []
        monday = date(2026, 7, 27)
        for week in range(5):
            rows.append(
                tx_row((monday + timedelta(weeks=week)).isoformat(), "Virgin Active", 420.00, "debit")
            )
        seed(db, rows)
        items = ForecastEngine(db).detect_recurring()
        assert items[0]["cadence"] == "weekly"
        assert items[0]["interval_days"] == 7

    def test_confidence_medium_when_amounts_vary(self, db, fixed_today):
        rows = [
            tx_row("2026-06-05", "City Power", 400.00, "debit"),
            tx_row("2026-07-06", "City Power", 550.00, "debit"),
            tx_row("2026-08-05", "City Power", 450.00, "debit"),
        ]
        seed(db, rows)
        items = ForecastEngine(db).detect_recurring(max_interval_deviation=5)
        assert items[0]["confidence"] == "medium"

    def test_confidence_low_when_amounts_wildly_vary(self, db, fixed_today):
        rows = [
            tx_row("2026-06-05", "Prepaid Electricity", 100.00, "debit"),
            tx_row("2026-07-06", "Prepaid Electricity", 900.00, "debit"),
            tx_row("2026-08-05", "Prepaid Electricity", 200.00, "debit"),
        ]
        seed(db, rows)
        items = ForecastEngine(db).detect_recurring(max_interval_deviation=5)
        assert items[0]["confidence"] == "low"

    def test_stale_subscriptions_marked_inactive(self, db, fixed_today):
        # Weekly payments that stopped months ago are not active commitments
        rows = [
            tx_row("2026-03-02", "Takealot Weekly", 500.00, "debit"),
            tx_row("2026-03-09", "Takealot Weekly", 500.00, "debit"),
            tx_row("2026-03-16", "Takealot Weekly", 500.00, "debit"),
        ]
        seed(db, rows)
        items = ForecastEngine(db).detect_recurring()
        assert len(items) == 1
        assert items[0]["active"] is False

    def test_recent_items_marked_active(self, db, fixed_today):
        rows = [
            tx_row("2026-06-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-07-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-08-01", "NETFLIX", 199.00, "debit"),
        ]
        seed(db, rows)
        items = ForecastEngine(db).detect_recurring()
        assert items[0]["active"] is True

    def test_projection_ignores_inactive_items(self, db, fixed_today):
        rows = [
            tx_row("2026-06-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-07-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-08-01", "NETFLIX", 199.00, "debit"),
            # Stopped weekly debit: recent enough to detect (< 12 months),
            # but inactive (> 3 weekly intervals since the last payment)
            tx_row("2026-03-02", "Old Gym", 300.00, "debit", category="gym"),
            tx_row("2026-03-09", "Old Gym", 300.00, "debit", category="gym"),
            tx_row("2026-03-16", "Old Gym", 300.00, "debit", category="gym"),
            # Balance anchor with no amount (excluded from detection)
            tx_row("2026-08-15", "Anchor Txn", 0, "credit", balance=1000.00),
        ]
        seed(db, rows)
        forecast = ForecastEngine(db).project(days=10, include_burn=False)
        # Only Netflix projects forward: R199 debit lands 2026-08-31
        assert forecast["end_balance"] == pytest.approx(801.00)
        assert forecast["recurring_count"] == 1

    def test_recurring_older_than_twelve_months_excluded(self, db, fixed_today):
        # Monthly payments that stopped 14 months ago are ignored entirely
        rows = [
            tx_row("2025-04-01", "Ancient Sub", 99.00, "debit"),
            tx_row("2025-05-01", "Ancient Sub", 99.00, "debit"),
            tx_row("2025-06-01", "Ancient Sub", 99.00, "debit"),
        ]
        seed(db, rows)
        assert ForecastEngine(db).detect_recurring() == []

    def test_recurring_within_twelve_months_included(self, db, fixed_today):
        # Last payment ~11 months ago is still within the window
        inside_window = TODAY - timedelta(days=340)
        rows = []
        for months_back in range(2, -1, -1):
            day = inside_window - timedelta(days=30 * months_back)
            rows.append(
                tx_row(day.isoformat(), "Still Going", 250.00, "debit")
            )
        seed(db, rows)
        items = ForecastEngine(db).detect_recurring()
        assert len(items) == 1
        assert items[0]["merchant"] == "Still Going"

    def test_sorted_by_monthly_equivalent(self, db, fixed_today):
        rows = [
            tx_row("2026-06-01", "Cheap Sub", 50.00, "debit"),
            tx_row("2026-07-01", "Cheap Sub", 50.00, "debit"),
            tx_row("2026-08-01", "Cheap Sub", 50.00, "debit"),
            tx_row("2026-06-10", "Big Rent", 9000.00, "debit"),
            tx_row("2026-07-10", "Big Rent", 9000.00, "debit"),
            tx_row("2026-08-10", "Big Rent", 9000.00, "debit"),
        ]
        seed(db, rows)
        items = ForecastEngine(db).detect_recurring()
        assert items[0]["merchant"] == "Big Rent"


class TestProject:
    """Tests for the balance projection."""

    def _seed_history(self, db, balance=1000.00):
        rows = [
            tx_row("2026-06-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-07-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-08-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-08-15", "Coffee Shop", 45.00, "debit", balance=balance),
        ]
        seed(db, rows)

    def test_projection_applies_recurring_debits(self, db, fixed_today):
        self._seed_history(db, balance=1000.00)
        forecast = ForecastEngine(db).project(days=10, include_burn=False)

        assert forecast["start_balance"] == 1000.00
        assert forecast["start_balance_date"] == "2026-08-15"
        # Next Netflix payment lands 2026-08-31 (last 2026-08-01 + 30 days)
        assert forecast["end_balance"] == pytest.approx(801.00)
        assert forecast["lowest_balance"] == pytest.approx(801.00)
        assert forecast["lowest_date"] == "2026-08-31"
        assert forecast["points"][0]["balance"] == 1000.00

    def test_critical_risk_when_overdrawn(self, db, fixed_today):
        self._seed_history(db, balance=150.00)
        forecast = ForecastEngine(db).project(days=10, include_burn=False)

        severities = [r["severity"] for r in forecast["risks"]]
        assert "critical" in severities
        assert forecast["lowest_balance"] < 0

    def test_ok_risk_when_healthy(self, db, fixed_today):
        self._seed_history(db, balance=5000.00)
        forecast = ForecastEngine(db).project(days=10, include_burn=False)
        assert all(r["severity"] != "critical" for r in forecast["risks"])
        assert any(r["severity"] == "ok" for r in forecast["risks"])

    def test_warning_risk_with_buffer(self, db, fixed_today):
        self._seed_history(db, balance=250.00)
        forecast = ForecastEngine(db).project(days=10, include_burn=False, safety_buffer=500.00)
        assert any(r["severity"] == "warning" for r in forecast["risks"])

    def test_no_balance_history(self, db, fixed_today):
        rows = [tx_row("2026-08-01", "Shop", 100.00, "debit")]
        seed(db, rows)
        forecast = ForecastEngine(db).project()
        assert forecast["start_balance"] is None
        assert forecast["points"] == []
        assert forecast["risks"][0]["severity"] == "info"

    def test_daily_burn_excludes_recurring(self, db, fixed_today):
        rows = [
            tx_row("2026-06-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-07-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-08-01", "NETFLIX", 199.00, "debit"),
        ]
        # 30 non-recurring R100 debits spread across the 90-day window
        for day in range(0, 90, 3):
            rows.append(
                tx_row(
                    (TODAY - timedelta(days=day)).isoformat(),
                    "Corner Cafe",
                    100.00,
                    "debit",
                )
            )
        seed(db, rows)
        engine = ForecastEngine(db)
        burn = engine._daily_burn({"netflix"})
        assert burn == pytest.approx(-100.0 / 3, abs=0.05)

    def test_include_burn_false_zeroes_burn(self, db, fixed_today):
        self._seed_history(db, balance=1000.00)
        forecast = ForecastEngine(db).project(days=5, include_burn=False)
        assert forecast["daily_burn"] == 0.0

    def test_upcoming_debits_within_week(self, db, fixed_today):
        self._seed_history(db, balance=1000.00)
        forecast = ForecastEngine(db).project(days=10, include_burn=False)
        merchants = [d["merchant"] for d in forecast["upcoming_debits"]]
        assert "Netflix" in merchants
        assert all(d["amount"] > 0 for d in forecast["upcoming_debits"])

    def test_committed_monthly_totals(self, db, fixed_today):
        rows = [
            tx_row("2026-06-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-07-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-08-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-06-25", "SALARY ACME", 20000.00, "credit"),
            tx_row("2026-07-25", "SALARY ACME", 20000.00, "credit"),
            tx_row("2026-08-25", "SALARY ACME", 20000.00, "credit"),
        ]
        seed(db, rows)
        forecast = ForecastEngine(db).project(include_burn=False)
        assert forecast["committed_monthly_outflow"] == pytest.approx(199.00 * 30.44 / 30, abs=1.0)
        assert forecast["committed_monthly_inflow"] == pytest.approx(20000.00 * 30.44 / 30, abs=1.0)


class TestCanAfford:
    """Tests for the affordability check."""

    def _seed(self, db, balance):
        # Only recurring activity, so the daily burn rate is exactly zero
        # and projections stay deterministic.
        rows = [
            tx_row("2026-06-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-07-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-08-01", "NETFLIX", 199.00, "debit", balance=balance),
        ]
        seed(db, rows)

    def test_affordable_purchase(self, db, fixed_today):
        self._seed(db, balance=2000.00)
        result = ForecastEngine(db).can_afford(500.00)
        assert result["affordable"] is True
        assert result["amount"] == 500.00
        assert result["lowest_balance_after"] == pytest.approx(1301.00)
        assert "Yes" in result["reason"]

    def test_unaffordable_purchase(self, db, fixed_today):
        self._seed(db, balance=1000.00)
        result = ForecastEngine(db).can_afford(1500.00)
        assert result["affordable"] is False
        assert result["lowest_balance_after"] < 0
        assert "short" in result["reason"]

    def test_future_purchase_target(self, db, fixed_today):
        self._seed(db, balance=1000.00)
        result = ForecastEngine(db).can_afford(500.00, days_ahead=10)
        assert result["target_date"] == "2026-09-04"
        # Netflix debits R199 on 2026-08-31, before the purchase date
        assert result["headroom_before_purchase"] == pytest.approx(801.00)

    def test_tight_but_affordable(self, db, fixed_today):
        # Balance dips near zero only because of the upcoming Netflix debit
        self._seed(db, balance=300.00)
        result = ForecastEngine(db).can_afford(100.00)
        assert result["affordable"] is True
        assert result["lowest_balance_after"] < 150.00
        assert "tight" in result["reason"]

    def test_insufficient_data(self, db, fixed_today):
        rows = [tx_row("2026-08-01", "Shop", 100.00, "debit")]
        seed(db, rows)
        result = ForecastEngine(db).can_afford(100.00)
        assert result["affordable"] is None
        assert "No balance history" in result["reason"]

    def test_horizon_extended_for_far_targets(self, db, fixed_today):
        self._seed(db, balance=5000.00)
        result = ForecastEngine(db).can_afford(100.00, days_ahead=60)
        assert result["affordable"] is not None


class TestAccountScoping:
    """Multi-account databases must forecast per account."""

    def test_default_account_is_most_recently_balanced(self, fixed_today):
        rows = [
            account_tx("2026-08-01", "Old Account Tx", 100.00, "debit",
                       "11111111111", balance=900.00),
            account_tx("2026-08-20", "New Account Tx", 100.00, "debit",
                       "22222222222", balance=5000.00),
        ]
        engine = ForecastEngine(StubDB(rows))
        assert engine.default_account() == "22222222222"

        forecast = engine.project(include_burn=False)
        # Anchor comes from the primary account only
        assert forecast["account"] == "22222222222"
        assert forecast["start_balance"] == 5000.00

    def test_explicit_account_selection(self, fixed_today):
        rows = [
            account_tx("2026-06-01", "NETFLIX", 199.00, "debit", "11111111111"),
            account_tx("2026-07-01", "NETFLIX", 199.00, "debit", "11111111111"),
            account_tx("2026-08-01", "NETFLIX", 199.00, "debit", "11111111111"),
            account_tx("2026-06-01", "NETFLIX", 499.00, "debit", "22222222222"),
            account_tx("2026-07-01", "NETFLIX", 499.00, "debit", "22222222222"),
            account_tx("2026-08-01", "NETFLIX", 499.00, "debit", "22222222222"),
            account_tx("2026-08-10", "Anchor", 0, "credit", "11111111111",
                       balance=1000.00),
        ]
        engine = ForecastEngine(StubDB(rows))

        first = engine.detect_recurring(account="11111111111")
        second = engine.detect_recurring(account="22222222222")
        assert len(first) == 1 and first[0]["typical_amount"] == 199.00
        assert len(second) == 1 and second[0]["typical_amount"] == 499.00

    def test_consolidated_all_accounts(self, fixed_today):
        rows = [
            account_tx("2026-08-01", "Acct One Tx", 100.00, "debit",
                       "11111111111", balance=900.00),
            account_tx("2026-08-20", "Acct Two Tx", 100.00, "debit",
                       "22222222222", balance=5000.00),
            account_tx("2026-08-21", "Acct One Later", 50.00, "debit",
                       "11111111111", balance=800.00),
        ]
        engine = ForecastEngine(StubDB(rows))
        point = engine._latest_balance_point("all")
        # Latest balance per account: R800 (Aug 21) + R5000 (Aug 20)
        assert point is not None
        anchor_date, total = point
        assert total == 5800.00
        assert anchor_date == date(2026, 8, 21)

    def test_consolidated_skips_unusable_rows(self, fixed_today):
        rows = [
            # Missing account number
            tx_row("2026-08-01", "No Account", 10.00, "debit", balance=50.00),
            # Bad date
            account_tx("not-a-date", "Bad Date", 10.00, "debit", "11111111111",
                       balance=60.00),
            # Bad balance value
            account_tx("2026-08-02", "Bad Balance", 10.00, "debit", "22222222222",
                       balance="junk"),
            # No balance at all
            account_tx("2026-08-03", "No Balance", 10.00, "debit", "33333333333"),
            # One good row
            account_tx("2026-08-05", "Good Row", 10.00, "debit", "44444444444",
                       balance=1234.00),
        ]
        engine = ForecastEngine(StubDB(rows))
        point = engine._latest_balance_point("all")
        assert point == (date(2026, 8, 5), 1234.00)

    def test_consolidated_no_usable_rows_returns_none(self, fixed_today):
        rows = [
            tx_row("2026-08-01", "No Account", 10.00, "debit", balance=50.00),
            account_tx("2026-08-02", "Bad Balance", 10.00, "debit", "11111111111",
                       balance="junk"),
        ]
        assert ForecastEngine(StubDB(rows))._latest_balance_point("all") is None

    def test_single_account_balance_point_skips_bad_dates(self, fixed_today):
        rows = [
            account_tx("not-a-date", "Bad Date", 10.00, "debit", "11111111111",
                       balance=999.00),
            account_tx("2026-08-10", "Good Row", 10.00, "debit", "11111111111",
                       balance=250.00),
        ]
        engine = ForecastEngine(StubDB(rows))
        assert engine._latest_balance_point("11111111111") == (
            date(2026, 8, 10), 250.00
        )

    def test_default_account_skips_bad_dates(self, fixed_today):
        rows = [
            account_tx("not-a-date", "Bad Date", 10.00, "debit", "11111111111",
                       balance=999.00),
            account_tx("2026-08-10", "Good Row", 10.00, "debit", "22222222222",
                       balance=250.00),
        ]
        assert ForecastEngine(StubDB(rows)).default_account() == "22222222222"

    def test_other_accounts_do_not_leak_into_projection(self, fixed_today):
        rows = [
            # Primary account: Netflix R199 monthly
            account_tx("2026-06-01", "NETFLIX", 199.00, "debit", "11111111111"),
            account_tx("2026-07-01", "NETFLIX", 199.00, "debit", "11111111111"),
            account_tx("2026-08-01", "NETFLIX", 199.00, "debit", "11111111111"),
            account_tx("2026-08-15", "Anchor", 0, "credit", "11111111111",
                       balance=1000.00),
            # Secondary account: huge debit that must be ignored
            account_tx("2026-06-05", "Rent Other Bank", 9000.00, "debit", "22222222222"),
            account_tx("2026-07-05", "Rent Other Bank", 9000.00, "debit", "22222222222"),
            account_tx("2026-08-05", "Rent Other Bank", 9000.00, "debit", "22222222222"),
        ]
        forecast = ForecastEngine(StubDB(rows)).project(
            days=20, include_burn=False, account="11111111111"
        )
        assert forecast["end_balance"] == pytest.approx(801.00)
        assert forecast["recurring_count"] == 1


class TestEngineHelpers:
    """Tests for engine internals."""

    def test_summarize_recurring(self, db, fixed_today):
        items = [
            {"direction": "out", "monthly_equivalent": 100.00},
            {"direction": "in", "monthly_equivalent": 500.00},
            {"direction": "out", "monthly_equivalent": 50.55},
        ]
        inflow, outflow = ForecastEngine._summarize_recurring(items)
        assert inflow == 500.00
        assert outflow == 150.55

    def test_empty_database(self, db, fixed_today):
        engine = ForecastEngine(db)
        assert engine.detect_recurring() == []
        forecast = engine.project()
        assert forecast["start_balance"] is None


class StubDB:
    """Minimal database stand-in returning canned rows."""

    def __init__(self, rows):
        self.rows = rows

    def get_all_transactions(self):
        return self.rows


class TestDefensivePaths:
    """Malformed and edge-case data must never crash the engine."""

    def test_parse_date_accepts_date_and_datetime(self):
        from datetime import datetime as dt

        assert _parse_date(dt(2026, 8, 25, 9, 30)) == TODAY
        assert _parse_date(TODAY) == TODAY

    def test_malformed_rows_skipped_in_detection(self, fixed_today):
        rows = [
            tx_row("2026-06-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-07-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-08-01", "NETFLIX", 199.00, "debit"),
            # Malformed entries that must be skipped silently
            tx_row("2026-05-01", "Broken Amount", "not-a-number", "debit"),
            tx_row("2026-05-02", "Zero Amount", 0, "debit"),
            tx_row("not-a-date", "Bad Date Row", 50.00, "debit"),
            tx_row("2026-05-03", "Bad Type Date", "not-a-date", "blah", 50.0),
            tx_row("2026-05-04", "12345 !!!", 10.00, "debit"),
        ]
        items = ForecastEngine(StubDB(rows)).detect_recurring()
        assert len(items) == 1
        assert items[0]["key"] == "netflix"

    def test_same_day_group_rejected(self, fixed_today):
        rows = [tx_row("2026-06-01", "Burst Txns", 50.00, "debit") for _ in range(4)]
        assert ForecastEngine(StubDB(rows)).detect_recurring() == []

    def test_deviation_override_can_reject_group(self, fixed_today):
        rows = [
            tx_row("2026-06-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-07-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-08-05", "NETFLIX", 199.00, "debit"),
        ]
        engine = ForecastEngine(StubDB(rows))
        # Intervals are 30/35 days (median ~32); a 1-day tolerance rejects
        assert engine.detect_recurring(max_interval_deviation=1) == []

    def test_deviation_override_with_unbucketed_median(self, fixed_today):
        rows = [
            tx_row("2026-05-01", "Quarterly Thing", 900.00, "debit"),
            tx_row("2026-08-01", "Quarterly Thing", 900.00, "debit"),
            tx_row("2026-11-01", "Quarterly Thing", 900.00, "debit"),
        ]
        # Median ~92 days is consistent but outside every cadence bucket
        assert ForecastEngine(StubDB(rows)).detect_recurring(
            max_interval_deviation=10
        ) == []

    def test_bad_balance_value_ignored_for_anchor(self, fixed_today):
        rows = [
            tx_row("2026-08-20", "ATM Cash", 100.00, "debit", balance="junk"),
            tx_row("2026-08-19", "Shop", 50.00, "debit", balance=250.00),
        ]
        point = ForecastEngine(StubDB(rows))._latest_balance_point()
        assert point == (date(2026, 8, 19), 250.00)

    def test_daily_burn_empty_database(self, fixed_today):
        assert ForecastEngine(StubDB([]))._daily_burn(set()) == 0.0

    def test_daily_burn_all_transactions_recurring(self, fixed_today):
        rows = [
            tx_row("2026-06-01", "NETFLIX", 199.00, "debit"),
            tx_row("2026-07-01", "NETFLIX", 199.00, "debit"),
        ]
        burn = ForecastEngine(StubDB(rows))._daily_burn({"netflix"})
        assert burn == 0.0

    def test_daily_burn_skips_malformed_amounts(self, fixed_today):
        rows = [
            tx_row("2026-08-01", "Cafe", "oops", "debit"),
            tx_row("2026-08-02", "Refund", 75.00, "credit"),
        ]
        burn = ForecastEngine(StubDB(rows))._daily_burn(set())
        assert burn > 0
