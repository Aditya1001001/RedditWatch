"""Themes API endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_themes():
    """List themes sorted by combined score."""
    # TODO: Implement in Phase 4
    return {"message": "Themes endpoint - coming in Phase 4"}


@router.get("/{theme_id}")
async def get_theme(theme_id: int):
    """Get a theme with all related insights."""
    # TODO: Implement in Phase 4
    return {"message": f"Theme {theme_id} - coming in Phase 4"}
