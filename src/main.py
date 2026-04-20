#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pdfplumber
import yaml
from rich.console import Console
from rich.table import Table

from .chat import ChatInterface
from .classifier import TransactionClassifier
from .config import get_config
from .database import Database
from .llm_backend import create_backend
from .parsers import list_available_parsers
from .watcher import StatementWatcher, import_existing, reimport_statement


console = Console()


def cmd_import(args: argparse.Namespace, config: dict) -> None:
    """Import all PDF statements from the statements directory."""
    # Allow command-line overrides
    statements_dir = args.path if args.path else config["paths"]["statements_dir"]
    bank = args.bank if args.bank else config["bank"]

    db = Database(config["paths"]["database"])
    backend = create_backend(config)
    classifier = TransactionClassifier(
        backend=backend,
        categories=config.get("categories"),
        classification_rules=config.get("classification_rules")
    )

    # Check LLM connection
    if not classifier.check_connection():
        console.print(
            f"[red]Cannot connect to LLM server or model '{config['llm']['model']}' "
            f"not found.[/red]"
        )
        console.print(
            f"[yellow]Available models: {classifier.get_available_models() or 'none'}[/yellow]"
        )
        console.print("[dim]Start LM Studio or your LLM server[/dim]")
        sys.exit(1)

    console.print(f"[dim]Importing from: {statements_dir}[/dim]")
    console.print(f"[dim]Using parser: {bank}[/dim]\n")

    count = import_existing(
        statements_dir=statements_dir,
        db=db,
        bank=bank,
        classifier=classifier,
        pdf_password=config.get("pdf_password")
    )

    console.print(f"\n[bold]Imported {count} new statement(s)[/bold]")


def cmd_watch(args: argparse.Namespace, config: dict) -> None:
    """Watch for new statements and import them automatically."""
    db = Database(config["paths"]["database"])
    backend = create_backend(config)
    classifier = TransactionClassifier(
        backend=backend,
        categories=config.get("categories"),
        classification_rules=config.get("classification_rules")
    )

    if not classifier.check_connection():
        console.print(
            f"[red]Cannot connect to LLM server or model '{config['llm']['model']}' "
            f"not found.[/red]"
        )
        sys.exit(1)

    watcher = StatementWatcher(
        statements_dir=config["paths"]["statements_dir"],
        db=db,
        bank=config["bank"],
        classifier=classifier,
        pdf_password=config.get("pdf_password")
    )
    watcher.start()


def cmd_chat(args: argparse.Namespace, config: dict) -> None:
    """Start interactive chat interface."""
    db = Database(config["paths"]["database"])

    stats = db.get_stats()
    if stats["total_transactions"] == 0:
        console.print("[yellow]No transactions in database.[/yellow]")
        console.print(
            f"[dim]Place PDF statements in {config['paths']['statements_dir']} "
            f"and run 'import' first.[/dim]"
        )
        sys.exit(1)

    backend = create_backend(config)
    chat = ChatInterface(db=db, backend=backend)
    chat.start()


def cmd_list(args: argparse.Namespace, config: dict) -> None:
    """List transactions."""
    db = Database(config["paths"]["database"])

    limit = args.limit or 20
    transactions = db.get_all_transactions(limit=limit)

    if not transactions:
        console.print("[yellow]No transactions found.[/yellow]")
        return

    table = Table(title=f"Recent Transactions (showing {len(transactions)})")
    table.add_column("Date", style="cyan")
    table.add_column("Description")
    table.add_column("Amount", justify="right")
    table.add_column("Type", style="dim")
    table.add_column("Category", style="magenta")

    for tx in transactions:
        amount = tx.get("amount", 0)
        tx_type = tx.get("transaction_type", "")

        if tx_type == "debit":
            amount_str = f"[red]-R{amount:.2f}[/red]"
        else:
            amount_str = f"[green]+R{amount:.2f}[/green]"

        table.add_row(
            tx.get("date", ""),
            tx.get("description", "")[:40],
            amount_str,
            tx_type,
            tx.get("category", "") or "-"
        )

    console.print(table)


