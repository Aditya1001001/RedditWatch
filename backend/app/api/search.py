"""Search API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Insight, Post
from app.services.search import get_search_service

router = APIRouter()


class SearchResult(BaseModel):
    """Search result item."""
    insight_id: int
    text: str
    similarity: Optional[float] = None
    type: Optional[str] = None
    theme_key: Optional[str] = None
    intensity_score: Optional[int] = None
    post_id: Optional[str] = None


class SearchResponse(BaseModel):
    """Search response."""
    query: str
    results: list[SearchResult]
    total: int


class DuplicatePair(BaseModel):
    """Duplicate insight pair."""
    insight_1_id: int
    insight_2_id: int
    similarity: float


class IndexStats(BaseModel):
    """Index statistics."""
    indexed_count: int
    total_insights: int
    status: str
    error: Optional[str] = None


@router.get("", response_model=SearchResponse)
async def search_insights(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(default=20, ge=1, le=100),
    type: Optional[str] = Query(default=None, description="Filter by insight type"),
    theme_key: Optional[str] = Query(default=None, description="Filter by theme"),
    min_intensity: Optional[int] = Query(default=None, ge=0, le=100),
    audience_id: Optional[int] = Query(default=None),
    subreddits: Optional[str] = Query(default=None, description="Comma-separated subreddit names"),
    session: AsyncSession = Depends(get_session),
):
    """
    Semantic search across all insights.

    Uses vector similarity to find relevant insights even if
    exact keywords don't match. Optionally filter by audience.
    """
    from app.api.analysis import resolve_audience_subreddits

    search_service = get_search_service()

    # Fetch more results if we need to post-filter by subreddit
    sub_names = await resolve_audience_subreddits(session, audience_id, subreddits)
    fetch_limit = limit * 3 if sub_names is not None else limit

    try:
        results = await search_service.search_async(
            query=q,
            limit=fetch_limit,
            type_filter=type,
            theme_filter=theme_key,
            min_intensity=min_intensity,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Search timed out")

    # Post-filter by subreddit if audience specified
    if sub_names is not None:
        from app.models import Post
        # Batch-load subreddit for all post_ids in one query
        post_ids = [r["metadata"].get("post_id") for r in results if r["metadata"].get("post_id")]
        if post_ids:
            rows = await session.execute(
                select(Post.id, Post.subreddit).where(Post.id.in_(post_ids))
            )
            post_subreddit_map = {row.id: row.subreddit for row in rows}
            results = [
                r for r in results
                if post_subreddit_map.get(r["metadata"].get("post_id")) in sub_names
            ][:limit]
        else:
            results = []

    return SearchResponse(
        query=q,
        results=[
            SearchResult(
                insight_id=r["insight_id"],
                text=r["text"],
                similarity=r.get("similarity"),
                type=r["metadata"].get("type"),
                theme_key=r["metadata"].get("theme_key"),
                intensity_score=r["metadata"].get("intensity_score"),
                post_id=r["metadata"].get("post_id"),
            )
            for r in results[:limit]
        ],
        total=len(results),
    )


@router.get("/similar/{insight_id}")
async def find_similar_insights(
    insight_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    threshold: float = Query(default=0.7, ge=0.0, le=1.0),
):
    """
    Find insights similar to a given insight.

    Useful for finding related pain points or grouping similar feedback.
    """
    search_service = get_search_service()

    results = search_service.find_similar(
        insight_id=insight_id,
        limit=limit,
        threshold=threshold,
    )

    return {
        "insight_id": insight_id,
        "similar": [
            {
                "insight_id": r["insight_id"],
                "text": r["text"][:200] + "..." if len(r["text"]) > 200 else r["text"],
                "similarity": round(r["similarity"], 3),
                "type": r["metadata"].get("type"),
                "theme_key": r["metadata"].get("theme_key"),
            }
            for r in results
        ],
        "count": len(results),
    }


@router.get("/duplicates", response_model=list[DuplicatePair])
async def find_duplicates(
    threshold: float = Query(default=0.9, ge=0.5, le=1.0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Find potential duplicate insights.

    Returns pairs of insights that are very similar and may need
    to be merged or deduplicated.
    """
    search_service = get_search_service()

    duplicates = search_service.find_duplicates(
        threshold=threshold,
        limit=limit,
    )

    return [
        DuplicatePair(
            insight_1_id=d["insight_1_id"],
            insight_2_id=d["insight_2_id"],
            similarity=round(d["similarity"], 3),
        )
        for d in duplicates
    ]


@router.get("/stats", response_model=IndexStats)
async def get_index_stats(
    session: AsyncSession = Depends(get_session),
):
    """Get search index statistics."""
    from sqlalchemy import func

    search_service = get_search_service()
    stats = search_service.get_stats()

    # Get total insights from database
    result = await session.execute(select(func.count(Insight.id)))
    total_insights = result.scalar() or 0

    indexed = stats.get("indexed_count", 0)

    return IndexStats(
        indexed_count=indexed,
        total_insights=total_insights,
        status="synced" if indexed == total_insights else "needs_reindex",
        error=stats.get("error"),
    )


@router.post("/reindex")
async def reindex_all_insights(
    session: AsyncSession = Depends(get_session),
):
    """
    Reindex all insights in the vector store.

    This clears the existing index and rebuilds it from the database.
    Run this after bulk imports or if the index gets out of sync.
    """
    search_service = get_search_service()

    # Get all insights with subreddit from database
    result = await session.execute(
        select(Insight, Post.subreddit).join(Post)
    )
    rows = result.all()

    # Format for indexing
    insight_data = [
        {
            "id": i.id,
            "text": f"{i.title}. {i.description or ''} {i.quote or ''}",
            "type": i.type,
            "theme_key": i.theme_key,
            "intensity_score": i.intensity_score or 0,
            "post_id": i.post_id,
            "subreddit": sub,
        }
        for i, sub in rows
    ]

    # Reindex
    stats = search_service.reindex_all(insight_data)

    return {
        "message": "Reindex complete",
        "indexed_count": stats["indexed_count"],
    }
