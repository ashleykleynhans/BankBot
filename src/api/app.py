"""FastAPI application for statement-chat API."""

import asyncio
import os
import sqlite3
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..config import get_config
from ..database import Database
from ..llm_backend import create_backend
from .routers import analytics, budgets, chat, forecast, stats, transactions
from .session import session_manager

# Browser origins allowed to call the API and open the chat WebSocket.
# The API has no authentication, so anything else is rejected to prevent
# arbitrary websites from reading financial data cross-origin.
# 5173 is the vite dev server; 8080 is the nginx proxy in docker-compose.
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]


def _allowed_origins() -> list[str]:
    """Resolve allowed browser origins, honoring BANKBOT_ALLOWED_ORIGINS."""
    raw = os.environ.get("BANKBOT_ALLOWED_ORIGINS")
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return list(DEFAULT_ALLOWED_ORIGINS)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan - startup and shutdown tasks."""
    # Startup: Load config and create shared database connection
    config = get_config()
    app.state.config = config
    app.state.db = Database(config["paths"]["database"])
    app.state.backend = create_backend(config)

    # Start background task for session cleanup
    cleanup_task = asyncio.create_task(periodic_cleanup())

    yield

    # Shutdown: Cancel cleanup task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


async def periodic_cleanup() -> None:
    """Periodically clean up stale sessions."""
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        session_manager.cleanup_stale_sessions(max_age_minutes=60)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="BankBot API",
        description="API for querying bank statements with a local AI",
        version="0.3.0",
        lifespan=lifespan,
    )

    # CORS configuration for browser clients
    allowed_origins = _allowed_origins()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Shared with the WebSocket router for Origin validation
    app.state.allowed_origins = allowed_origins

    # Include routers
    app.include_router(chat.router, prefix="/ws", tags=["chat"])
    app.include_router(stats.router, prefix="/api/v1", tags=["stats"])
    app.include_router(transactions.router, prefix="/api/v1", tags=["transactions"])
    app.include_router(analytics.router, prefix="/api/v1", tags=["analytics"])
    app.include_router(budgets.router, prefix="/api/v1", tags=["budgets"])
    app.include_router(forecast.router, prefix="/api/v1", tags=["forecast"])

    @app.exception_handler(sqlite3.OperationalError)
    async def sqlite_error_handler(request: Request, exc: sqlite3.OperationalError) -> JSONResponse:
        """Handle missing tables gracefully with import instructions."""
        return JSONResponse(
            status_code=503,
            content={
                "error": "No bank statements imported yet.",
                "instructions": (
                    "Place your bank statement PDFs in the statements/ directory, "
                    "then run: bankbot import"
                ),
            },
        )

    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "active_sessions": session_manager.active_sessions,
        }

    return app


# Create app instance
app = create_app()
