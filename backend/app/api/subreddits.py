"""Subreddit management API endpoints."""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import MonitoredSubreddit, SubscriberSnapshot
from app.models.post import Post
from app.services.collector import get_collector

SUBREDDIT_PATTERN = re.compile(r"^[a-zA-Z0-9_]{2,21}$")

router = APIRouter()


class SubredditCreate(BaseModel):
    """Request to add a subreddit."""
    name: str
    category: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip().lower().replace("r/", "")
        if not SUBREDDIT_PATTERN.match(v):
            raise ValueError(
                "Invalid subreddit name. Must be 2-21 characters, "
                "alphanumeric and underscores only."
            )
        return v


class SubredditResponse(BaseModel):
    """Subreddit response model."""
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    subscribers: Optional[int] = None
    icon_url: Optional[str] = None
    category: Optional[str] = None
    enabled: bool = True
    post_count: int = 0
    insight_count: int = 0
    last_collected: Optional[str] = None

    model_config = {"from_attributes": True}


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
    category_display_name: Optional[str] = None
    best_for: Optional[str] = None


class SubredditSearchResult(BaseModel):
    """Search result for subreddit discovery."""
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    subscribers: Optional[int] = None
    icon_url: Optional[str] = None
    source: str  # "catalog" or "reddit"
    category: Optional[str] = None
    is_monitored: bool = False


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
            icon_url=getattr(s, 'icon_url', None),
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
            category_display_name=s.get("category_display_name"),
            best_for=s.get("best_for"),
        )
        for s in catalog
    ]


@router.get("/catalog/categories")
async def get_catalog_categories():
    """Get list of categories with display names and counts."""
    collector = get_collector()
    categories = collector.get_catalog_categories()
    total = sum(c["count"] for c in categories)
    return {
        "categories": categories,
        "total_subreddits": total,
    }


