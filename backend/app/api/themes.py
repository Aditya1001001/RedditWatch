"""Themes API endpoints.

Note: Primary theme endpoints are under /api/analyze/themes.
This module provides the /api/themes namespace for direct theme queries.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Insight

router = APIRouter()


@router.get("")
async def list_themes(session: AsyncSession = Depends(get_session)):
    """List all themes with counts. See /api/analyze/themes for full aggregation."""
    query = (
        select(
            Insight.theme_key,
            func.count(Insight.id).label("count"),
            func.avg(Insight.intensity_score).label("avg_intensity"),
        )
        .group_by(Insight.theme_key)
        .order_by(func.count(Insight.id).desc())
    )
    result = await session.execute(query)
    return [
        {
            "theme_key": row[0],
            "count": row[1],
            "avg_intensity": round(float(row[2] or 0), 1),
        }
        for row in result.all()
    ]


@router.get("/{theme_key}")
async def get_theme(theme_key: str, session: AsyncSession = Depends(get_session)):
    """Get all insights for a specific theme."""
    query = (
        select(Insight)
        .where(Insight.theme_key == theme_key)
        .order_by(Insight.intensity_score.desc().nullslast())
    )
    result = await session.execute(query)
    insights = result.scalars().all()

    if not insights:
        return {"theme_key": theme_key, "count": 0, "insights": []}

    return {
        "theme_key": theme_key,
        "count": len(insights),
        "avg_intensity": round(
            sum(i.intensity_score or 0 for i in insights) / len(insights), 1
        ),
        "insights": [
            {
                "id": i.id,
                "type": i.type,
                "title": i.title,
                "description": i.description,
                "quote": i.quote,
                "intensity_score": i.intensity_score,
            }
            for i in insights
        ],
    }
