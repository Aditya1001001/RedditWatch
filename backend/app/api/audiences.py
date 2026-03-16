"""Audience management API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Audience, MonitoredSubreddit

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
