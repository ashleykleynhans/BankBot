#!/usr/bin/env python3
"""Create a dummy BankBot database based on an existing one.

The script reads transactions from your real database and writes an anonymised
copy to a separate SQLite file. Dates, descriptions, categories, and
transaction types are preserved so the dummy data still looks realistic, but:

- every amount is randomly jittered within a configurable range;
- selected categories are capped at a maximum amount (salary at R20,000 and
  transfers/deposits at R500 by default);
- running balances are jittered per account, preserving the shape of the
  original balance history;
- account numbers are replaced and raw OCR text is dropped.

The source database is never modified.

Examples:
    # Create ./data/statements_dummy.db from ./data/statements.db
    uv run python scripts/seed_dummy_db.py

    # Overwrite an existing dummy database with a different random seed
    uv run python scripts/seed_dummy_db.py --force --seed 7

    # Override a default cap or add another one
    uv run python scripts/seed_dummy_db.py --cap groceries=500

    # Point the application at the dummy database
    BANKBOT_DB=./data/statements_dummy.db uv run bankbot stats
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
from pathlib import Path

# Allow running as a script from a source checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import Database  # noqa: E402

DEFAULT_SOURCE = "./data/statements.db"
DEFAULT_TARGET = "./data/statements_dummy.db"
DEFAULT_CAPS = {
    "salary": 20_000.0,
    "transfer": 500.0,
    "deposit": 500.0,
}
DUMMY_ACCOUNT_NUMBER = "00000000000"


def parse_caps(specs: list[str]) -> dict[str, float]:
    """Parse repeated CATEGORY=AMOUNT arguments into a dict."""
    caps: dict[str, float] = {}
    for spec in specs:
        category, separator, amount = spec.partition("=")
        category = category.strip()
        if not separator or not category:
            raise argparse.ArgumentTypeError(
                f"invalid --cap value {spec!r}; expected CATEGORY=AMOUNT"
            )
        try:
            value = float(amount)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"invalid amount in --cap value {spec!r}"
            ) from exc
        if value <= 0:
            raise argparse.ArgumentTypeError(
                f"cap for {category!r} must be greater than zero"
            )
        caps[category] = value
    return caps


def open_source(db_path: Path) -> sqlite3.Connection:
    """Open the source database read-only so it can never be modified."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def load_statements(db_path: Path) -> list[dict]:
    """Load every statement from the source database."""
    connection = open_source(db_path)
    try:
        rows = connection.execute(
            """
            SELECT id, filename, bank, account_number, statement_date,
                   statement_number
            FROM statements
            ORDER BY statement_date, id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def load_transactions(db_path: Path) -> list[dict]:
    """Load every transaction from the source database."""
    connection = open_source(db_path)
    try:
        rows = connection.execute(
            """
            SELECT id, statement_id, date, description, amount, balance,
                   transaction_type, category, recipient_or_payer, reference,
                   raw_text
            FROM transactions
            ORDER BY date, id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def anonymise_accounts(statements: list[dict]) -> dict[str, str]:
    """Map real account numbers to anonymous ones, one per account."""
    real_accounts = sorted(
        {statement["account_number"] for statement in statements
         if statement["account_number"]}
    )
    return {
        account: f"{index:011d}"
        for index, account in enumerate(real_accounts, start=1)
    }


def build_dummy_transactions(
    transactions: list[dict],
    statement_accounts: dict[int, str],
    rng: random.Random,
    jitter: tuple[float, float],
    caps: dict[str, float],
    max_amount: float | None,
    balance_jitter: tuple[float, float],
) -> tuple[list[dict], int]:
    """Return jittered and capped copies of the source transactions."""
    low, high = jitter
    capped_count = 0
    dummy: list[dict] = []

    accounts = {statement_accounts.get(t["statement_id"], "unknown")
                for t in transactions}
    balance_factors = {
        account: rng.uniform(*balance_jitter) for account in accounts
    }

    for transaction in transactions:
        account = statement_accounts.get(transaction["statement_id"], "unknown")
        amount = float(transaction["amount"]) * rng.uniform(low, high)

        was_capped = False
        cap = caps.get(transaction["category"])
        if cap is not None and amount > cap:
            amount = cap
            was_capped = True
        if max_amount is not None and amount > max_amount:
            amount = max_amount
            was_capped = True
        if was_capped:
            capped_count += 1

        source_balance = transaction["balance"]
        balance = (
            None if source_balance is None
            else round(float(source_balance) * balance_factors[account], 2)
        )

        dummy.append(
            {
                "account": account,
                "statement_id": transaction["statement_id"],
                "date": transaction["date"],
                "description": transaction["description"],
                "amount": round(max(amount, 0.01), 2),
                "balance": balance,
                "transaction_type": transaction["transaction_type"],
                "category": transaction["category"],
                "recipient_or_payer": transaction["recipient_or_payer"],
                "reference": transaction["reference"],
                # Raw OCR text can contain the original amounts.
                "raw_text": None,
            }
        )

    return dummy, capped_count


def seed_database(
    source: Path,
    target: Path,
    rng: random.Random,
    jitter: tuple[float, float],
    caps: dict[str, float],
    max_amount: float | None,
    balance_jitter: tuple[float, float],
) -> tuple[int, int, int]:
    """Write the dummy database and return (transactions, statements, capped)."""
    source_statements = load_statements(source)
    source_transactions = load_transactions(source)

    account_map = anonymise_accounts(source_statements)
    statement_accounts = {
        statement["id"]: account_map.get(
            statement["account_number"], DUMMY_ACCOUNT_NUMBER
        )
        for statement in source_statements
    }

    target_db = Database(target)

    statement_map: dict[int, int] = {}
    for statement in source_statements:
        new_id = target_db.insert_statement(
            filename=f"dummy_{statement['filename']}",
            bank=statement["bank"],
            account_number=statement_accounts[statement["id"]],
            statement_date=statement["statement_date"],
            statement_number=statement["statement_number"],
        )
        statement_map[statement["id"]] = new_id

    dummy_transactions, capped_count = build_dummy_transactions(
        source_transactions,
        statement_accounts=statement_accounts,
        rng=rng,
        jitter=jitter,
        caps=caps,
        max_amount=max_amount,
        balance_jitter=balance_jitter,
    )

    by_statement: dict[int, list[dict]] = {}
    for transaction in dummy_transactions:
        new_statement_id = statement_map.get(transaction["statement_id"])
        if new_statement_id is None:
            continue
        by_statement.setdefault(new_statement_id, []).append(transaction)

    inserted = 0
    for statement_id, transactions in by_statement.items():
        target_db.insert_transactions_batch(statement_id, transactions)
        inserted += len(transactions)

    return inserted, len(source_statements), capped_count


def remove_existing_database(path: Path) -> None:
    """Delete a database and its SQLite sidecar files."""
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{path}{suffix}")
        if candidate.exists():
            candidate.unlink()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a dummy BankBot database from an existing one.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(DEFAULT_SOURCE),
        help="existing database to base the dummy data on",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path(DEFAULT_TARGET),
        help="database to create",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="random seed, so the same dummy data can be regenerated",
    )
    parser.add_argument(
        "--jitter",
        type=float,
        nargs=2,
        metavar=("MIN", "MAX"),
        default=(0.75, 1.25),
        help="multiply every amount by a random factor in this range",
    )
    parser.add_argument(
        "--balance-jitter",
        type=float,
        nargs=2,
        metavar=("MIN", "MAX"),
        default=(0.9, 1.1),
        help="multiply each account's balance history by a random factor",
    )
    parser.add_argument(
        "--cap",
        action="append",
        default=[],
        metavar="CATEGORY=AMOUNT",
        help="cap transaction amounts per category (repeatable, overrides defaults)",
    )
    parser.add_argument(
        "--no-default-caps",
        action="store_true",
        help="do not apply the default caps for salary, transfer, and deposit",
    )
    parser.add_argument(
        "--max-amount",
        type=float,
        default=None,
        help="cap every transaction amount at this value",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the target database if it already exists",
    )
    return parser.parse_args(argv)