def cmd_categories(args: argparse.Namespace, config: dict) -> None:
    """Show transaction categories and spending summary."""
    db = Database(config["paths"]["database"])

    summary = db.get_category_summary()

    if not summary:
        console.print("[yellow]No transactions found.[/yellow]")
        return

    table = Table(title="Spending by Category")
    table.add_column("Category")
    table.add_column("Count", justify="right")
    table.add_column("Total Debits", justify="right", style="red")
    table.add_column("Total Credits", justify="right", style="green")

    for row in summary:
        table.add_row(
            row.get("category") or "uncategorized",
            str(row.get("count", 0)),
            f"R{row.get('total_debits', 0):.2f}",
            f"R{row.get('total_credits', 0):.2f}"
        )

    console.print(table)


def cmd_stats(args: argparse.Namespace, config: dict) -> None:
    """Show database statistics."""
    db = Database(config["paths"]["database"])
    stats = db.get_stats()

    table = Table(title="Database Statistics")
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    table.add_row("Total Statements", str(stats.get("total_statements", 0)))
    table.add_row("Total Transactions", str(stats.get("total_transactions", 0)))
    table.add_row("Total Debits", f"R{stats.get('total_debits', 0):.2f}")
    table.add_row("Total Credits", f"R{stats.get('total_credits', 0):.2f}")
    table.add_row("Categories", str(stats.get("categories_count", 0)))

    console.print(table)


def cmd_search(args: argparse.Namespace, config: dict) -> None:
    """Search transactions."""
    db = Database(config["paths"]["database"])

    results = db.search_transactions(args.term)

    if not results:
        console.print(f"[yellow]No transactions matching '{args.term}'[/yellow]")
        return

    table = Table(title=f"Search Results: '{args.term}' ({len(results)} found)")
    table.add_column("Date", style="cyan")
    table.add_column("Description")
    table.add_column("Amount", justify="right")
    table.add_column("Category", style="magenta")

    for tx in results[:50]:
        amount = tx.get("amount", 0)
        tx_type = tx.get("transaction_type", "")

        if tx_type == "debit":
            amount_str = f"[red]-R{amount:.2f}[/red]"
        else:
            amount_str = f"[green]+R{amount:.2f}[/green]"

        table.add_row(
            tx.get("date", ""),
            tx.get("description", "")[:50],
            amount_str,
            tx.get("category", "") or "-"
        )

    console.print(table)


def cmd_parsers(args: argparse.Namespace, config: dict) -> None:
    """List available bank parsers."""
    parsers = list_available_parsers()
    current = config.get("bank", "")

    console.print("[bold]Available Bank Parsers:[/bold]")
    for parser in parsers:
        marker = " [green](active)[/green]" if parser == current else ""
        console.print(f"  - {parser}{marker}")

    if not parsers:
        console.print("  [dim]No parsers available[/dim]")


