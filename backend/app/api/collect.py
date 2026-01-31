"""Collection API endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.collector import get_collector

router = APIRouter()


from typing import Optional


class CollectionStatus(BaseModel):
    """Collection status response."""
    status: str
    last_run: Optional[str] = None
    next_run: Optional[str] = None


class CollectionResult(BaseModel):
    """Collection result response."""
    subreddits_processed: int
    posts_collected: int
    posts_new: int
    comments_collected: int
    errors: list


@router.get("/status")
async def get_collection_status():
    """Get the current collection status."""
    # TODO: Integrate with scheduler in Phase 2.5
    return CollectionStatus(
        status="idle",
        last_run=None,
        next_run=None,
    )


@router.post("", response_model=CollectionResult)
async def trigger_collection():
    """
    Trigger immediate collection from all enabled subreddits.

    This runs synchronously and may take a while depending on the number
    of monitored subreddits.
    """
    collector = get_collector()
    stats = await collector.collect_all()

    return CollectionResult(
        subreddits_processed=stats["subreddits_processed"],
        posts_collected=stats["posts_collected"],
        posts_new=stats["posts_new"],
        comments_collected=stats["comments_collected"],
        errors=stats["errors"],
    )


@router.post("/test")
async def test_reddit_connection():
    """Test the Reddit API connection."""
    collector = get_collector()
    return await collector.test_reddit_connection()
