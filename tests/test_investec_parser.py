"""Tests for Investec parser module."""

from pathlib import Path

import pytest

from src.parsers.investec import InvestecParser
from src.parsers.base import Transaction, StatementData
from src.parsers import get_parser, list_available_parsers


@pytest.fixture
def parser():
    """Create an Investec parser instance."""
    return InvestecParser()


class TestInvestecParserMeta:
    """Tests for parser metadata."""

    def test_bank_name(self, parser):
        """Test bank name is correct."""
        assert parser.bank_name() == "investec"

    def test_parser_registered(self):
        """Test parser is discoverable via registry."""
        assert "investec" in list_available_parsers()

    def test_get_parser(self):
        """Test parser can be retrieved by name."""
        parser = get_parser("investec")
        assert isinstance(parser, InvestecParser)


class TestAccountNumberExtraction:
    """Tests for account number extraction."""

    def test_extract_account_number(self, parser):
        """Test extracting account number."""
        text = "Account Number 10014670887"
        result = parser._extract_account_number(text)
        assert result == "10014670887"

    def test_extract_account_number_not_found(self, parser):
        """Test when account number not found."""
        text = "Some random text without account number"
        result = parser._extract_account_number(text)
        assert result is None


class TestStatementDateExtraction:
    """Tests for statement date extraction."""

    def test_extract_statement_date(self, parser):
        """Test extracting statement date."""
        text = "Statement Date 31 January 2026"
        result = parser._extract_statement_date(text)
        assert result == "2026-01-31"

    def test_extract_statement_date_not_found(self, parser):
        """Test when statement date not found."""
        text = "Some random text"
        result = parser._extract_statement_date(text)
        assert result is None

    def test_extract_statement_number_from_date(self, parser):
        """Test statement number is derived from date as YYYY-MM."""
        text = "Statement Date 31 January 2026"
        date = parser._extract_statement_date(text)
        result = parser._derive_statement_number(date)
        assert result == "2026-01"


class TestTransactionParsing:
    """Tests for transaction line parsing."""

    def test_parse_credit_transaction(self, parser):
        """Test parsing a credit (deposit) transaction."""
        text = (
            "Transaction detail\n"
            "Posted Date Trans Date Transaction Description Debit Credit Balance\n"
            "Balance brought forward 0.00\n"
            "13 Jan 2026 13 Jan 2026 TRANSFER FNB 3,544.00 3,544.00\n"
            "Closing Balance 3,544.00\n"
            "Online payments, deposits, fees and interest\n"
        )
        result = parser._parse_transactions(text, "2026-01-31")
        assert len(result) == 1
        assert result[0].date == "2026-01-13"
        assert result[0].description == "TRANSFER FNB"
        assert result[0].amount == 3544.00
        assert result[0].balance == 3544.00

    def test_parse_debit_transaction(self, parser):
        """Test parsing a debit (payment) transaction."""
        text = (
            "Transaction detail\n"
            "Posted Date Trans Date Transaction Description Debit Credit Balance\n"
            "Balance brought forward 10,000.00\n"
            "13 Jan 2026 13 Jan 2026 KEANU PAYMENT 502.00 9,498.00\n"
            "Closing Balance 9,498.00\n"
            "Online payments, deposits, fees and interest\n"
        )
        result = parser._parse_transactions(text, "2026-01-31")
        assert len(result) == 1
        assert result[0].date == "2026-01-13"
        assert result[0].description == "KEANU PAYMENT"
        assert result[0].amount == -502.00
        assert result[0].balance == 9498.00

    def test_parse_multiple_transactions(self, parser):
        """Test parsing multiple transactions from a real statement excerpt."""
        text = (
            "Transaction detail\n"
            "Posted Date Trans Date Transaction Description Debit Credit Balance\n"
            "Balance brought forward 0.00\n"
            "13 Jan 2026 13 Jan 2026 TRANSFER FNB 3,544.00 3,544.00\n"
            "13 Jan 2026 13 Jan 2026 KEANU PAYMENT 502.00 3,042.00\n"
            "16 Jan 2026 16 Jan 2026 Dog Parlour 460.00 1,979.00\n"
            "22 Jan 2026 22 Jan 2026 TRANSFER FNB 61,000.00 62,499.00\n"
            "31 Jan 2026 31 Jan 2026 CARTRACK S104549692 185.90 27,693.10\n"
            "1 Feb 2026 31 Jan 2026 Credit interest 3.09 27,696.19\n"
            "Closing Balance 27,696.19\n"
            "Online payments, deposits, fees and interest\n"
        )
        result = parser._parse_transactions(text, "2026-01-31")
        assert len(result) == 6
        assert result[0].description == "TRANSFER FNB"
        assert result[0].amount == 3544.00
        assert result[1].description == "KEANU PAYMENT"
        assert result[1].amount == -502.00
        assert result[2].description == "Dog Parlour"
        assert result[2].amount == -460.00
        assert result[3].description == "TRANSFER FNB"
        assert result[3].amount == 61000.00
        assert result[4].description == "CARTRACK S104549692"
        assert result[4].amount == -185.90
        assert result[5].description == "Credit interest"
        assert result[5].date == "2026-01-31"
        assert result[5].amount == 3.09

    def test_skips_balance_brought_forward(self, parser):
        """Test that 'Balance brought forward' is skipped."""
        text = (
            "Transaction detail\n"
            "Posted Date Trans Date Transaction Description Debit Credit Balance\n"
            "Balance brought forward 0.00\n"
            "13 Jan 2026 13 Jan 2026 TRANSFER FNB 3,544.00 3,544.00\n"
            "Closing Balance 3,544.00\n"
            "Online payments, deposits, fees and interest\n"
        )
        result = parser._parse_transactions(text, "2026-01-31")
        assert len(result) == 1
        assert result[0].description == "TRANSFER FNB"

    def test_stops_at_online_payments_section(self, parser):
        """Test that parsing stops at the duplicate summary section."""
        text = (
            "Transaction detail\n"
            "Posted Date Trans Date Transaction Description Debit Credit Balance\n"
            "Balance brought forward 0.00\n"
            "13 Jan 2026 13 Jan 2026 TRANSFER FNB 3,544.00 3,544.00\n"
            "Closing Balance 3,544.00\n"
            "Online payments, deposits, fees and interest\n"
            "Trans Date Description Fees Debit Credit\n"
            "13 Jan 2026 TRANSFER FNB 3,544.00\n"
        )
        result = parser._parse_transactions(text, "2026-01-31")
        assert len(result) == 1

    def test_parse_transaction_with_reference_number(self, parser):
        """Test parsing a transaction with a long reference number."""
        text = (
            "Transaction detail\n"
            "Posted Date Trans Date Transaction Description Debit Credit Balance\n"
            "Balance brought forward 10,000.00\n"
            "22 Jan 2026 22 Jan 2026 Mr AM Kleynhans 1100114374501 603.00 9,397.00\n"
            "Closing Balance 9,397.00\n"
            "Online payments, deposits, fees and interest\n"
        )
        result = parser._parse_transactions(text, "2026-01-31")
        assert len(result) == 1
        assert result[0].description == "Mr AM Kleynhans 1100114374501"
        assert result[0].amount == -603.00