def cmd_rename(args: argparse.Namespace, config: dict) -> None:
    """Rename statement PDFs to standardized format: {number}_{month}_{year}.pdf"""
    statements_dir = Path(config["paths"]["statements_dir"])

    if not statements_dir.exists():
        console.print(f"[red]Statements directory not found: {statements_dir}[/red]")
        sys.exit(1)

    # Pattern for already-renamed files: 287_Oct_2025.pdf
    expected_pattern = re.compile(r"^\d+_[A-Z][a-z]{2}_\d{4}\.pdf$")

    renamed = 0
    skipped = 0
    errors = 0

    for pdf_file in sorted(statements_dir.glob("*.pdf")):
        # Skip if already in correct format
        if expected_pattern.match(pdf_file.name):
            console.print(f"[dim]SKIP: {pdf_file.name} (already correct format)[/dim]")
            skipped += 1
            continue

        try:
            with pdfplumber.open(pdf_file) as pdf:
                text = pdf.pages[0].extract_text() or ""

            # Extract Tax Invoice/Statement Number (with or without spaces)
            match = re.search(r"Tax\s*Invoice/Statement\s*Number\s*[:\s]+(\d+)", text, re.IGNORECASE)
            if not match:
                console.print(f"[yellow]SKIP: {pdf_file.name} - no statement number found[/yellow]")
                skipped += 1
                continue
            statement_num = match.group(1)

            # Extract Statement Date (with or without spaces)
            match = re.search(r"Statement\s*Date\s*[:\s]+(\d{1,2}\s*\w+\s*\d{4})", text, re.IGNORECASE)
            if not match:
                console.print(f"[yellow]SKIP: {pdf_file.name} - no statement date found[/yellow]")
                skipped += 1
                continue

            # Parse date - handle with or without spaces
            date_str = match.group(1)
            # Add spaces if missing (e.g., "1February2025" -> "1 February 2025")
            date_str = re.sub(r"(\d+)([A-Za-z])", r"\1 \2", date_str)
            date_str = re.sub(r"([A-Za-z])(\d)", r"\1 \2", date_str)
            try:
                date_obj = datetime.strptime(date_str, "%d %B %Y")
            except ValueError:
                date_obj = datetime.strptime(date_str, "%d %b %Y")

            month = date_obj.strftime("%b")
            year = date_obj.strftime("%Y")

            new_name = f"{statement_num}_{month}_{year}.pdf"
            new_path = statements_dir / new_name

            if new_path.exists() and new_path != pdf_file:
                console.print(f"[yellow]SKIP: {pdf_file.name} -> {new_name} (target exists)[/yellow]")
                skipped += 1
                continue

            pdf_file.rename(new_path)
            console.print(f"[green]RENAMED: {pdf_file.name} -> {new_name}[/green]")
            renamed += 1

        except Exception as e:
            console.print(f"[red]ERROR: {pdf_file.name} - {e}[/red]")
            errors += 1

    console.print(f"\n[bold]Summary: {renamed} renamed, {skipped} skipped, {errors} errors[/bold]")


def cmd_reimport(args: argparse.Namespace, config: dict) -> None:
    """Re-import PDF statement(s) (deletes existing and re-imports)."""
    # Handle "all" as positional argument (bankbot reimport all)
    if args.file == "all":
        args.all = True
        args.file = None

    # Validate arguments
    if not args.all and not args.file:
        console.print("[red]Error: Must specify a file or use --all[/red]")
        sys.exit(1)

    bank = args.bank if args.bank else config["bank"]

    db = Database(config["paths"]["database"])
    backend = create_backend(config)
    classifier = TransactionClassifier(
        backend=backend,
        categories=config.get("categories"),
        classification_rules=config.get("classification_rules")
    )

    # Check LLM connection
    if not classifier.check_connection():
        console.print(
            f"[red]Cannot connect to LLM server or model '{config['llm']['model']}' "
            f"not found.[/red]"
        )
        sys.exit(1)

    if args.all:
        # Reimport all PDF files
        statements_dir = Path(config["paths"]["statements_dir"])
        pdf_files = sorted(statements_dir.glob("*.pdf"))

        if not pdf_files:
            console.print(f"[yellow]No PDF files found in {statements_dir}[/yellow]")
            return

        console.print(f"[bold]Re-importing {len(pdf_files)} PDF files...[/bold]\n")

        success_count = 0
        fail_count = 0

        for pdf_path in pdf_files:
            console.print(f"[dim]Re-importing: {pdf_path.name}[/dim]")
            success = reimport_statement(
                pdf_path=pdf_path,
                db=db,
                bank=bank,
                classifier=classifier,
                pdf_password=config.get("pdf_password")
            )
            if success:
                success_count += 1
            else:
                fail_count += 1
                console.print(f"[red]Failed: {pdf_path.name}[/red]")

        console.print(f"\n[bold]Summary: {success_count} succeeded, {fail_count} failed[/bold]")
    else:
        # Reimport single file
        pdf_path = Path(args.file)

        if not pdf_path.exists():
            console.print(f"[red]File not found: {pdf_path}[/red]")
            sys.exit(1)

        console.print(f"[dim]Re-importing: {pdf_path}[/dim]")
        console.print(f"[dim]Using parser: {bank}[/dim]\n")

        success = reimport_statement(
            pdf_path=pdf_path,
            db=db,
            bank=bank,
            classifier=classifier,
            pdf_password=config.get("pdf_password")
        )

        if success:
            console.print("\n[bold green]Re-import completed successfully[/bold green]")
        else:
            console.print("\n[bold red]Re-import failed[/bold red]")
            sys.exit(1)


