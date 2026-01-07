"""REST endpoints for statistics and categories."""

from fastapi import APIRouter, Request

from ..models import (
    CategoriesListResponse,
    CategorySummaryItem,
    CategorySummaryResponse,
    StatsResponse,
)

router = APIRouter()


@router.get("/stats", response_model=StatsResponse)
async def get_stats(request: Request) -> StatsResponse:
    """Get database statistics."""
    db = request.app.state.db
    stats = db.get_stats()
    return StatsResponse(**stats)


@router.get("/categories", response_model=CategoriesListResponse)
async def list_categories(request: Request) -> CategoriesListResponse:
    """Get list of all transaction categories."""
    db = request.app.state.db
    categories = db.get_all_categories()
    # Filter out None values
    categories = [c for c in categories if c is not None]
    return CategoriesListResponse(categories=categories)


@router.get("/categories/summary", response_model=CategorySummaryResponse)
async def category_summary(request: Request) -> CategorySummaryResponse:
    """Get spending summary grouped by category."""
    db = request.app.state.db
    summary = db.get_category_summary()
    return CategorySummaryResponse(
        categories=[CategorySummaryItem(**item) for item in summary]
    )