def validate_range(
    parser_value: tuple[float, float],
    name: str,
) -> str | None:
    """Return an error message when a MIN/MAX range is invalid."""
    low, high = parser_value
    if low <= 0 or low > high:
        return f"error: --{name} must satisfy 0 < MIN <= MAX"
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    for name, value in (
        ("jitter", args.jitter),
        ("balance-jitter", args.balance_jitter),
    ):
        error = validate_range(value, name)
        if error:
            print(error, file=sys.stderr)
            return 2

    if args.max_amount is not None and args.max_amount <= 0:
        print("error: --max-amount must be greater than zero", file=sys.stderr)
        return 2

    try:
        caps = parse_caps(args.cap)
    except argparse.ArgumentTypeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not args.no_default_caps:
        caps = {**DEFAULT_CAPS, **caps}

    source = args.source.expanduser()
    target = args.target.expanduser()

    if not source.exists():
        print(f"error: source database not found: {source}", file=sys.stderr)
        return 1
    if source.resolve() == target.resolve():
        print("error: --source and --target must be different files", file=sys.stderr)
        return 1
    if target.exists() and not args.force:
        print(
            f"error: target database already exists: {target}\n"
            "       pass --force to overwrite it",
            file=sys.stderr,
        )
        return 1

    remove_existing_database(target)

    rng = random.Random(args.seed)
    transactions, statements, capped = seed_database(
        source=source,
        target=target,
        rng=rng,
        jitter=tuple(args.jitter),
        caps=caps,
        max_amount=args.max_amount,
        balance_jitter=tuple(args.balance_jitter),
    )

    caps_summary = ", ".join(
        f"{category} <= {amount:,.2f}" for category, amount in sorted(caps.items())
    ) or "none"

    print(f"Created {target}")
    print(f"  statements:   {statements}")
    print(f"  transactions: {transactions}")
    print(f"  amount caps:  {caps_summary}")
    print(f"  capped txns:  {capped}")
    print(f"  random seed:  {args.seed}")
    print()
    print("Use it with:")
    print(f"  BANKBOT_DB={target} uv run bankbot stats")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