def cmd_export_budget(args: argparse.Namespace, config: dict) -> None:
    """Export budgets to a file."""
    db = Database(config["paths"]["database"])
    budgets = db.get_all_budgets()

    if not budgets:
        console.print("[yellow]No budgets to export[/yellow]")
        return

    # Prepare export data (just category and amount)
    export_data = [{"category": b["category"], "amount": b["amount"]} for b in budgets]

    output_path = Path(args.output)
    file_format = args.format or output_path.suffix.lstrip(".") or "json"

    if file_format in ("yaml", "yml"):
        content = yaml.dump({"budgets": export_data}, default_flow_style=False, sort_keys=False)
    else:
        content = json.dumps({"budgets": export_data}, indent=2)

    output_path.write_text(content)
    console.print(f"[green]Exported {len(export_data)} budgets to {output_path}[/green]")


def cmd_import_budget(args: argparse.Namespace, config: dict) -> None:
    """Import budgets from a file."""
    input_path = Path(args.input)

    if not input_path.exists():
        console.print(f"[red]File not found: {input_path}[/red]")
        sys.exit(1)

    content = input_path.read_text()
    file_format = input_path.suffix.lstrip(".")

    try:
        if file_format in ("yaml", "yml"):
            data = yaml.safe_load(content)
        else:
            data = json.loads(content)
    except (yaml.YAMLError, json.JSONDecodeError) as e:
        console.print(f"[red]Failed to parse file: {e}[/red]")
        sys.exit(1)

    budgets = data.get("budgets", [])
    if not budgets:
        console.print("[yellow]No budgets found in file[/yellow]")
        return

    db = Database(config["paths"]["database"])

    # Clear existing budgets before importing
    deleted = db.delete_all_budgets()
    if deleted > 0:
        console.print(f"[dim]Cleared {deleted} existing budget(s)[/dim]")

    imported = 0
    for budget in budgets:
        category = budget.get("category")
        amount = budget.get("amount")

        if not category or amount is None:
            console.print(f"[yellow]Skipping invalid budget entry: {budget}[/yellow]")
            continue

        db.upsert_budget(category, float(amount))
        imported += 1

    console.print(f"[green]Imported {imported} budgets from {input_path}[/green]")


def cmd_update_bank(args: argparse.Namespace, config: dict) -> None:
    """Update bank for existing statements that have no bank set."""
    from .database import Database

    db_path = config.get("paths", {}).get("database", "./data/statements.db")
    db = Database(db_path)

    # Use provided bank or fall back to config
    bank = args.bank or config.get("bank", "fnb")

    updated = db.update_statements_bank(bank)

    if updated > 0:
        console.print(f"[green]Updated {updated} statement(s) with bank: {bank}[/green]")
    else:
        console.print("[yellow]No statements needed updating (all already have bank set)[/yellow]")


