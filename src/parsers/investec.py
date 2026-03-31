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
        """Parse transactions from statement text. Implemented in next task."""
        return []
