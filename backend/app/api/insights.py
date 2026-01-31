"""Insights API endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_insights():
    """List insights with filters."""
    # TODO: Implement in Phase 3
    return {"message": "Insights endpoint - coming in Phase 3"}


@router.get("/stats")
async def get_insight_stats():
    """Get aggregate statistics."""
    # TODO: Implement in Phase 3
    return {"message": "Insight stats - coming in Phase 3"}
