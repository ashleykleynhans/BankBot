"""Cashflow forecasting engine.

Detects recurring transactions from history, projects future balances,
highlights cashflow risks, and answers affordability questions.

All public methods return plain dicts with ISO date strings so they can be
serialized directly by the API, CLI, or chat layers.
"""

import re
from datetime import date, datetime, timedelta
from collections import Counter
from statistics import median

DEFAULT_HORIZON_DAYS = 31
BURN_WINDOW_DAYS = 90
DAYS_PER_MONTH = 30.44

# Recurring groups whose most recent payment is older than this are ignored.
RECENCY_WINDOW_DAYS = 365

# Tokens that describe the transaction mechanics rather than the merchant.
NOISE_TOKENS = {
    "pos", "purchase", "purchases", "debit", "credit", "order", "card",
    "payment", "payments", "the", "and", "for", "from", "to", "ref",
    "reference", "trf", "transfer", "eft", "online", "banking", "www",
    "co", "za", "com", "pty", "ltd", "sa", "value", "added", "tax",
    "invoice", "till", "prepaid", "airtime", "wallet", "acct", "account",
}

# Cadence buckets: (min median interval, max median interval, name).
CADENCES = [
    (5, 9, "weekly"),
    (12, 18, "fortnightly"),
    (25, 38, "monthly"),
]


def _today() -> date:
    """Return today's date. Module-level so tests can patch it."""
    return date.today()


