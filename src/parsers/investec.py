"""Investec bank statement parser."""

import re
from datetime import datetime
from pathlib import Path

import pdfplumber

from . import register_parser
from .base import BaseBankParser, StatementData, Transaction


@register_parser
class InvestecParser(BaseBankParser):
    """Parser for Investec Private Bank statements."""

    @classmethod
    def bank_name(cls) -> str:
        """Return the bank identifier."""
        return "investec"

    def parse(self, pdf_path: str | Path, password: str | None = None) -> StatementData:
        """Parse an Investec statement PDF."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        full_text = ""
        with pdfplumber.open(pdf_path, password=password) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                full_text += page_text + "\n"

        account_number = self._extract_account_number(full_text)
        statement_date = self._extract_statement_date(full_text)
        statement_number = self._derive_statement_number(statement_date)
        transactions = self._parse_transactions(full_text, statement_date)

        return StatementData(
            account_number=account_number,
            statement_date=statement_date,
            statement_number=statement_number,
            transactions=transactions,
        )

    def _extract_account_number(self, text: str) -> str | None:
        """Extract account number from statement text."""
        match = re.search(r"Account\s*Number\s+(\d{10,})", text, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_statement_date(self, text: str) -> str | None:
        """Extract statement date and return as YYYY-MM-DD."""
        match = re.search(
            r"Statement\s+Date\s+(\d{1,2}\s+\w+\s+\d{4})", text, re.IGNORECASE
        )
        if not match:
            return None
        try:
            dt = datetime.strptime(match.group(1), "%d %B %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None

    def _derive_statement_number(self, statement_date: str | None) -> str | None:
        """Derive statement number as YYYY-MM from statement date."""
        if not statement_date:
            return None
        return statement_date[:7]

    def _parse_transactions(self, text: str, statement_date: str | None) -> list[Transaction]:
        """Parse transactions from the 'Transaction detail' table."""
        raw_transactions: list[Transaction] = []
        lines = text.split("\n")
        in_transactions = False
        opening_balance: float | None = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if "Transaction detail" in line:
                in_transactions = True
                continue

            if not in_transactions:
                continue

            if line.startswith("Posted Date"):
                continue

            if line.startswith("Balance brought forward"):
                match = re.search(r"([\d,]+\.\d{2})", line)
                if match:
                    opening_balance = float(match.group(1).replace(",", ""))
                continue

            if line.startswith("Closing Balance"):
                continue

            if "Online payments, deposits, fees and interest" in line:
                break

            tx = self._parse_transaction_line(line)
            if tx:
                raw_transactions.append(tx)

        # Second pass: determine debit/credit using balance changes
        prev_balance = opening_balance if opening_balance is not None else 0.0
        signed_transactions: list[Transaction] = []

        for tx in raw_transactions:
            if tx.balance is not None:
                if abs((prev_balance + tx.amount) - tx.balance) < 0.01:
                    signed_amount = tx.amount  # credit (positive)
                elif abs((prev_balance - tx.amount) - tx.balance) < 0.01:
                    signed_amount = -tx.amount  # debit (negative)
                else:
                    # Fallback: use balance direction to determine sign
                    if tx.balance > prev_balance:
                        signed_amount = tx.amount  # balance went up = credit
                    else:
                        signed_amount = -tx.amount  # balance went down = debit
                prev_balance = tx.balance
            else:
                signed_amount = -tx.amount

            signed_transactions.append(Transaction(
                date=tx.date,
                description=tx.description,
                amount=signed_amount,
                balance=tx.balance,
                raw_text=tx.raw_text,
            ))

        return signed_transactions

    def _parse_transaction_line(self, line: str) -> Transaction | None:
        """Parse a single Investec transaction line."""
        date_pattern = r"(\d{1,2}\s+\w{3}\s+\d{4})"
        match = re.match(
            rf"^{date_pattern}\s+{date_pattern}\s+(.+?)\s+([\d,]+\.\d{{2}})\s+([\d,]+\.\d{{2}})$",
            line,
        )
        if not match:
            return None

        trans_date_str = match.group(2)
        description = match.group(3).strip()
        amount_str = match.group(4).replace(",", "")
        balance_str = match.group(5).replace(",", "")

        try:
            dt = datetime.strptime(trans_date_str, "%d %b %Y")
            date = dt.strftime("%Y-%m-%d")
        except ValueError:
            return None

        return Transaction(
            date=date,
            description=description,
            amount=float(amount_str),
            balance=float(balance_str),
            raw_text=line,
        )
