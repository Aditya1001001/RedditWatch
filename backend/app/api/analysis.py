"""Analysis API endpoints."""

from collections import defaultdict
from itertools import combinations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Audience, Insight, Post
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


@router.get("/themes/timeline")
async def get_theme_timeline(
    days: int = Query(default=30, ge=1, le=90),
    top_n: int = Query(default=8, ge=1, le=20),
    audience_id: Optional[int] = Query(default=None),
    subreddits: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Theme popularity over time — insight counts per theme per day."""
    from datetime import datetime, timedelta, timezone

    sub_names = await resolve_audience_subreddits(session, audience_id, subreddits)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Get top N themes by total count
    top_q = (
        select(Insight.theme_key, func.count(Insight.id).label("cnt"))
        .where(Insight.created_at >= cutoff)
    )
    if sub_names is not None:
        top_q = top_q.join(Post).where(Post.subreddit.in_(sub_names))
    top_q = top_q.group_by(Insight.theme_key).order_by(func.count(Insight.id).desc()).limit(top_n)
    top_result = await session.execute(top_q)
    top_themes = [row.theme_key for row in top_result]

    if not top_themes:
        return {"themes": [], "dates": [], "series": {}}

    # Get daily counts for those themes
    daily_q = (
        select(
            Insight.theme_key,
            func.date(Insight.created_at).label("day"),
            func.count(Insight.id).label("cnt"),
        )
        .where(Insight.created_at >= cutoff)
        .where(Insight.theme_key.in_(top_themes))
    )
    if sub_names is not None:
        daily_q = daily_q.join(Post).where(Post.subreddit.in_(sub_names))
    daily_q = daily_q.group_by(Insight.theme_key, func.date(Insight.created_at))
    daily_result = await session.execute(daily_q)

    # Build series keyed by theme
    series = defaultdict(dict)
    all_dates = set()
    for row in daily_result:
        date_str = str(row.day)
        series[row.theme_key][date_str] = row.cnt
        all_dates.add(date_str)

    dates = sorted(all_dates)

    return {
        "themes": top_themes,
        "dates": dates,
        "series": {
            theme: [series[theme].get(d, 0) for d in dates]
            for theme in top_themes
        },
    }


@router.get("/themes/co-occurrence")
async def get_theme_co_occurrence(
    min_weight: int = Query(default=2, ge=1),
    top_n: int = Query(default=15, ge=5, le=30),
    audience_id: Optional[int] = Query(default=None),
    subreddits: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Theme co-occurrence network — themes that appear together in the same post."""
    sub_names = await resolve_audience_subreddits(session, audience_id, subreddits)

    # Get top themes by frequency
    top_q = (
        select(Insight.theme_key, func.count(Insight.id).label("cnt"))
    )
    if sub_names is not None:
        top_q = top_q.join(Post).where(Post.subreddit.in_(sub_names))
    top_q = top_q.group_by(Insight.theme_key).order_by(func.count(Insight.id).desc()).limit(top_n)
    top_result = await session.execute(top_q)
    theme_counts = {row.theme_key: row.cnt for row in top_result}
    top_themes = set(theme_counts.keys())

    if len(top_themes) < 2:
        return {"nodes": [], "edges": []}

    # Get all (post_id, theme_key) pairs for top themes
    pairs_q = select(Insight.post_id, Insight.theme_key).where(
        Insight.theme_key.in_(top_themes)
    )
    if sub_names is not None:
        pairs_q = pairs_q.join(Post).where(Post.subreddit.in_(sub_names))
    pairs_result = await session.execute(pairs_q)

    # Group themes by post
    post_themes = defaultdict(set)
    for row in pairs_result:
        post_themes[row.post_id].add(row.theme_key)

    # Count co-occurrences
    edge_counts = defaultdict(int)
    for themes in post_themes.values():
        for a, b in combinations(sorted(themes), 2):
            edge_counts[(a, b)] += 1

    nodes = [
        {"id": t, "label": t.replace("_", " ").title(), "count": theme_counts[t]}
        for t in top_themes
    ]
    edges = [
        {"source": a, "target": b, "weight": w}
        for (a, b), w in edge_counts.items()
        if w >= min_weight
    ]

    return {"nodes": nodes, "edges": edges}


@router.get("/themes/matrix")
async def get_theme_subreddit_matrix(
    top_themes: int = Query(default=10, ge=1, le=25),
    top_subreddits: int = Query(default=10, ge=1, le=25),
    audience_id: Optional[int] = Query(default=None),
    subreddits: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Subreddit x Theme matrix — insight counts per (subreddit, theme) pair."""
    sub_names = await resolve_audience_subreddits(session, audience_id, subreddits)

    # Get top themes
    theme_q = (
        select(Insight.theme_key, func.count(Insight.id).label("cnt"))
    )
    if sub_names is not None:
        theme_q = theme_q.join(Post).where(Post.subreddit.in_(sub_names))
    theme_q = theme_q.group_by(Insight.theme_key).order_by(func.count(Insight.id).desc()).limit(top_themes)
    theme_result = await session.execute(theme_q)
    theme_keys = [row.theme_key for row in theme_result]

    if not theme_keys:
        return {"themes": [], "subreddits": [], "matrix": {}}

    # Get top subreddits by insight count
    sub_q = (
        select(Post.subreddit, func.count(Insight.id).label("cnt"))
        .join(Insight)
    )
    if sub_names is not None:
        sub_q = sub_q.where(Post.subreddit.in_(sub_names))
    sub_q = sub_q.group_by(Post.subreddit).order_by(func.count(Insight.id).desc()).limit(top_subreddits)
    sub_result = await session.execute(sub_q)
    sub_keys = [row.subreddit for row in sub_result]

    # Get cross-tab counts
    matrix_q = (
        select(
            Post.subreddit,
            Insight.theme_key,
            func.count(Insight.id).label("cnt"),
        )
        .join(Insight)
        .where(Insight.theme_key.in_(theme_keys))
        .where(Post.subreddit.in_(sub_keys))
        .group_by(Post.subreddit, Insight.theme_key)
    )
    matrix_result = await session.execute(matrix_q)

    matrix = defaultdict(dict)
    for row in matrix_result:
        matrix[row.subreddit][row.theme_key] = row.cnt

    return {
        "themes": theme_keys,
        "subreddits": sub_keys,
        "matrix": {
            sub: {t: matrix[sub].get(t, 0) for t in theme_keys}
            for sub in sub_keys
        },
    }
