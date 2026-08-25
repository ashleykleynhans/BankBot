"""REST endpoints for cashflow forecasting."""

from fastapi import APIRouter, HTTPException, Query, Request

from ...forecast import ForecastEngine
from ..models import (
    AffordabilityResponse,
    BalanceForecastResponse,
    RecurringListResponse,
)

router = APIRouter()

MAX_HORIZON_DAYS = 400


@router.get("/forecast/recurring", response_model=RecurringListResponse)
async def get_recurring(
    request: Request,
    min_count: int = Query(3, ge=2, le=52, description="Minimum occurrences"),
    account: str | None = Query(None, description="Restrict to one bank account"),
) -> RecurringListResponse:
    """Detect recurring payments and income from transaction history."""
    db = request.app.state.db
    items = ForecastEngine(db).detect_recurring(
        min_occurrences=min_count,
        account=account,
    )
    inflow = sum(i["monthly_equivalent"] for i in items if i["direction"] == "in")
    outflow = sum(i["monthly_equivalent"] for i in items if i["direction"] == "out")
    return RecurringListResponse(
        items=items,
        total_monthly_inflow=round(inflow, 2),
        total_monthly_outflow=round(outflow, 2),
    )


@router.get("/forecast/balance", response_model=BalanceForecastResponse)
async def get_balance_forecast(
    request: Request,
    days: int = Query(31, ge=1, le=MAX_HORIZON_DAYS, description="Horizon in days"),
    include_burn: bool = Query(True, description="Apply average daily non-recurring spend"),
    buffer: float = Query(0.0, ge=0.0, description="Safety buffer to warn against"),
    account: str | None = Query(
        None, description="Bank account (defaults to the most recently active one)"
    ),
) -> BalanceForecastResponse:
    """Project daily balances forward and highlight cashflow risks."""
    db = request.app.state.db
    forecast = ForecastEngine(db).project(
        days=days,
        include_burn=include_burn,
        safety_buffer=buffer,
        account=account,
    )
    return BalanceForecastResponse(**forecast)


@router.get("/forecast/afford", response_model=AffordabilityResponse)
async def check_affordability(
    request: Request,
    amount: float = Query(..., gt=0, description="Expense amount in rands"),
    days_ahead: int = Query(
        0, ge=0, le=MAX_HORIZON_DAYS, description="Days until the expense"
    ),
    account: str | None = Query(None, description="Bank account to check against"),
) -> AffordabilityResponse:
    """Answer whether spending an amount on a future date is affordable."""
    db = request.app.state.db
    result = ForecastEngine(db).can_afford(amount, days_ahead=days_ahead, account=account)
    return AffordabilityResponse(**result)
