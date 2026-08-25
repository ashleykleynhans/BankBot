"""Pydantic models for API request/response schemas."""

from pydantic import BaseModel


class TransactionSchema(BaseModel):
    """Schema for a single transaction."""

    model_config = {"from_attributes": True}

    id: int
    date: str
    description: str
    amount: float
    balance: float | None = None
    transaction_type: str
    category: str | None = None
    recipient_or_payer: str | None = None
    reference: str | None = None
    bank: str | None = None
    statement_number: str | None = None


class TransactionListResponse(BaseModel):
    """Response for paginated transaction list."""

    transactions: list[TransactionSchema]
    total: int
    limit: int
    offset: int


class TransactionSearchResponse(BaseModel):
    """Response for transaction search."""

    transactions: list[dict]
    count: int


class StatsResponse(BaseModel):
    """Response for database statistics."""

    total_statements: int
    total_transactions: int
    total_debits: float
    total_credits: float
    categories_count: int


class CategorySummaryItem(BaseModel):
    """Single category in summary."""

    category: str | None
    count: int
    total_debits: float
    total_credits: float


class CategorySummaryResponse(BaseModel):
    """Response for category spending summary."""

    categories: list[CategorySummaryItem]


class CategoriesListResponse(BaseModel):
    """Response for list of categories."""

    categories: list[str]


class ChatMessage(BaseModel):
    """Incoming chat message."""

    type: str
    payload: dict | None = None


class ChatResponsePayload(BaseModel):
    """Payload for chat response."""

    message: str
    transactions: list[dict]
    timestamp: str


class ChatResponse(BaseModel):
    """WebSocket chat response."""

    type: str
    payload: dict


# Budget models
class BudgetCreate(BaseModel):
    """Request to create a budget."""

    category: str
    amount: float


class BudgetUpdate(BaseModel):
    """Request to update a budget."""

    amount: float


class BudgetResponse(BaseModel):
    """Single budget entry."""

    id: int
    category: str
    amount: float


class BudgetListResponse(BaseModel):
    """Response for list of budgets."""

    budgets: list[BudgetResponse]


class BudgetSummaryItem(BaseModel):
    """Budget with actual spending comparison."""

    category: str
    budget: float
    actual: float
    remaining: float
    percentage: float  # 0-100+, can exceed 100 if over budget


class BudgetSummaryResponse(BaseModel):
    """Response for budget summary with actuals."""

    items: list[BudgetSummaryItem]
    total_budgeted: float
    total_spent: float


class BudgetExportItem(BaseModel):
    """Single budget entry for export/import."""

    category: str
    amount: float


class BudgetExportResponse(BaseModel):
    """Response for budget export."""

    budgets: list[BudgetExportItem]


class BudgetImportRequest(BaseModel):
    """Request to import budgets."""

    budgets: list[BudgetExportItem]


class BudgetImportResponse(BaseModel):
    """Response for budget import."""

    imported: int
    deleted: int


# Analytics models
class StatementInfo(BaseModel):
    """Basic statement information."""

    id: int
    statement_number: str | None
    statement_date: str | None
    account_number: str | None


class StatementListResponse(BaseModel):
    """Response for list of statements."""

    statements: list[StatementInfo]


class AnalyticsResponse(BaseModel):
    """Response for analytics data."""

    statement_number: str | None
    statement_date: str | None
    total_debits: float
    total_credits: float
    transaction_count: int
    categories: list[CategorySummaryItem]


# Forecast models
class UpcomingDebit(BaseModel):
    """A recurring debit expected within the next few days."""

    merchant: str
    amount: float
    date: str


class RiskAlert(BaseModel):
    """Cashflow risk detected in the projection."""

    severity: str  # critical, warning, ok, info
    date: str | None = None
    message: str


class RecurringItem(BaseModel):
    """A detected recurring payment or income source."""

    key: str
    merchant: str
    description_sample: str
    category: str | None = None
    direction: str  # in, out
    cadence: str  # weekly, fortnightly, monthly
    interval_days: int
    typical_amount: float
    last_amount: float
    last_date: str
    next_date: str
    occurrences: int
    confidence: str  # high, medium, low
    active: bool
    monthly_equivalent: float


class RecurringListResponse(BaseModel):
    """Response for recurring payment detection."""

    items: list[RecurringItem]
    total_monthly_inflow: float
    total_monthly_outflow: float


class ForecastPoint(BaseModel):
    """Projected balance on a single day."""

    date: str
    balance: float


class BalanceForecastResponse(BaseModel):
    """Response for the balance projection."""

    as_of: str
    days: int
    account: str | None
    start_balance: float | None
    start_balance_date: str | None
    end_balance: float | None
    lowest_balance: float | None
    lowest_date: str | None
    daily_burn: float
    include_burn: bool
    committed_monthly_inflow: float
    committed_monthly_outflow: float
    points: list[ForecastPoint]
    risks: list[RiskAlert]
    upcoming_debits: list[UpcomingDebit]
    recurring_count: int


class AffordabilityResponse(BaseModel):
    """Response for an affordability check."""

    amount: float
    target_date: str
    account: str | None
    affordable: bool | None
    reason: str | None
    lowest_balance_after: float | None
    lowest_date_after: str | None
    headroom_before_purchase: float | None
    upcoming_debits_before_target: list[UpcomingDebit]