def _parse_date(value: object) -> date | None:
    """Parse an ISO date string (or date) into a date, or None."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def normalize_description(description: str) -> str:
    """Normalize a transaction description into a grouping key.

    Strips numbers (references, dates), bank jargon tokens, and punctuation
    so that e.g. "POS Purchase Netflix.Com 2410" and "NETFLIX.COM" group
    together.
    """
    tokens = re.split(r"[^a-z]+", description.lower())
    kept = [
        token for token in tokens
        if token and token not in NOISE_TOKENS and not any(c.isdigit() for c in token)
    ]
    return " ".join(kept)


def display_name(normalized: str) -> str:
    """Convert a normalized description key into a human-friendly name."""
    return " ".join(word.capitalize() for word in normalized.split()) or "Unknown"


def _classify_cadence(intervals: list[int]) -> tuple[str, int] | None:
    """Classify a list of day intervals into a cadence.

    Returns (cadence_name, interval_days) using the median interval when all
    intervals fall within tolerance of it, else None.
    """
    med = int(round(median(intervals)))
    tolerance = max(3, round(med * 0.25))
    if any(abs(interval - med) > tolerance for interval in intervals):
        return None
    for low, high, name in CADENCES:
        if low <= med <= high:
            return name, med
    return None


class ForecastEngine:
    """Forecasts balances and detects recurring payments from stored transactions."""

    def __init__(self, db):
        """Create an engine over a BankBot Database instance."""
        self.db = db

    def _load_transactions(self) -> list[dict]:
        """Load all transactions sorted oldest first."""
        transactions = self.db.get_all_transactions()
        return sorted(transactions, key=lambda t: (t.get("date") or "", t.get("id") or 0))

    @staticmethod
    def _for_account(transactions: list[dict], account: str | None) -> list[dict]:
        """Filter transactions down to a single bank account."""
        if account is None or account == "all":
            return transactions
        return [t for t in transactions if t.get("account_number") == account]

    def detect_recurring(
        self,
        min_occurrences: int = 3,
        max_interval_deviation: float | None = None,
        account: str | None = None,
    ) -> list[dict]:
        """Detect recurring payments and income from transaction history.

        Groups transactions by normalized description, then keeps groups whose
        payment intervals are consistent enough to look scheduled. Groups
        whose most recent payment is older than RECENCY_WINDOW_DAYS are
        ignored entirely.

        Args:
            min_occurrences: Minimum times a description must appear.
            max_interval_deviation: Optional override for interval tolerance
                in days; defaults to max(3, 25% of median interval).
            account: Restrict detection to one bank account; by default all
                accounts are scanned.

        Returns:
            List of recurring item dicts sorted by monthly-equivalent amount
            descending.
        """
        cutoff_date = _today() - timedelta(days=RECENCY_WINDOW_DAYS)
        groups: dict[str, list[dict]] = {}
        for tx in self._for_account(self._load_transactions(), account):
            try:
                amount = abs(float(tx.get("amount") or 0))
            except (TypeError, ValueError):
                continue
            if amount <= 0:
                continue
            tx_date = _parse_date(tx.get("date"))
            if tx_date is None:
                continue
            key = normalize_description(tx.get("description") or "")
            if not key:
                continue
            groups.setdefault(key, []).append({
                **tx,
                "_date": tx_date,
                "_amount": amount,
            })

        items: list[dict] = []
        for key, group in groups.items():
            if len(group) < min_occurrences:
                continue
            group.sort(key=lambda t: t["_date"])
            if group[-1]["_date"] < cutoff_date:
                continue
            intervals = [
                (later["_date"] - earlier["_date"]).days
                for earlier, later in zip(group, group[1:])
                if later["_date"] > earlier["_date"]
            ]
            if not intervals:
                continue

            if max_interval_deviation is not None:
                med = int(round(median(intervals)))
                if any(abs(i - med) > max_interval_deviation for i in intervals):
                    continue
                cadence = next(
                    (name for low, high, name in CADENCES if low <= med <= high),
                    None,
                )
                if cadence is None:
                    continue
                cadence_result = (cadence, med)
            else:
                cadence_result = _classify_cadence(intervals)
            if cadence_result is None:
                continue
            cadence, interval_days = cadence_result

            amounts = [t["_amount"] for t in group]
            typical_amount = round(median(amounts), 2)
            spread = (max(amounts) - min(amounts)) / typical_amount if typical_amount else 0

            directions = Counter(t.get("transaction_type") for t in group)
            direction = "in" if directions["credit"] > directions["debit"] else "out"

            categories = Counter(
                t.get("category") for t in group if t.get("category")
            )
            category = categories.most_common(1)[0][0] if categories else None

            last = group[-1]
            next_date = last["_date"] + timedelta(days=interval_days)
            while next_date <= _today():
                next_date += timedelta(days=interval_days)

            # A commitment is only "active" if its last payment is recent
            # relative to its own cadence; stopped subscriptions must not
            # project forward indefinitely.
            active = last["_date"] + timedelta(days=interval_days * 3) >= _today()

            confidence = "high"
            if len(group) < 4 or spread > 0.15:
                confidence = "medium"
            if spread > 0.5:
                confidence = "low"

            items.append({
                "key": key,
                "merchant": display_name(key),
                "description_sample": last.get("description") or "",
                "category": category,
                "direction": direction,
                "cadence": cadence,
                "interval_days": interval_days,
                "typical_amount": typical_amount,
                "last_amount": round(amounts[-1], 2),
                "last_date": last["_date"].isoformat(),
                "next_date": next_date.isoformat(),
                "occurrences": len(group),
                "confidence": confidence,
                "active": active,
                "monthly_equivalent": round(typical_amount * DAYS_PER_MONTH / interval_days, 2),
            })

        items.sort(key=lambda i: i["monthly_equivalent"], reverse=True)
        return items

    def _latest_balance_point(self, account: str | None = None) -> tuple[date, float] | None:
        """Find the most recent balance, optionally across all accounts.

        With account="all", sums the latest known balance of every account
        (a consolidated view); the anchor date is the most recent of those.
        """
        if account == "all":
            latest_by_account: dict[str, tuple[date, float]] = {}
            for tx in self._load_transactions():
                acct = tx.get("account_number")
                if tx.get("balance") is None or not acct:
                    continue
                tx_date = _parse_date(tx.get("date"))
                if tx_date is None:
                    continue
                try:
                    balance = float(tx["balance"])
                except (TypeError, ValueError):
                    continue
                if (
                    acct not in latest_by_account
                    or tx_date >= latest_by_account[acct][0]
                ):
                    latest_by_account[acct] = (tx_date, balance)
            if not latest_by_account:
                return None
            anchor_date = max(d for d, _ in latest_by_account.values())
            total = sum(b for _, b in latest_by_account.values())
            return anchor_date, total

        latest: tuple[date, float] | None = None
        for tx in self._for_account(self._load_transactions(), account):
            if tx.get("balance") is None:
                continue
            tx_date = _parse_date(tx.get("date"))
            if tx_date is None:
                continue
            try:
                balance = float(tx["balance"])
            except (TypeError, ValueError):
                continue
            if latest is None or tx_date >= latest[0]:
                latest = (tx_date, balance)
        return latest

    def default_account(self) -> str | None:
        """Pick the primary forecast account.

        The account whose most recent balance-bearing transaction is the
        newest - typically the main spending account. Returns None when no
        balances are recorded at all.
        """
        best_account: str | None = None
        best_date: date | None = None
        for tx in self._load_transactions():
            if tx.get("balance") is None or not tx.get("account_number"):
                continue
            tx_date = _parse_date(tx.get("date"))
            if tx_date is None:
                continue
            if best_date is None or tx_date >= best_date:
                best_date = tx_date
                best_account = tx["account_number"]
        return best_account

    def _daily_burn(
        self, recurring_keys: set[str], account: str | None = None
    ) -> float:
        """Estimate average daily net flow from non-recurring activity.

        Looks at the trailing BURN_WINDOW_DAYS of history ending at the most
        recent transaction, excludes detected recurring descriptions, and
        returns net rands per day (negative when spending outpaces income).
        """
        transactions = self._for_account(self._load_transactions(), account)
        if not transactions:
            return 0.0

        end_date = _parse_date(transactions[-1].get("date"))
        start_date = end_date - timedelta(days=BURN_WINDOW_DAYS)

        window = [
            tx for tx in transactions
            if start_date <= _parse_date(tx.get("date")) <= end_date
            and normalize_description(tx.get("description") or "") not in recurring_keys
        ]
        if not window:
            return 0.0

        span_days = max((end_date - start_date).days, 1)
        net = 0.0
        for tx in window:
            try:
                amount = float(tx.get("amount") or 0)
            except (TypeError, ValueError):
                continue
            net += amount if tx.get("transaction_type") == "credit" else -amount
        return round(net / span_days, 2)

    @staticmethod
    def _summarize_recurring(items: list[dict]) -> tuple[float, float]:
        """Sum monthly-equivalent inflow and outflow across recurring items."""
        inflow = sum(i["monthly_equivalent"] for i in items if i["direction"] == "in")
        outflow = sum(i["monthly_equivalent"] for i in items if i["direction"] == "out")
        return round(inflow, 2), round(outflow, 2)

    def project(
        self,
        days: int = DEFAULT_HORIZON_DAYS,
        include_burn: bool = True,
        safety_buffer: float = 0.0,
        account: str | None = None,
    ) -> dict:
        """Project daily balances forward using recurring flows and burn rate.

        Args:
            days: Horizon length in days from today.
            include_burn: Whether to apply the average daily non-recurring
                net spend on top of committed recurring flows.
            safety_buffer: Warn when projected balance dips below this value.
            account: Bank account to forecast. When omitted, defaults to the
                account with the most recent balance data.

        Returns:
            Dict with starting balance, daily points, risk alerts, and
            committed monthly totals.
        """
        account = account or self.default_account()
        recurring = [
            item for item in self.detect_recurring(account=account) if item["active"]
        ]
        inflow_monthly, outflow_monthly = self._summarize_recurring(recurring)

        result: dict = {
            "as_of": _today().isoformat(),
            "days": days,
            "account": account,
            "start_balance": None,
            "start_balance_date": None,
            "end_balance": None,
            "lowest_balance": None,
            "lowest_date": None,
            "daily_burn": 0.0,
            "include_burn": include_burn,
            "committed_monthly_inflow": inflow_monthly,
            "committed_monthly_outflow": outflow_monthly,
            "points": [],
            "risks": [],
            "upcoming_debits": [],
            "recurring_count": len(recurring),
        }

        anchor = self._latest_balance_point(account=account)
        if anchor is None:
            result["risks"].append({
                "severity": "info",
                "date": None,
                "message": (
                    "No balance history available, so absolute balances cannot "
                    "be projected. Import statements with running balances."
                ),
            })
            return result

        anchor_date, balance = anchor
        horizon_end = _today() + timedelta(days=days)

        events: dict[date, float] = {}
        upcoming: list[dict] = []
        for item in recurring:
            signed = (
                item["typical_amount"] if item["direction"] == "in" else -item["typical_amount"]
            )
            occurrence = _parse_date(item["next_date"])
            while occurrence <= horizon_end:
                events[occurrence] = events.get(occurrence, 0.0) + signed
                if (
                    anchor_date < occurrence <= _today() + timedelta(days=7)
                    and item["direction"] == "out"
                ):
                    upcoming.append({
                        "merchant": item["merchant"],
                        "amount": item["typical_amount"],
                        "date": occurrence.isoformat(),
                    })
                occurrence += timedelta(days=item["interval_days"])
        upcoming.sort(key=lambda u: u["date"])

        daily_burn = (
            self._daily_burn({item["key"] for item in recurring}, account=account)
            if include_burn
            else 0.0
        )

        points: list[dict] = [{"date": anchor_date.isoformat(), "balance": round(balance, 2)}]
        lowest_balance = balance
        lowest_date = anchor_date
        current_day = anchor_date
        while current_day < horizon_end:
            current_day += timedelta(days=1)
            balance += daily_burn + events.get(current_day, 0.0)
            balance = round(balance, 2)
            points.append({"date": current_day.isoformat(), "balance": balance})
            if balance < lowest_balance:
                lowest_balance = balance
                lowest_date = current_day
            if balance < 0:
                deficit = round(-balance, 2)
                if not any(r["severity"] == "critical" for r in result["risks"]):
                    result["risks"].append({
                        "severity": "critical",
                        "date": current_day.isoformat(),
                        "message": (
                            f"Projected balance drops below zero (-R{deficit:,.2f}) "
                            f"on {current_day.strftime('%-d %B %Y')}"
                        ),
                    })
            elif safety_buffer > 0 and balance < safety_buffer:
                if not any(r["severity"] == "warning" for r in result["risks"]):
                    result["risks"].append({
                        "severity": "warning",
                        "date": current_day.isoformat(),
                        "message": (
                            f"Projected balance dips under your R{safety_buffer:,.2f} "
                            f"safety buffer on {current_day.strftime('%-d %B %Y')}"
                        ),
                    })

        if not any(r["severity"] in ("critical", "warning") for r in result["risks"]):
            result["risks"].append({
                "severity": "ok",
                "date": None,
                "message": (
                    f"No cashflow risks detected in the next {days} days. "
                    f"Lowest projected balance is R{lowest_balance:,.2f}."
                ),
            })

        result.update({
            "start_balance": round(anchor[1], 2),
            "start_balance_date": anchor_date.isoformat(),
            "end_balance": points[-1]["balance"],
            "lowest_balance": round(lowest_balance, 2),
            "lowest_date": lowest_date.isoformat(),
            "daily_burn": daily_burn,
            "points": points,
            "upcoming_debits": upcoming,
        })
        return result

    def can_afford(
        self,
        amount: float,
        days_ahead: int = 0,
        horizon: int = DEFAULT_HORIZON_DAYS,
        account: str | None = None,
    ) -> dict:
        """Answer whether spending `amount` on `today + days_ahead` is affordable.

        Simulates the purchase on top of the baseline projection and checks
        whether the balance ever drops below zero afterwards.

        Returns a dict with the verdict, the resulting lowest balance, and any
        recurring debits scheduled before the purchase date.
        """
        # Make sure the projection extends past the purchase date
        horizon = max(horizon, days_ahead + 1)
        projection = self.project(days=horizon, account=account)
        target = _today() + timedelta(days=days_ahead)

        base: dict = {
            "amount": round(amount, 2),
            "target_date": target.isoformat(),
            "account": projection["account"],
            "affordable": None,
            "reason": None,
            "lowest_balance_after": None,
            "lowest_date_after": None,
            "headroom_before_purchase": None,
            "upcoming_debits_before_target": [],
        }

        if projection["start_balance"] is None:
            base["reason"] = (
                "No balance history available to judge affordability. "
                "Import statements with running balances first."
            )
            return base

        for debit in projection["upcoming_debits"]:
            if debit["date"] <= target.isoformat():
                base["upcoming_debits_before_target"].append(debit)

        balances_after = []
        balances_before = [projection["start_balance"]]
        for point in projection["points"]:
            point_date = _parse_date(point["date"])
            adjusted = point["balance"]
            if point_date is not None and point_date >= target:
                adjusted -= amount
                balances_after.append(round(adjusted, 2))
            else:
                balances_before.append(point["balance"])

        lowest_after = min(balances_after)
        lowest_index = balances_after.index(lowest_after)
        lowest_point = [
            p for p in projection["points"] if _parse_date(p["date"]) >= target
        ][lowest_index]

        base.update({
            "affordable": lowest_after >= 0,
            "lowest_balance_after": lowest_after,
            "lowest_date_after": lowest_point["date"],
            "headroom_before_purchase": round(min(balances_before), 2),
        })

        if lowest_after < 0:
            shortfall = round(-lowest_after, 2)
            base["reason"] = (
                f"This would leave you R{shortfall:,.2f} short at your lowest "
                f"projected balance."
            )
        elif lowest_after < round(amount * 0.2, 2):
            base["reason"] = (
                f"Yes, but it will be tight. Your lowest balance afterwards "
                f"would be R{lowest_after:,.2f} around {lowest_point['date']}."
            )
        else:
            base["reason"] = (
                f"Yes, comfortably. Your lowest balance afterwards would still "
                f"be R{lowest_after:,.2f} around {lowest_point['date']}."
            )
        return base
