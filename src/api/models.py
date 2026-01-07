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