@router.get("/search", response_model=list[SubredditSearchResult])
async def search_subreddits(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    """Search subreddits across local catalog and Reddit's live search."""
    collector = get_collector()

    # Get monitored names for marking results
    monitored = await collector.get_monitored_subreddits(session)
    monitored_names = {s.name.lower() for s in monitored}

    results = await collector.search_subreddits(q, limit, monitored_names)
    return [SubredditSearchResult(**r) for r in results]


@router.get("/growth/summary")
async def get_growth_summary(
    days: int = Query(default=7, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
):
    """Get subscriber growth summary for all monitored subreddits."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Get all monitored subreddits with their current subscriber counts
    subs_result = await session.execute(
        select(MonitoredSubreddit).order_by(MonitoredSubreddit.name)
    )
    subreddits_list = subs_result.scalars().all()

    # Batch query: get oldest snapshot per subreddit in one query
    from sqlalchemy import and_

    oldest_subq = (
        select(
            SubscriberSnapshot.subreddit_name,
            func.min(SubscriberSnapshot.recorded_at).label("min_recorded_at"),
        )
        .where(SubscriberSnapshot.recorded_at >= cutoff)
        .group_by(SubscriberSnapshot.subreddit_name)
        .subquery()
    )
    oldest_result = await session.execute(
        select(SubscriberSnapshot.subreddit_name, SubscriberSnapshot.subscriber_count)
        .join(
            oldest_subq,
            and_(
                SubscriberSnapshot.subreddit_name == oldest_subq.c.subreddit_name,
                SubscriberSnapshot.recorded_at == oldest_subq.c.min_recorded_at,
            ),
        )
    )
    oldest_map = {row.subreddit_name: row.subscriber_count for row in oldest_result}

    growth_data = []
    for sub in subreddits_list:
        current_count = sub.subscribers or 0
        oldest_count = oldest_map.get(sub.name)

        change = None
        change_pct = None
        if oldest_count is not None and oldest_count > 0:
            change = current_count - oldest_count
            change_pct = round((change / oldest_count) * 100, 2)

        growth_data.append({
            "subreddit": sub.name,
            "current_subscribers": current_count,
            "change": change,
            "change_pct": change_pct,
            "days": days,
        })

    return growth_data


@router.get("/growth/multi")
async def get_growth_multi(
    session: AsyncSession = Depends(get_session),
):
    """Get all monitored subs with multi-timeframe growth and activity metrics."""
    from sqlalchemy import and_

    now = datetime.now(timezone.utc)

    # Get all monitored subreddits
    subs_result = await session.execute(
        select(MonitoredSubreddit).order_by(MonitoredSubreddit.name)
    )
    subreddits_list = subs_result.scalars().all()

    if not subreddits_list:
        return []

    # Batch query oldest snapshot per subreddit for each timeframe
    timeframes = {"1d": 1, "7d": 7, "30d": 30, "365d": 365}
    oldest_maps = {}

    for label, days in timeframes.items():
        cutoff = now - timedelta(days=days)
        oldest_subq = (
            select(
                SubscriberSnapshot.subreddit_name,
                func.min(SubscriberSnapshot.recorded_at).label("min_recorded_at"),
            )
            .where(SubscriberSnapshot.recorded_at >= cutoff)
            .group_by(SubscriberSnapshot.subreddit_name)
            .subquery()
        )
        oldest_result = await session.execute(
            select(SubscriberSnapshot.subreddit_name, SubscriberSnapshot.subscriber_count)
            .join(
                oldest_subq,
                and_(
                    SubscriberSnapshot.subreddit_name == oldest_subq.c.subreddit_name,
                    SubscriberSnapshot.recorded_at == oldest_subq.c.min_recorded_at,
                ),
            )
        )
        oldest_maps[label] = {row.subreddit_name: row.subscriber_count for row in oldest_result}

    # Posts per day over last 30 days
    cutoff_30d = now - timedelta(days=30)
    posts_count_result = await session.execute(
        select(Post.subreddit, func.count(Post.id))
        .where(Post.created_utc >= cutoff_30d)
        .group_by(Post.subreddit)
    )
    posts_count_map = {row[0]: row[1] for row in posts_count_result}

    result = []
    for sub in subreddits_list:
        current = sub.subscribers or 0

        def calc_pct(label):
            oldest = oldest_maps[label].get(sub.name)
            if oldest is not None and oldest > 0:
                return round(((current - oldest) / oldest) * 100, 2)
            return None

        post_count_30d = posts_count_map.get(sub.name, 0)
        posts_per_day = round(post_count_30d / 30, 1)

        result.append({
            "subreddit": sub.name,
            "display_name": sub.display_name or f"r/{sub.name}",
            "subscribers": current,
            "icon_url": getattr(sub, 'icon_url', None),
            "post_count": sub.post_count,
            "posts_per_day": posts_per_day,
            "growth_1d_pct": calc_pct("1d"),
            "growth_7d_pct": calc_pct("7d"),
            "growth_30d_pct": calc_pct("30d"),
            "growth_365d_pct": calc_pct("365d"),
            "last_collected": sub.last_collected.isoformat() if sub.last_collected else None,
        })

    return result


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
            icon_url=getattr(subreddit, 'icon_url', None),
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
        icon_url=getattr(subreddit, 'icon_url', None),
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


@router.get("/{name}/growth")
async def get_subreddit_growth(
    name: str,
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    """Get subscriber growth time series for a subreddit."""
    sub = await session.get(MonitoredSubreddit, name.lower())
    if not sub:
        raise HTTPException(status_code=404, detail=f"Subreddit r/{name} not found")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await session.execute(
        select(SubscriberSnapshot)
        .where(SubscriberSnapshot.subreddit_name == name.lower())
        .where(SubscriberSnapshot.recorded_at >= cutoff)
        .order_by(SubscriberSnapshot.recorded_at.asc())
    )
    snapshots = result.scalars().all()

    time_series = [
        {
            "date": s.recorded_at.isoformat(),
            "subscribers": s.subscriber_count,
        }
        for s in snapshots
    ]

    # Calculate growth metrics
    current = sub.subscribers or 0
    change = None
    change_pct = None
    change_7d_pct = None

    if snapshots:
        first_count = snapshots[0].subscriber_count
        if first_count > 0:
            change = current - first_count
            change_pct = round((change / first_count) * 100, 2)

        # 7-day change
        cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
        recent = [s for s in snapshots if s.recorded_at >= cutoff_7d]
        if recent and recent[0].subscriber_count > 0:
            change_7d = current - recent[0].subscriber_count
            change_7d_pct = round((change_7d / recent[0].subscriber_count) * 100, 2)

    return {
        "subreddit": name,
        "current_subscribers": current,
        "change": change,
        "change_pct": change_pct,
        "change_7d_pct": change_7d_pct,
        "days": days,
        "data_points": len(time_series),
        "time_series": time_series,
    }


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
