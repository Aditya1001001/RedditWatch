"""RedditWatch FastAPI application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.config import get_config
from app.database import init_db
from app.services.collector import shutdown_collector
from app.services.scheduler import get_scheduler, shutdown_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting RedditWatch...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Load config
    config = get_config()
    logger.info(f"LLM provider: {config.llm.provider}")

    # Start scheduler if auto_schedule is enabled
    if config.collection.auto_schedule:
        scheduler = get_scheduler()
        scheduler.start()
        logger.info("Collection scheduler started (auto_schedule=true)")

    yield

    # Shutdown
    logger.info("Shutting down RedditWatch...")
    await shutdown_scheduler()
    await shutdown_collector()
    logger.info("Cleanup complete")


# Create FastAPI app
app = FastAPI(
    title="RedditWatch",
    description="Self-hosted Reddit market research tool",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware (configurable via config.yaml)
_config = get_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_config.server.cors.allowed_origins,
    allow_credentials=_config.server.cors.allow_credentials,
    allow_methods=_config.server.cors.allow_methods,
    allow_headers=_config.server.cors.allow_headers,
)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "redditwatch",
        "version": "0.1.0",
    }


# Include API routes
app.include_router(api_router)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors."""
    logger.exception(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Serve frontend static files if they exist
# IMPORTANT: This must be LAST because it catches all routes
frontend_path = Path(__file__).parent.parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    config = get_config()
    uvicorn.run(
        "app.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=True,
    )
