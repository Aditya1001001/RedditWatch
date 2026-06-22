"""Collection API endpoints."""

from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_session
from app.models import Audience
from app.models.audience import audience_subreddits
from app.services.collector import get_collector
from app.services.tasks import get_task_tracker

router = APIRouter()


class CollectionMode(str, Enum):
    REGULAR = "regular"
    DEEP = "deep"


class CollectionStatus(BaseModel):
    """Collection status response."""
    status: str
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    task_id: Optional[str] = None
    progress: int = 0
    total: int = 0
    scheduler_running: bool = False
    scheduler_jobs: list = []


class CollectionResult(BaseModel):
    """Collection result response."""
    subreddits_processed: int
    posts_collected: int
    posts_new: int
    comments_collected: int
    errors: list


class RefreshResult(BaseModel):
    """Comment refresh result."""
    posts_refreshed: int
    comments_new: int
    comments_updated: int
    errors: list


@router.get("/status")
async def get_collection_status():
    """Get the current collection status, including scheduler state."""
    tracker = get_task_tracker()
    active = tracker.get_active_task("collection")
    if active:
        result = active.to_dict()
        result.update(_get_scheduler_info())
        return result

    # Check most recent completed task
    tasks = tracker.get_tasks_by_type("collection")
    if tasks:
        latest = max(tasks, key=lambda t: t.created_at)
        result = latest.to_dict()
        result.update(_get_scheduler_info())
        return result

    status = CollectionStatus(status="idle", **_get_scheduler_info())
    return status.model_dump()


def _get_scheduler_info() -> dict:
    """Get scheduler status info for inclusion in collection status."""
    try:
        from app.services.scheduler import get_scheduler
        scheduler = get_scheduler()
        return {
            "scheduler_running": scheduler.running,
            "scheduler_jobs": scheduler.get_job_summaries(),
        }
    except Exception:
        return {"scheduler_running": False, "scheduler_jobs": []}


@router.post("")
async def trigger_collection(
    mode: CollectionMode = Query(
        default=CollectionMode.REGULAR,
        description="Collection mode: 'regular' (single sort/page) or 'deep' (multi-sort with pagination)",
    ),
    since_days: Optional[int] = Query(
        default=None,
        description="Collect posts from the last N days (deep mode only). "
        "Paginates 'new' sort until posts are older than the cutoff.",
    ),
    session: AsyncSession = Depends(get_session),
):
    """
    Trigger collection from all enabled subreddits.

    Args:
        mode: 'regular' for single sort/page, 'deep' for multi-sort with pagination
        since_days: If set, collect all posts from the last N days (deep mode)

    Returns immediately with a task_id. Poll /status or /task/{task_id}
    for progress.
    """
    tracker = get_task_tracker()

    # Don't start a new collection if one is already running
    active = tracker.get_active_task("collection")
    if active:
        return active.to_dict()

    active_subreddits = await session.execute(
        select(audience_subreddits.c.subreddit_name)
        .join(Audience, Audience.id == audience_subreddits.c.audience_id)
        .where(Audience.active == True)
        .distinct()
        .limit(1)
    )
    if active_subreddits.first() is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "No followed audiences with monitored subreddits. "
                "Create or follow an audience before running Collect All."
            ),
        )

    task_info = tracker.create_task("collection")
    collector = get_collector()

    since_date = None
    if since_days is not None:
        since_date = datetime.now(timezone.utc) - timedelta(days=since_days)

    async def _run_collection():
        return await collector.collect_all(
            deep=(mode == CollectionMode.DEEP),
            since_date=since_date,
        )

    tracker.run_background(task_info, _run_collection())
    return task_info.to_dict()


@router.post("/seed")
async def trigger_seed_collection():
    """
    Trigger a one-time deep scrape of all monitored subreddits.

    Uses all configured sort modes with pagination to build the initial dataset.
    This can take a long time (~3.5 hours for 50 subreddits).

    Returns immediately with a task_id. Poll /status or /task/{task_id}
    for progress.
    """
    tracker = get_task_tracker()

    # Don't start if any collection is already running
    active = tracker.get_active_task("collection")
    if active:
        raise HTTPException(
            status_code=409,
            detail=f"A collection task is already running (task_id: {active.task_id})",
        )

    task_info = tracker.create_task("collection")
    collector = get_collector()

    async def _run_seed():
        return await collector.seed_collection()

    tracker.run_background(task_info, _run_seed())
    return task_info.to_dict()


@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """Get status of a specific task."""
    tracker = get_task_tracker()
    task = tracker.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task.to_dict()


@router.post("/test")
async def test_reddit_connection():
    """Test the Reddit API connection."""
    collector = get_collector()
    return await collector.test_reddit_connection()


@router.post("/refresh", response_model=RefreshResult)
async def refresh_hot_conversations(
    min_score: int = 10,
    min_comments: int = 5,
    limit: int = 10,
):
    """
    Refresh comments for high-engagement posts.

    Re-fetches comments (including nested replies) for posts with high
    scores/comment counts that may have valuable new replies.
    """
    collector = get_collector()
    stats = await collector.refresh_hot_conversations(
        min_score=min_score,
        min_comments=min_comments,
        limit=limit,
    )

    return RefreshResult(
        posts_refreshed=stats["posts_refreshed"],
        comments_new=stats["comments_new"],
        comments_updated=stats["comments_updated"],
        errors=stats["errors"],
    )


@router.post("/refresh/{post_id}")
async def refresh_post_comments(
    post_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Refresh comments for a specific post.

    Re-fetches all comments including nested replies.
    """
    from app.models import Post

    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")

    collector = get_collector()
    stats = await collector.refresh_comments(
        session,
        post_id,
        post.subreddit,
    )
    await session.commit()

    return stats