def cmd_fetch_investec(args: argparse.Namespace, config: dict) -> None:
    """Fetch transactions from the Investec Programmable Banking API."""
    from .investec_api import InvestecAPI

    investec_config = config.get("investec", {})

    # Environment variables take precedence over config
    client_id = os.environ.get("INVESTEC_CLIENT_ID") or investec_config.get("client_id", "")
    client_secret = os.environ.get("INVESTEC_CLIENT_SECRET") or investec_config.get("client_secret", "")
    api_key = os.environ.get("INVESTEC_API_KEY") or investec_config.get("api_key", "")

    if not all([client_id, client_secret, api_key]):
        console.print("[red]Investec API credentials not configured.[/red]")
        console.print(
            "[dim]Set them in config.yaml under 'investec' or via environment variables:\n"
            "  INVESTEC_CLIENT_ID, INVESTEC_CLIENT_SECRET, INVESTEC_API_KEY[/dim]"
        )
        sys.exit(1)

    api = InvestecAPI(client_id, client_secret, api_key)

    # Load the LLM before authenticating: the Investec access token has a short
    # TTL, and a cold MLX model load (first run downloads several GB) can burn
    # enough of it to expire the token before classification runs.
    db = None
    classifier = None
    if not args.list_accounts:
        db = Database(config["paths"]["database"])
        backend = create_backend(config)
        classifier = TransactionClassifier(
            backend=backend,
            categories=config.get("categories"),
            classification_rules=config.get("classification_rules"),
        )
        if not classifier.check_connection():
            console.print("[red]Cannot connect to LLM server[/red]")
            sys.exit(1)

    try:
        api.authenticate()
        console.print("[green]Authenticated with Investec API[/green]")
    except Exception as e:
        console.print(f"[red]Authentication failed: {e}[/red]")
        sys.exit(1)

    # List accounts mode
    if args.list_accounts:
        accounts = api.get_accounts()
        table = Table(title="Investec Accounts")
        table.add_column("Account ID")
        table.add_column("Account Number")
        table.add_column("Name")
        table.add_column("Product")
        for acc in accounts:
            table.add_row(
                acc.get("accountId", ""),
                acc.get("accountNumber", ""),
                acc.get("referenceName", acc.get("accountName", "")),
                acc.get("productName", ""),
            )
        console.print(table)
        return

    # Determine date range
    if args.from_date and args.to_date:
        from_date = args.from_date
        to_date = args.to_date
    else:
        today = datetime.now()
        from_date = today.replace(day=1).strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")

    # Determine which accounts to fetch
    accounts = api.get_accounts()

    if args.account:
        account_ids = [args.account]
    elif args.all:
        account_ids = [acc["accountId"] for acc in accounts]
    elif len(accounts) == 1:
        account_ids = [accounts[0]["accountId"]]
    else:
        console.print("[yellow]Multiple accounts found. Specify --account <id> or --all[/yellow]")
        for acc in accounts:
            console.print(f"  {acc['accountId']} - {acc.get('accountNumber', '')} ({acc.get('referenceName', '')})")
        sys.exit(1)

    for account_id in account_ids:
        console.print(f"\n[cyan]Fetching transactions for account {account_id}...[/cyan]")
        console.print(f"[dim]Date range: {from_date} to {to_date}[/dim]")

        synthetic_filename = f"investec_api_{account_id}_{from_date}_{to_date}"
        if db.statement_exists(synthetic_filename):
            console.print("[yellow]Already imported this exact range. Skipping.[/yellow]")
            continue

        try:
            # Look up account number to avoid extra API call
            acct_number = next(
                (a["accountNumber"] for a in accounts if a["accountId"] == account_id), None
            )
            statement_data = api.fetch_as_statement_data(
                account_id, from_date, to_date, account_number=acct_number
            )
        except Exception as e:
            console.print(f"[red]Failed to fetch transactions: {e}[/red]")
            continue

        if not statement_data.transactions:
            console.print("[yellow]No transactions found for this period.[/yellow]")
            continue

        # Deduplicate against existing transactions
        account_number = statement_data.account_number or ""
        original_count = len(statement_data.transactions)
        deduped_transactions = [
            tx for tx in statement_data.transactions
            if not db.transaction_exists(
                account_number=account_number,
                date=tx.date,
                description=tx.description,
                amount=abs(tx.amount),
            )
        ]
        skipped = original_count - len(deduped_transactions)
        if skipped:
            console.print(f"[dim]  Skipped {skipped} duplicate transaction(s)[/dim]")

        if not deduped_transactions:
            console.print("[yellow]All transactions already exist. Nothing to import.[/yellow]")
            continue

        # Insert statement record
        statement_id = db.insert_statement(
            filename=synthetic_filename,
            bank="investec",
            account_number=statement_data.account_number,
            statement_date=statement_data.statement_date,
            statement_number=statement_data.statement_number,
        )

        # Classify and insert
        from .watcher import _classify_and_prepare
        transactions_to_classify = _classify_and_prepare(
            deduped_transactions, classifier, console
        )
        db.insert_transactions_batch(statement_id, transactions_to_classify)

        console.print(
            f"[green]Imported {len(transactions_to_classify)} transactions[/green]"
        )


