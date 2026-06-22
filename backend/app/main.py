"""RedditWatch FastAPI application."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env file before anything reads env vars
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import api_router
from app.config import Config, get_config
from app.database import init_db
from app.services.collector import get_collector, shutdown_collector
from app.services.scheduler import get_scheduler, shutdown_scheduler
from app.services.tasks import get_task_tracker

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

    # Startup catch-up: collect if data is stale
    if config.collection.collect_on_startup:
        asyncio.create_task(_startup_collect_if_stale(config))

    yield

    # Shutdown
    logger.info("Shutting down RedditWatch...")
    await shutdown_scheduler()
    await shutdown_collector()
    logger.info("Cleanup complete")


async def _startup_collect_if_stale(config: Config):
    """Check data staleness and trigger background collection if needed."""
    try:
        collector = get_collector()
        staleness = await collector.get_staleness(config.collection.stale_threshold_hours)

        if not staleness["total_subreddits"]:
            logger.info("No monitored subreddits — skipping startup collection")
            return

        if not staleness["stale"]:
            hours = staleness["oldest_collection_hours"]
            logger.info(f"Data is fresh (collected {hours}h ago), skipping startup collection")
            return

        # Build a human-readable reason
        parts = []
        if staleness["oldest_collection_hours"] is not None:
            parts.append(f"{staleness['oldest_collection_hours']}h since last collection")
        if staleness["subreddits_never_collected"]:
            parts.append(f"{staleness['subreddits_never_collected']} never collected")
        reason = ", ".join(parts)

        logger.info(f"Data is stale ({reason}), starting background collection...")

        # Register with TaskTracker so the frontend can show progress
        tracker = get_task_tracker()
        active = tracker.get_active_task("collection")
        if active:
            logger.info("Collection already running, skipping startup collection")
            return

        task_info = tracker.create_task("collection")

        async def _collect_then_analyze():
            result = await collector.collect_all(deep=False)
            if config.analysis.auto_analyze:
                from app.services.scheduler import get_scheduler
                scheduler = get_scheduler()
                await scheduler._maybe_run_analysis()
            return result

        tracker.run_background(task_info, _collect_then_analyze())

        logger.info(f"Startup collection started (task_id={task_info.task_id})")
    except Exception:
        logger.exception("Startup collection check failed (non-fatal)")


# Create FastAPI app
app = FastAPI(
    title="RedditWatch",
    description="Self-hosted community intelligence tool for ranked, source-backed Reddit market signals",
    version=__version__,
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
        "version": __version__,
    }


# Include API routes
app.include_router(api_router)

# Conditionally load cloud (SaaS-only) routes
if _config.is_cloud:
    try:
        from app.cloud import register_cloud_routes

        register_cloud_routes(app)
    except ImportError:
        logger.warning("EDITION=cloud but cloud package not found — running as OSS")


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
