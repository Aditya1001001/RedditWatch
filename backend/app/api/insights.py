"""Insights API endpoints.

Note: Primary insight endpoints are under /api/analyze/insights and /api/analyze/themes.
This module provides the /api/insights namespace for future direct insight management.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Insight

router = APIRouter()


@router.get("")
async def list_insights(
    type: Optional[str] = Query(default=None, alias="type"),
    theme_key: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """List insights with filters. See also /api/analyze/insights for richer filtering."""
    query = select(Insight).order_by(Insight.intensity_score.desc().nullslast())
    if type:
        query = query.where(Insight.type == type)
    if theme_key:
        query = query.where(Insight.theme_key == theme_key)
    query = query.limit(limit)

    result = await session.execute(query)
    insights = result.scalars().all()
    return [
        {
            "id": i.id,
            "type": i.type,
            "theme_key": i.theme_key,
            "title": i.title,
            "intensity_score": i.intensity_score,
        }
        for i in insights
    ]


@router.get("/stats")
async def get_insight_stats(session: AsyncSession = Depends(get_session)):
    """Get aggregate insight statistics."""
    total = (await session.execute(select(func.count(Insight.id)))).scalar() or 0
    themes = (await session.execute(select(func.count(func.distinct(Insight.theme_key))))).scalar() or 0

    type_query = select(Insight.type, func.count(Insight.id)).group_by(Insight.type)
    type_result = await session.execute(type_query)
    by_type = {row[0]: row[1] for row in type_result}

    return {
        "total_insights": total,
        "total_themes": themes,
        "by_type": by_type,
    }
