"""Analysis API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Audience
from app.services.analyzer import get_analyzer
from app.services.tasks import get_task_tracker


async def resolve_audience_subreddits(
    session: AsyncSession,
    audience_id: Optional[int] = None,
    subreddits: Optional[str] = None,
) -> Optional[list[str]]:
    """Resolve audience_id or comma-separated subreddit string to a list of names.

    Returns None if no filtering is requested.
    """
    if audience_id:
        audience = await session.get(Audience, audience_id)
        if audience:
            return [s.name for s in audience.subreddits]
        return []
    if subreddits:
        return [s.strip().lower() for s in subreddits.split(",") if s.strip()]
    return None

router = APIRouter()


class AnalysisResult(BaseModel):
    """Analysis run result."""
    posts_analyzed: int
    insights_extracted: int
    total_duration_ms: int
    avg_duration_ms: int
    errors: list


class ThemeSummary(BaseModel):
    """Theme aggregation summary."""
    theme_key: str
    count: int
    avg_intensity: float
    combined_score: float
    types: list[str]
    top_quotes: list[dict]


class InsightResponse(BaseModel):
    """Single insight response."""
    id: int
    post_id: str
    type: str
    theme_key: str
    title: str
    description: str
    quote: Optional[str] = None
    quote_author: Optional[str] = None
    permalink: Optional[str] = None
    intensity_score: Optional[int] = None
    product_name: Optional[str] = None
    sentiment: Optional[str] = None
    created_at: Optional[str] = None
    subreddit: Optional[str] = None

    model_config = {"from_attributes": True}


@router.post("")
async def trigger_analysis(
    limit: int = Query(default=10, ge=1, le=50),
    min_score: int = Query(default=3, ge=0),
):
    """
    Trigger LLM analysis on unanalyzed posts.

    Returns immediately with a task_id. Poll /status for progress.
    """
    tracker = get_task_tracker()

    # Don't start if one is already running
    active = tracker.get_active_task("analysis")
    if active:
        return active.to_dict()

    task_info = tracker.create_task("analysis")
    analyzer = get_analyzer()

    async def _run_analysis():
        return await analyzer.analyze_unanalyzed_posts(
            limit=limit,
            min_score=min_score,
        )

    tracker.run_background(task_info, _run_analysis())
    return task_info.to_dict()


@router.get("/task/{task_id}")
async def get_analysis_task(task_id: str):
    """Get status of a specific analysis task."""
    tracker = get_task_tracker()
    task = tracker.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task.to_dict()


@router.get("/themes", response_model=list[ThemeSummary])
async def get_themes(
    audience_id: Optional[int] = Query(default=None),
    subreddits: Optional[str] = Query(default=None, description="Comma-separated subreddit names"),
    session: AsyncSession = Depends(get_session),
):
    """
    Get aggregated theme summary.

    Returns themes sorted by combined score (frequency x intensity).
    Optionally filter by audience or specific subreddits.
    """
    sub_names = await resolve_audience_subreddits(session, audience_id, subreddits)

    analyzer = get_analyzer()
    themes = await analyzer.get_theme_summary(session, subreddit_names=sub_names)

    return [
        ThemeSummary(
            theme_key=t["theme_key"],
            count=t["count"],
            avg_intensity=t["avg_intensity"],
            combined_score=t["combined_score"],
            types=t["types"],
            top_quotes=t["top_quotes"],
        )
        for t in themes
    ]


@router.get("/insights", response_model=list[InsightResponse])
async def get_insights(
    theme_key: Optional[str] = None,
    type: Optional[str] = Query(default=None, alias="type"),
    sort: Optional[str] = Query(default=None, description="Sort by: intensity, date"),
    limit: int = Query(default=50, ge=1, le=200),
    audience_id: Optional[int] = Query(default=None),
    subreddits: Optional[str] = Query(default=None, description="Comma-separated subreddit names"),
    session: AsyncSession = Depends(get_session),
):
    """
    Get extracted insights with optional filters.
    """
    sub_names = await resolve_audience_subreddits(session, audience_id, subreddits)

    analyzer = get_analyzer()
    insights = await analyzer.get_insights_by_theme(
        session,
        theme_key=theme_key,
        insight_type=type,
        limit=limit,
        sort_by=sort,
        subreddit_names=sub_names,
    )

    return [
        InsightResponse(
            id=i.id,
            post_id=i.post_id,
            type=i.type,
            theme_key=i.theme_key,
            title=i.title,
            description=i.description,
            quote=i.quote,
            quote_author=i.quote_author,
            permalink=i.permalink,
            intensity_score=i.intensity_score,
            product_name=i.product_name,
            sentiment=i.sentiment,
            created_at=i.created_at.isoformat() if i.created_at else None,
            subreddit=i.post.subreddit if i.post else None,
        )
        for i in insights
    ]


@router.get("/status")
async def get_analysis_status(
    audience_id: Optional[int] = Query(default=None),
    subreddits: Optional[str] = Query(default=None, description="Comma-separated subreddit names"),
    session: AsyncSession = Depends(get_session),
):
    """Get analysis statistics including timing metrics and active task status."""
    from sqlalchemy import func
    from app.models import Post, Insight

    sub_names = await resolve_audience_subreddits(session, audience_id, subreddits)

    # Base queries, scoped to audience if specified
    post_base = select(func.count(Post.id))
    insight_base = select(func.count(Insight.id))
    if sub_names is not None:
        post_base = post_base.where(Post.subreddit.in_(sub_names))
        insight_base = insight_base.join(Post).where(Post.subreddit.in_(sub_names))

    # Count posts
    total = (await session.execute(post_base)).scalar() or 0
    analyzed_q = post_base.where(Post.analyzed == True)
    analyzed = (await session.execute(analyzed_q)).scalar() or 0

    # Count insights
    insights = (await session.execute(insight_base)).scalar() or 0

    # Get timing stats
    avg_q = select(func.avg(Post.analysis_duration_ms)).where(Post.analyzed == True)
    if sub_names is not None:
        avg_q = avg_q.where(Post.subreddit.in_(sub_names))
    avg_ms = (await session.execute(avg_q)).scalar()

    last_q = select(func.max(Post.analyzed_at)).where(Post.analyzed == True)
    if sub_names is not None:
        last_q = last_q.where(Post.subreddit.in_(sub_names))
    last_at = (await session.execute(last_q)).scalar()

    # Count themes
    theme_q = select(func.count(func.distinct(Insight.theme_key)))
    if sub_names is not None:
        theme_q = theme_q.join(Post).where(Post.subreddit.in_(sub_names))
    themes = (await session.execute(theme_q)).scalar() or 0

    # Count by insight type
    type_q = select(Insight.type, func.count(Insight.id)).group_by(Insight.type)
    if sub_names is not None:
        type_q = type_q.join(Post).where(Post.subreddit.in_(sub_names))
    type_result = await session.execute(type_q)
    insights_by_type = {row[0]: row[1] for row in type_result}

    # Check for active analysis task
    tracker = get_task_tracker()
    active_task = tracker.get_active_task("analysis")

    return {
        "total_posts": total,
        "analyzed_posts": analyzed,
        "unanalyzed_posts": total - analyzed,
        "total_insights": insights,
        "total_themes": themes,
        "insights_by_type": insights_by_type,
        "avg_analysis_duration_ms": int(avg_ms) if avg_ms else None,
        "last_analyzed_at": last_at.isoformat() if last_at else None,
        "status": active_task.status.value if active_task else "idle",
        "active_task": active_task.to_dict() if active_task else None,
    }
