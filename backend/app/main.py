"""
Forecheck Fantasy API
FastAPI backend for fantasy hockey analytics
"""

import logging
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from app.database import engine, Base
import app.models  # noqa: F401
from app.routers import (
    auth_router,
    setup_router,
    players_router,
    scans_router,
    leagues_router,
    admin_router,
    yahoo_auth_router,
    schedule_router,
)
from app.config import get_settings
from app.services.nhl_sync import run_periodic_sync
from app.migrations import ensure_schema_updates

settings = get_settings()

# Configure logging
log_level = logging.DEBUG if settings.environment == "development" else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting Forecheck v2 API...")
    # Startup: Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")
    ensure_schema_updates(engine)

    sync_task = None
    if settings.nhl_sync_enabled and settings.run_sync_loop:
        logger.info(f"NHL sync enabled, interval: {settings.nhl_sync_interval_minutes} minutes")
        sync_task = asyncio.create_task(run_periodic_sync())
    else:
        logger.info("NHL sync loop is disabled for this process")

    yield

    # Shutdown
    logger.info("Shutting down Forecheck Fantasy API...")
    if sync_task:
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass
    logger.info("Shutdown complete")


app = FastAPI(
    title="Forecheck v2 API",
    description="Self-hosted fantasy hockey analytics API",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["http://localhost:6767"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(setup_router)
app.include_router(yahoo_auth_router)
app.include_router(players_router)
app.include_router(scans_router)
app.include_router(leagues_router)
app.include_router(admin_router)
app.include_router(schedule_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Forecheck v2 API",
        "version": "2.0.0",
        "docs": "/docs",
        "status": "healthy",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
