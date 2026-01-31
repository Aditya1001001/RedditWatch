"""Subreddit management API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.collector import get_collector

router = APIRouter()


class SubredditCreate(BaseModel):
    """Request to add a subreddit."""
    name: str
    category: Optional[str] = None


class SubredditResponse(BaseModel):
    """Subreddit response model."""
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    subscribers: Optional[int] = None
    category: Optional[str] = None
    enabled: bool = True
    post_count: int = 0
    insight_count: int = 0
    last_collected: Optional[str] = None

    class Config:
        from_attributes = True


class SubredditToggle(BaseModel):
    """Request to toggle subreddit."""
    enabled: bool


class CatalogEntry(BaseModel):
    """Catalog entry model."""
    name: str
    display_name: str
    description: Optional[str] = None
    subscribers: Optional[int] = None
    category: str
    best_for: Optional[str] = None


@router.get("", response_model=list[SubredditResponse])
async def list_subreddits(
    enabled_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    """List all monitored subreddits."""
    collector = get_collector()
    subreddits = await collector.get_monitored_subreddits(session, enabled_only=enabled_only)

    return [
        SubredditResponse(
            name=s.name,
            display_name=s.display_name,
            description=s.description,
            subscribers=s.subscribers,
            category=s.category,
            enabled=s.enabled,
            post_count=s.post_count,
            insight_count=s.insight_count,
            last_collected=s.last_collected.isoformat() if s.last_collected else None,
        )
        for s in subreddits
    ]


@router.get("/catalog", response_model=list[CatalogEntry])
async def get_subreddit_catalog(category: Optional[str] = None):
    """
    Browse the curated subreddit catalog.

    Optional filter by category.
    """
    collector = get_collector()
    catalog = collector.get_catalog_flat()

    if category:
        catalog = [s for s in catalog if s["category"] == category]

    return [
        CatalogEntry(
            name=s["name"],
            display_name=s.get("display_name", f"r/{s['name']}"),
            description=s.get("description"),
            subscribers=s.get("subscribers"),
            category=s["category"],
            best_for=s.get("best_for"),
        )
        for s in catalog
    ]


@router.get("/catalog/categories")
async def get_catalog_categories():
    """Get list of categories in the catalog."""
    collector = get_collector()
    catalog = collector.load_subreddit_catalog()
    return {
        "categories": list(catalog.keys()),
        "total_subreddits": sum(len(subs) for subs in catalog.values()),
    }


@router.post("", response_model=SubredditResponse)
async def add_subreddit(
    request: SubredditCreate,
    session: AsyncSession = Depends(get_session),
):
    """
    Add a subreddit to monitor.

    The subreddit must exist on Reddit.
    """
    collector = get_collector()

    try:
        subreddit = await collector.add_subreddit(
            session,
            name=request.name,
            category=request.category,
        )
        await session.commit()

        return SubredditResponse(
            name=subreddit.name,
            display_name=subreddit.display_name,
            description=subreddit.description,
            subscribers=subreddit.subscribers,
            category=subreddit.category,
            enabled=subreddit.enabled,
            post_count=subreddit.post_count,
            insight_count=subreddit.insight_count,
            last_collected=subreddit.last_collected.isoformat() if subreddit.last_collected else None,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{name}", response_model=SubredditResponse)
async def toggle_subreddit(
    name: str,
    request: SubredditToggle,
    session: AsyncSession = Depends(get_session),
):
    """Enable or disable a monitored subreddit."""
    collector = get_collector()

    subreddit = await collector.toggle_subreddit(session, name, request.enabled)
    if not subreddit:
        raise HTTPException(status_code=404, detail=f"Subreddit r/{name} not found")

    await session.commit()

    return SubredditResponse(
        name=subreddit.name,
        display_name=subreddit.display_name,
        description=subreddit.description,
        subscribers=subreddit.subscribers,
        category=subreddit.category,
        enabled=subreddit.enabled,
        post_count=subreddit.post_count,
        insight_count=subreddit.insight_count,
        last_collected=subreddit.last_collected.isoformat() if subreddit.last_collected else None,
    )


@router.delete("/{name}")
async def remove_subreddit(
    name: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Remove a subreddit from monitoring.

    This does NOT delete collected posts/insights from that subreddit.
    """
    collector = get_collector()

    removed = await collector.remove_subreddit(session, name)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Subreddit r/{name} not found")

    await session.commit()

    return {"message": f"Subreddit r/{name} removed from monitoring"}


@router.post("/{name}/collect")
async def collect_subreddit(
    name: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Trigger immediate collection for a specific subreddit.
    """
    collector = get_collector()

    # Verify subreddit is being monitored
    subreddits = await collector.get_monitored_subreddits(session)
    if not any(s.name.lower() == name.lower() for s in subreddits):
        raise HTTPException(
            status_code=404,
            detail=f"Subreddit r/{name} not being monitored. Add it first."
        )

    stats = await collector.collect_subreddit(session, name)
    await session.commit()

    return stats