class TestEdgeCases:
    """Tests for edge cases and error paths."""

    def test_extract_statement_date_invalid_format(self, parser):
        """Test that invalid date format returns None."""
        text = "Statement Date 31 Foobar 2026"
        result = parser._extract_statement_date(text)
        assert result is None

    def test_derive_statement_number_none(self, parser):
        """Test derive statement number with None date."""
        assert parser._derive_statement_number(None) is None

    def test_parse_transaction_line_non_matching(self, parser):
        """Test that non-matching lines return None."""
        assert parser._parse_transaction_line("Some random text") is None

    def test_parse_transaction_line_invalid_date(self, parser):
        """Test that invalid month in transaction line returns None."""
        line = "13 Foo 2026 13 Foo 2026 TRANSFER FNB 3,544.00 3,544.00"
        assert parser._parse_transaction_line(line) is None

    def test_parse_transactions_with_empty_lines(self, parser):
        """Test that empty lines in transaction section are skipped."""
        text = (
            "Transaction detail\n"
            "Posted Date Trans Date Transaction Description Debit Credit Balance\n"
            "Balance brought forward 0.00\n"
            "\n"
            "   \n"
            "13 Jan 2026 13 Jan 2026 TRANSFER FNB 3,544.00 3,544.00\n"
            "Closing Balance 3,544.00\n"
            "Online payments, deposits, fees and interest\n"
        )
        result = parser._parse_transactions(text, "2026-01-31")
        assert len(result) == 1

    def test_signing_with_no_balance(self, parser):
        """Test that a transaction with no balance defaults to debit."""
        from unittest.mock import patch
        from src.parsers.base import Transaction

        no_balance_tx = Transaction(
            date="2026-01-13", description="TEST", amount=100.0,
            balance=None, raw_text="test",
        )

        # Inject a transaction with no balance via mocked _parse_transaction_line
        text = (
            "Transaction detail\n"
            "Posted Date Trans Date Transaction Description Debit Credit Balance\n"
            "Balance brought forward 0.00\n"
            "13 Jan 2026 13 Jan 2026 TEST 100.00 100.00\n"
            "Closing Balance 0.00\n"
            "Online payments, deposits, fees and interest\n"
        )
        with patch.object(parser, "_parse_transaction_line", return_value=no_balance_tx):
            result = parser._parse_transactions(text, "2026-01-31")
        assert len(result) == 1
        assert result[0].amount == -100.0  # defaults to debit


class TestFullPDFParsing:
    """Integration test with a real Investec statement PDF."""

    @pytest.fixture
    def sample_pdf_path(self):
        """Path to a real Investec statement for testing."""
        path = Path.home() / "Google Drive/My Drive/PERSONAL/INVESTEC/STATEMENTS/2026/Investec-Current-20260201.pdf"
        if not path.exists():
            pytest.skip("Sample Investec PDF not available")
        return path

    def test_full_parse(self, parser, sample_pdf_path):
        """Test parsing a complete real Investec statement."""
        result = parser.parse(sample_pdf_path)

        assert result.account_number == "10014670887"
        assert result.statement_date == "2026-01-31"
        assert result.statement_number == "2026-01"
        assert len(result.transactions) == 18

        first = result.transactions[0]
        assert first.date == "2026-01-13"
        assert first.description == "TRANSFER FNB"
        assert first.amount == 3544.00

        second = result.transactions[1]
        assert second.description == "KEANU PAYMENT"
        assert second.amount == -502.00

        last = result.transactions[-1]
        assert last.description == "Credit interest"
        assert last.amount == 3.09
        assert last.date == "2026-01-31"
