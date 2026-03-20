"""Audience management API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Audience, Insight, MonitoredSubreddit, Post

logger = logging.getLogger(__name__)

router = APIRouter()


class AudienceCreate(BaseModel):
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    subreddit_names: list[str] = []


class AudienceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    subreddit_names: Optional[list[str]] = None


class AudienceResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    subreddit_names: list[str] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


def _audience_to_response(audience: Audience) -> AudienceResponse:
    return AudienceResponse(
        id=audience.id,
        name=audience.name,
        description=audience.description,
        color=audience.color,
        subreddit_names=[s.name for s in audience.subreddits],
        created_at=audience.created_at.isoformat() if audience.created_at else None,
        updated_at=audience.updated_at.isoformat() if audience.updated_at else None,
    )


@router.get("", response_model=list[AudienceResponse])
async def list_audiences(
    session: AsyncSession = Depends(get_session),
):
    """List all audiences with their subreddits."""
    result = await session.execute(select(Audience).order_by(Audience.name))
    audiences = result.scalars().all()
    return [_audience_to_response(a) for a in audiences]


@router.post("", response_model=AudienceResponse, status_code=201)
async def create_audience(
    request: AudienceCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new audience."""
    # Check for duplicate name
    existing = await session.execute(
        select(Audience).where(Audience.name == request.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Audience '{request.name}' already exists")

    audience = Audience(
        name=request.name,
        description=request.description,
        color=request.color,
    )

    # Resolve subreddits
    if request.subreddit_names:
        for name in request.subreddit_names:
            sub = await session.get(MonitoredSubreddit, name.lower())
            if sub:
                audience.subreddits.append(sub)

    session.add(audience)
    await session.flush()

    return _audience_to_response(audience)


@router.get("/{audience_id}", response_model=AudienceResponse)
async def get_audience(
    audience_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get a single audience."""
    audience = await session.get(Audience, audience_id)
    if not audience:
        raise HTTPException(status_code=404, detail=f"Audience {audience_id} not found")
    return _audience_to_response(audience)


@router.put("/{audience_id}", response_model=AudienceResponse)
async def update_audience(
    audience_id: int,
    request: AudienceUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update an audience."""
    audience = await session.get(Audience, audience_id)
    if not audience:
        raise HTTPException(status_code=404, detail=f"Audience {audience_id} not found")

    if request.name is not None:
        audience.name = request.name
    if request.description is not None:
        audience.description = request.description
    if request.color is not None:
        audience.color = request.color

    if request.subreddit_names is not None:
        audience.subreddits.clear()
        for name in request.subreddit_names:
            sub = await session.get(MonitoredSubreddit, name.lower())
            if sub:
                audience.subreddits.append(sub)

    await session.flush()
    return _audience_to_response(audience)


@router.delete("/{audience_id}")
async def delete_audience(
    audience_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete an audience."""
    audience = await session.get(Audience, audience_id)
    if not audience:
        raise HTTPException(status_code=404, detail=f"Audience {audience_id} not found")

    await session.delete(audience)
    return {"message": f"Audience '{audience.name}' deleted"}


class AskRequest(BaseModel):
    question: str


@router.post("/{audience_id}/ask")
async def ask_about_audience(
    audience_id: int,
    request: AskRequest,
    session: AsyncSession = Depends(get_session),
):
    """Ask an AI question about this audience."""
    audience = await session.get(Audience, audience_id)
    if not audience:
        raise HTTPException(status_code=404, detail=f"Audience {audience_id} not found")

    sub_names = [s.name for s in audience.subreddits]
    if not sub_names:
        raise HTTPException(status_code=400, detail="Audience has no subreddits")

    # Gather context
    post_count_q = select(func.count(Post.id)).where(Post.subreddit.in_(sub_names))
    total_posts = (await session.execute(post_count_q)).scalar() or 0

    insight_count_q = select(func.count(Insight.id)).join(Post).where(Post.subreddit.in_(sub_names))
    total_insights = (await session.execute(insight_count_q)).scalar() or 0

    # Insights by type
    type_q = (
        select(Insight.type, func.count(Insight.id))
        .join(Post).where(Post.subreddit.in_(sub_names))
        .group_by(Insight.type)
    )
    type_result = await session.execute(type_q)
    insights_by_type = {row[0]: row[1] for row in type_result}

    # Top themes
    theme_q = (
        select(Insight.theme_key, func.count(Insight.id).label("cnt"))
        .join(Post).where(Post.subreddit.in_(sub_names))
        .group_by(Insight.theme_key)
        .order_by(func.count(Insight.id).desc())
        .limit(10)
    )
    theme_result = await session.execute(theme_q)
    top_themes = [(row.theme_key, row.cnt) for row in theme_result]

    # Sample high-intensity insights
    sample_q = (
        select(Insight.title, Insight.type)
        .join(Post).where(Post.subreddit.in_(sub_names))
        .where(Insight.intensity_score.isnot(None))
        .order_by(Insight.intensity_score.desc())
        .limit(5)
    )
    sample_result = await session.execute(sample_q)
    samples = [(row.title, row.type) for row in sample_result]

    # Build type summary
    type_summary = ", ".join(
        f"{t.replace('_', ' ').title()} ({c})"
        for t, c in sorted(insights_by_type.items(), key=lambda x: -x[1])
    )
    theme_summary = ", ".join(f"{t} ({c})" for t, c in top_themes[:8])
    sample_text = "\n".join(f'- "{title}" ({typ.replace("_", " ")})' for title, typ in samples)

    prompt = f"""You are a market research assistant. The user has an audience called "{audience.name}" tracking subreddits: {', '.join('r/' + s for s in sub_names)}.

Data summary:
- {total_posts} posts, {total_insights} insights
- Themes: {type_summary}
- Top topics: {theme_summary}
- Sample high-intensity insights:
{sample_text}

Answer concisely: {request.question}"""

    try:
        from app.llm.factory import get_llm_provider
        provider = await get_llm_provider()
        response = await provider.generate(
            prompt=prompt,
            system="You are a helpful market research assistant. Give concise, actionable answers based on the data provided.",
            temperature=0.4,
            max_tokens=1024,
        )
        return {"answer": response.content, "model": response.model}
    except Exception as e:
        logger.error(f"LLM error in ask endpoint: {e}")
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {str(e)}")


@router.get("/{audience_id}/theme-summary")
async def get_theme_summary(
    audience_id: int,
    type: str = Query(..., description="Insight type (e.g. pain_point)"),
    session: AsyncSession = Depends(get_session),
):
    """Get an AI-generated summary of a specific insight type for this audience."""
    audience = await session.get(Audience, audience_id)
    if not audience:
        raise HTTPException(status_code=404, detail=f"Audience {audience_id} not found")

    sub_names = [s.name for s in audience.subreddits]
    if not sub_names:
        raise HTTPException(status_code=400, detail="Audience has no subreddits")

    # Get top insights of this type
    insights_q = (
        select(Insight)
        .join(Post).where(Post.subreddit.in_(sub_names))
        .where(Insight.type == type)
        .order_by(Insight.intensity_score.desc().nullslast())
        .limit(10)
    )
    result = await session.execute(insights_q)
    insights = result.scalars().all()

    if not insights:
        return {
            "summary": f"No {type.replace('_', ' ')} insights found for this audience yet.",
            "insight_count": 0,
            "type": type,
        }

    # Count total
    count_q = (
        select(func.count(Insight.id))
        .join(Post).where(Post.subreddit.in_(sub_names))
        .where(Insight.type == type)
    )
    insight_count = (await session.execute(count_q)).scalar() or 0

    type_label = type.replace("_", " ").title()
    insight_text = "\n".join(
        f"- {i.title}: {i.description}" + (f' ("{i.quote}")' if i.quote else "")
        for i in insights
    )

    prompt = f"""Here are {type_label} insights from the "{audience.name}" audience ({insight_count} total, showing top 10):

{insight_text}

In 2-3 sentences, describe the main patterns. Start directly with a finding — no preamble or meta-commentary."""

    try:
        from app.llm.factory import get_llm_provider
        provider = await get_llm_provider()
        response = await provider.generate(
            prompt=prompt,
            system="You are a market research analyst. Respond with the summary directly — no preamble.",
            temperature=0.3,
            max_tokens=512,
        )
        return {
            "summary": response.content,
            "insight_count": insight_count,
            "type": type,
        }
    except Exception as e:
        logger.error(f"LLM error in theme-summary: {e}")
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {str(e)}")
