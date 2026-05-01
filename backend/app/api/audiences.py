"""Audience management API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
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
    active: bool = False
    subreddit_names: list[str] = []


class AudienceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    active: Optional[bool] = None
    subreddit_names: Optional[list[str]] = None


class AudienceResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    active: bool = False
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
        active=audience.active,
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
        active=request.active,
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
    if request.active is not None:
        audience.active = request.active

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


@router.put("/{audience_id}/follow", response_model=AudienceResponse)
async def follow_audience(
    audience_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Follow an audience (set active = True)."""
    audience = await session.get(Audience, audience_id)
    if not audience:
        raise HTTPException(status_code=404, detail=f"Audience {audience_id} not found")
    audience.active = True
    await session.flush()
    return _audience_to_response(audience)


@router.put("/{audience_id}/unfollow", response_model=AudienceResponse)
async def unfollow_audience(
    audience_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Unfollow an audience (set active = False)."""
    audience = await session.get(Audience, audience_id)
    if not audience:
        raise HTTPException(status_code=404, detail=f"Audience {audience_id} not found")
    audience.active = False
    await session.flush()
    return _audience_to_response(audience)


class HistoryItem(BaseModel):
    question: str
    answer: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    history: list[HistoryItem] = Field(default_factory=list, max_length=3)


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

    # RAG retrieval — semantic search filtered to audience subreddits
    retrieved_text = "(no relevant insights found)"
    try:
        from app.services.search import get_search_service
        search_svc = get_search_service()
        raw_results = await search_svc.search_async(
            query=request.question,
            limit=12,
            subreddits=sub_names,
        )

        if raw_results:
            insight_ids = [r["metadata"]["insight_id"] for r in raw_results if r["metadata"].get("insight_id")]
            insight_map = {}
            if insight_ids:
                insight_rows = await session.execute(
                    select(Insight).where(Insight.id.in_(insight_ids))
                )
                insight_map = {i.id: i for i in insight_rows.scalars().all()}

            lines = []
            for r in raw_results:
                iid = r["metadata"].get("insight_id")
                insight = insight_map.get(iid)
                if not insight:
                    continue
                sub = r["metadata"].get("subreddit", "unknown")
                line = f'({insight.type}, r/{sub}) "{insight.title}"'
                if insight.description:
                    line += f"\n    {insight.description}"
                if insight.quote:
                    author = f" — u/{insight.quote_author}" if insight.quote_author else ""
                    line += f'\n    Quote: "{insight.quote}"{author}'
                lines.append(line)

            if lines:
                retrieved_text = "\n\n".join(lines)
    except Exception:
        logger.warning("RAG retrieval failed for ask endpoint, falling back to stats-only", exc_info=True)

    # Build conversation history block
    history_block = ""
    if request.history:
        history_lines = []
        for h in request.history:
            history_lines.append(f"User: {h.question}")
            history_lines.append(f"Assistant: {h.answer}")
        history_block = "CONVERSATION HISTORY:\n" + "\n".join(history_lines) + "\n\n"

    subreddit_list = ", ".join("r/" + s for s in sub_names)
    prompt = f"""AUDIENCE: "{audience.name}" \u2014 tracking {subreddit_list}

DATA OVERVIEW:
- {total_posts} posts analyzed, {total_insights} insights extracted
- By type: {type_summary}
- Top themes: {theme_summary}

RETRIEVED INSIGHTS (most relevant to the question):
{retrieved_text}

{history_block}QUESTION: {request.question}"""

    system_prompt = """You are an expert market research analyst. You answer questions ONLY using the provided insights data. You must NEVER make up quotes, usernames, or claims.

RULES:
- ONLY use information from the RETRIEVED INSIGHTS section below. If no relevant insights are provided, say "I don't have enough data on this topic to give a grounded answer" and suggest what the user could ask instead based on the DATA OVERVIEW.
- When an insight has a quote, include it verbatim in quotation marks with the author (e.g. "quote here" — u/author). NEVER invent quotes or attribute statements to usernames not in the data.
- Always name the specific subreddit where a pattern appears (e.g. "In r/startups, founders report...")
- Do NOT reference insight numbers, indices, or counts like "Insight 5" or "(Insights 3 and 7)" — just state the finding naturally
- Give actionable recommendations, not just summaries"""

    try:
        from app.llm.factory import get_llm_provider
        provider = await get_llm_provider()
        response = await provider.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.4,
            max_tokens=2048,
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
