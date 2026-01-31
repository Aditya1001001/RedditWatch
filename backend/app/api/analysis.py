"""Analysis API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.analyzer import get_analyzer

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

    class Config:
        from_attributes = True


@router.post("", response_model=AnalysisResult)
async def trigger_analysis(
    limit: int = Query(default=10, ge=1, le=50),
    min_score: int = Query(default=3, ge=0),
):
    """
    Trigger LLM analysis on unanalyzed posts.

    Args:
        limit: Maximum number of posts to analyze (1-50)
        min_score: Minimum post score to consider for analysis

    Returns:
        Statistics about the analysis run
    """
    analyzer = get_analyzer()
    stats = await analyzer.analyze_unanalyzed_posts(
        limit=limit,
        min_score=min_score,
    )

    return AnalysisResult(
        posts_analyzed=stats["posts_analyzed"],
        insights_extracted=stats["insights_extracted"],
        total_duration_ms=stats["total_duration_ms"],
        avg_duration_ms=stats["avg_duration_ms"],
        errors=stats["errors"],
    )


@router.get("/themes", response_model=list[ThemeSummary])
async def get_themes(
    session: AsyncSession = Depends(get_session),
):
    """
    Get aggregated theme summary.

    Returns themes sorted by combined score (frequency × intensity).
    """
    analyzer = get_analyzer()
    themes = await analyzer.get_theme_summary(session)

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
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """
    Get extracted insights with optional filters.

    Args:
        theme_key: Filter by theme key
        type: Filter by insight type (pain_point, solution_request, product_mention, opportunity)
        limit: Maximum number of insights to return
    """
    analyzer = get_analyzer()
    insights = await analyzer.get_insights_by_theme(
        session,
        theme_key=theme_key,
        insight_type=type,
        limit=limit,
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
        )
        for i in insights
    ]


@router.get("/status")
async def get_analysis_status(
    session: AsyncSession = Depends(get_session),
):
    """Get analysis statistics including timing metrics."""
    from sqlalchemy import select, func
    from app.models import Post, Insight

    # Count posts
    total_posts = await session.execute(select(func.count(Post.id)))
    total = total_posts.scalar() or 0

    analyzed_posts = await session.execute(
        select(func.count(Post.id)).where(Post.analyzed == True)
    )
    analyzed = analyzed_posts.scalar() or 0

    # Count insights
    total_insights = await session.execute(select(func.count(Insight.id)))
    insights = total_insights.scalar() or 0

    # Get timing stats
    avg_duration = await session.execute(
        select(func.avg(Post.analysis_duration_ms)).where(Post.analyzed == True)
    )
    avg_ms = avg_duration.scalar()

    last_analyzed = await session.execute(
        select(func.max(Post.analyzed_at)).where(Post.analyzed == True)
    )
    last_at = last_analyzed.scalar()

    # Count themes
    theme_count = await session.execute(
        select(func.count(func.distinct(Insight.theme_key)))
    )
    themes = theme_count.scalar() or 0

    return {
        "total_posts": total,
        "analyzed_posts": analyzed,
        "unanalyzed_posts": total - analyzed,
        "total_insights": insights,
        "total_themes": themes,
        "avg_analysis_duration_ms": int(avg_ms) if avg_ms else None,
        "last_analyzed_at": last_at.isoformat() if last_at else None,
        "status": "idle",
    }
