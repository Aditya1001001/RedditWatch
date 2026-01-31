"""Export API endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/insights")
async def export_insights(format: str = "json"):
    """Export insights as CSV or JSON."""
    # TODO: Implement in Phase 4
    return {"message": f"Export insights as {format} - coming in Phase 4"}


@router.get("/themes")
async def export_themes(format: str = "json"):
    """Export themes as CSV or JSON."""
    # TODO: Implement in Phase 4
    return {"message": f"Export themes as {format} - coming in Phase 4"}
