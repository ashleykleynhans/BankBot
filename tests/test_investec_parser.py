"""Tests for Investec parser module."""

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