def cmd_serve(args: argparse.Namespace, config: dict) -> None:
    """Start the API server."""
    import uvicorn

    from .api.app import app

    host = args.host
    port = args.port

    console.print(f"[bold green]Starting API server...[/bold green]")
    console.print(f"[dim]WebSocket: ws://{host}:{port}/ws/chat[/dim]")
    console.print(f"[dim]REST API:  http://{host}:{port}/api/v1/...[/dim]")
    console.print(f"[dim]API Docs:  http://{host}:{port}/docs[/dim]")
    console.print()

    uvicorn.run(app, host=host, port=port, log_level="info")


def cmd_debug_ocr(args: argparse.Namespace, config: dict) -> None:
    """Debug OCR output for a PDF file."""
    import io

    import fitz
    import pytesseract
    from PIL import Image

    pdf_path = Path(args.file)

    if not pdf_path.exists():
        console.print(f"[red]File not found: {pdf_path}[/red]")
        sys.exit(1)

    console.print(f"[bold]OCR Debug for: {pdf_path.name}[/bold]\n")

    doc = fitz.open(pdf_path)
    page_num = args.page - 1 if args.page else 0

    if page_num >= len(doc):
        console.print(f"[red]Page {args.page} not found (PDF has {len(doc)} pages)[/red]")
        sys.exit(1)

    page = doc[page_num]

    # Render at high resolution
    scale = args.scale or 4
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    img = Image.open(io.BytesIO(pix.tobytes("png")))

    console.print(f"[dim]Page {page_num + 1}, Scale {scale}x, Image size: {img.size}[/dim]\n")

    # Save rendered image for inspection
    if args.save_image:
        img_path = pdf_path.with_suffix(f".page{page_num + 1}.png")
        img.save(img_path)
        console.print(f"[green]Saved rendered image to: {img_path}[/green]\n")

    # Try different OCR configs
    configs = [
        ("Default", ""),
        ("PSM 6 (Uniform block)", "--psm 6"),
        ("PSM 4 (Single column)", "--psm 4"),
        ("PSM 11 (Sparse text)", "--psm 11"),
        ("PSM 3 (Full auto)", "--psm 3"),
    ]

    for name, ocr_config in configs:
        console.print(f"[bold cyan]Config: {name}[/bold cyan]")
        console.print("-" * 60)

        # Convert to grayscale
        gray_img = img.convert("L")
        ocr_text = pytesseract.image_to_string(gray_img, config=ocr_config)

        # Find lines with dates (transaction lines) or # descriptions
        lines = ocr_text.split("\n")
        date_pattern = re.compile(r"\d{1,2}\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", re.IGNORECASE)

        for line in lines:
            if date_pattern.search(line) or "#" in line:
                console.print(f"  [yellow]{line}[/yellow]")

        console.print()

    # Also show what pdfplumber extracts
    console.print(f"[bold cyan]pdfplumber text extraction:[/bold cyan]")
    console.print("-" * 60)
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        page_text = pdf.pages[page_num].extract_text() or ""
        lines = page_text.split("\n")
        date_pattern = re.compile(r"\d{1,2}\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", re.IGNORECASE)
        for line in lines:
            if date_pattern.search(line) or "#" in line:
                console.print(f"  [green]{line}[/green]")

    # Also try PyMuPDF text extraction with layout
    console.print(f"\n[bold cyan]PyMuPDF text extraction (with layout):[/bold cyan]")
    console.print("-" * 60)
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        if block.get("type") == 0:  # Text block
            for line in block.get("lines", []):
                line_text = "".join(span.get("text", "") for span in line.get("spans", []))
                if date_pattern.search(line_text) or "#" in line_text:
                    console.print(f"  [magenta]{line_text}[/magenta]")

    doc.close()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Bank Statement Chat Bot - Parse and query your bank statements with AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s import               Import all PDFs from statements directory
  %(prog)s watch                Watch for new statements and auto-import
  %(prog)s chat                 Start interactive chat
  %(prog)s list                 List recent transactions
  %(prog)s search "doctor"      Search for transactions
  %(prog)s categories           Show spending by category
  %(prog)s reimport 288_Dec.pdf Re-import a specific statement
        """
    )

    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Import command
    import_parser = subparsers.add_parser("import", help="Import PDF statements")
    import_parser.add_argument("--path", help="Path to statements directory (overrides config)")
    import_parser.add_argument("--bank", help="Bank parser to use (overrides config)")

    # Watch command
    subparsers.add_parser("watch", help="Watch for new statements")

    # Chat command
    subparsers.add_parser("chat", help="Start interactive chat")

    # List command
    list_parser = subparsers.add_parser("list", help="List transactions")
    list_parser.add_argument("-n", "--limit", type=int, help="Number of transactions")

    # Categories command
    subparsers.add_parser("categories", help="Show category summary")

    # Stats command
    subparsers.add_parser("stats", help="Show database statistics")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search transactions")
    search_parser.add_argument("term", help="Search term")

    # Parsers command
    subparsers.add_parser("parsers", help="List available bank parsers")

    # Rename command
    subparsers.add_parser("rename", help="Rename PDFs to {number}_{month}_{year}.pdf format")

    # Reimport command
    reimport_parser = subparsers.add_parser("reimport", help="Re-import PDF statement(s)")
    reimport_parser.add_argument("file", nargs="?", help="Path to the PDF file to re-import")
    reimport_parser.add_argument("--all", action="store_true", help="Re-import all PDF files in statements directory")
    reimport_parser.add_argument("--bank", help="Bank parser to use (overrides config)")

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start API server")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind to (default: 8000)")

    # Export budget command
    export_budget_parser = subparsers.add_parser("export-budget", help="Export budgets to a file")
    export_budget_parser.add_argument("output", help="Output file path (e.g., budgets.json or budgets.yaml)")
    export_budget_parser.add_argument("--format", choices=["json", "yaml"], help="Output format (auto-detected from extension)")

    # Import budget command
    import_budget_parser = subparsers.add_parser("import-budget", help="Import budgets from a file")
    import_budget_parser.add_argument("input", help="Input file path (e.g., budgets.json or budgets.yaml)")

    # Debug OCR command
    debug_ocr_parser = subparsers.add_parser("debug-ocr", help="Debug OCR output for a PDF file")
    debug_ocr_parser.add_argument("file", help="Path to the PDF file")
    debug_ocr_parser.add_argument("--page", type=int, default=1, help="Page number to analyze (default: 1)")
    debug_ocr_parser.add_argument("--scale", type=int, default=4, help="Image scale factor (default: 4)")
    debug_ocr_parser.add_argument("--save-image", action="store_true", help="Save rendered image for inspection")

    # Update bank command
    update_bank_parser = subparsers.add_parser("update-bank", help="Update bank for existing statements")
    update_bank_parser.add_argument("--bank", help="Bank name to set (default: from config)")

    # Fetch Investec command
    fetch_investec_parser = subparsers.add_parser(
        "fetch-investec", help="Fetch transactions from Investec API"
    )
    fetch_investec_parser.add_argument(
        "--from-date", help="Start date YYYY-MM-DD (default: 1st of current month)"
    )
    fetch_investec_parser.add_argument(
        "--to-date", help="End date YYYY-MM-DD (default: today)"
    )
    fetch_investec_parser.add_argument(
        "--account", help="Investec account ID to fetch"
    )
    fetch_investec_parser.add_argument(
        "--all", action="store_true", help="Fetch all accounts"
    )
    fetch_investec_parser.add_argument(
        "--list-accounts", action="store_true", help="List available accounts and exit"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load config
    try:
        config = get_config() if args.config == "config.yaml" else __import__("yaml").safe_load(open(args.config))
    except FileNotFoundError:
        console.print(f"[red]Config file not found: {args.config}[/red]")
        console.print("[dim]Create config.yaml or specify path with -c[/dim]")
        sys.exit(1)

    # Dispatch command
    commands = {
        "import": cmd_import,
        "watch": cmd_watch,
        "chat": cmd_chat,
        "list": cmd_list,
        "categories": cmd_categories,
        "stats": cmd_stats,
        "search": cmd_search,
        "parsers": cmd_parsers,
        "rename": cmd_rename,
        "reimport": cmd_reimport,
        "serve": cmd_serve,
        "export-budget": cmd_export_budget,
        "import-budget": cmd_import_budget,
        "debug-ocr": cmd_debug_ocr,
        "update-bank": cmd_update_bank,
        "fetch-investec": cmd_fetch_investec,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args, config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
