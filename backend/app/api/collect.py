"""Collection API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_session
from app.services.collector import get_collector
from app.services.tasks import get_task_tracker

router = APIRouter()


class CollectionStatus(BaseModel):
    """Collection status response."""
    status: str
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    task_id: Optional[str] = None
    progress: int = 0
    total: int = 0


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
    """Get the current collection status."""
    tracker = get_task_tracker()
    active = tracker.get_active_task("collection")
    if active:
        return active.to_dict()

    # Check most recent completed task
    tasks = tracker.get_tasks_by_type("collection")
    if tasks:
        latest = max(tasks, key=lambda t: t.created_at)
        return latest.to_dict()

    return CollectionStatus(status="idle").model_dump()


@router.post("")
async def trigger_collection():
    """
    Trigger collection from all enabled subreddits.

    Returns immediately with a task_id. Poll /status or /task/{task_id}
    for progress.
    """
    tracker = get_task_tracker()

    # Don't start a new collection if one is already running
    active = tracker.get_active_task("collection")
    if active:
        return active.to_dict()

    task_info = tracker.create_task("collection")
    collector = get_collector()

    async def _run_collection():
        return await collector.collect_all()

    tracker.run_background(task_info, _run_collection())
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
