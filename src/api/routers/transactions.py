"""REST endpoints for transaction queries."""

import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..models import TransactionListResponse, TransactionSchema

router = APIRouter()


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    request: Request,
    limit: int = Query(20, ge=1, le=100, description="Number of transactions to return"),
    offset: int = Query(0, ge=0, description="Number of transactions to skip"),
) -> TransactionListResponse:
    """Get paginated list of transactions, ordered by date descending."""
    db = request.app.state.db
    transactions = db.get_all_transactions(limit=limit, offset=offset)
    stats = db.get_stats()

    return TransactionListResponse(
        transactions=[TransactionSchema(**tx) for tx in transactions],
        total=stats["total_transactions"],
        limit=limit,
        offset=offset,
    )


@router.get("/transactions/search")
async def search_transactions(
    request: Request,
    q: str = Query(..., min_length=1, description="Search term"),
) -> dict:
    """Search transactions by description, recipient, or raw text."""
    db = request.app.state.db
    results = db.search_transactions(q)
    return {"transactions": results, "count": len(results)}


@router.get("/transactions/category/{category}")
async def get_by_category(request: Request, category: str) -> dict:
    """Get all transactions for a specific category."""
    db = request.app.state.db
    results = db.get_transactions_by_category(category)
    return {"transactions": results, "count": len(results)}


@router.get("/transactions/type/{tx_type}")
async def get_by_type(request: Request, tx_type: str) -> dict:
    """Get transactions by type (debit or credit)."""
    if tx_type not in ("debit", "credit"):
        raise HTTPException(
            status_code=400, detail="Type must be 'debit' or 'credit'"
        )
    db = request.app.state.db
    results = db.get_transactions_by_type(tx_type)
    return {"transactions": results, "count": len(results)}


@router.get("/transactions/date-range")
async def get_by_date_range(
    request: Request,
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
) -> dict:
    """Get transactions within a date range."""
    if start > end:
        raise HTTPException(
            status_code=400, detail="Start date must be before or equal to end date"
        )
    db = request.app.state.db
    results = db.get_transactions_in_date_range(start.isoformat(), end.isoformat())
    return {"transactions": results, "count": len(results)}


@router.get("/transactions/statement/{statement_number}")
async def get_by_statement(request: Request, statement_number: str) -> dict:
    """Get all transactions for a specific statement."""
    db = request.app.state.db
    results = db.get_transactions_by_statement(statement_number)
    return {"transactions": results, "count": len(results)}


@router.get("/transactions/export")
async def export_transactions(
    request: Request,
    q: str | None = Query(None, description="Search query"),
    category: str | None = Query(None, description="Category filter"),
    statement: str | None = Query(None, description="Statement number"),
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
) -> StreamingResponse:
    """Export transactions as CSV file.

    Accepts filter parameters to export only matching transactions.
    If no filters provided, exports all transactions.
    """
    db = request.app.state.db

    # Determine which filter to apply (mutually exclusive)
    if q:
        transactions = db.search_transactions(q)
    elif category:
        transactions = db.get_transactions_by_category(category)
    elif statement:
        transactions = db.get_transactions_by_statement(statement)
    elif start_date and end_date:
        if start_date > end_date:
            raise HTTPException(
                status_code=400, detail="Start date must be before end date"
            )
        transactions = db.get_transactions_in_date_range(
            start_date.isoformat(), end_date.isoformat()
        )
    else:
        # No filter - get all transactions (no pagination limit)
        transactions = db.get_all_transactions(limit=100000, offset=0)

    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)

        # Header row
        headers = [
            "Date",
            "Description",
            "Amount",
            "Type",
            "Category",
            "Balance",
            "Statement",
            "Reference",
            "Recipient/Payer",
        ]
        writer.writerow(headers)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        # Data rows
        for tx in transactions:
            row = [
                tx.get("date", ""),
                tx.get("description", ""),
                tx.get("amount", ""),
                tx.get("transaction_type", ""),
                tx.get("category", ""),
                tx.get("balance", ""),
                tx.get("statement_number", ""),
                tx.get("reference", ""),
                tx.get("recipient_or_payer", ""),
            ]
            writer.writerow(row)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    # Generate filename with current date
    filename = f"transactions_{datetime.now().strftime('%Y-%m-%d')}.csv"

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
