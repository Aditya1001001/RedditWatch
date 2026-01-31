"""Post API endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models import Comment, Insight, Post

router = APIRouter()


class CommentResponse(BaseModel):
    """Comment response model."""
    id: str
    body: str
    author: Optional[str] = None
    score: int = 0
    created_utc: Optional[datetime] = None

    class Config:
        from_attributes = True


class PostResponse(BaseModel):
    """Post response model."""
    id: str
    subreddit: str
    title: str
    body: Optional[str] = None
    author: Optional[str] = None
    score: int = 0
    upvote_ratio: Optional[float] = None
    num_comments: int = 0
    permalink: Optional[str] = None
    url: Optional[str] = None
    created_utc: Optional[datetime] = None
    collected_at: datetime
    analyzed: bool = False
    category: Optional[str] = None
    reddit_url: str

    class Config:
        from_attributes = True


class PostDetailResponse(PostResponse):
    """Post with comments and insights."""
    comments: list[CommentResponse] = []
    insight_count: int = 0


class PostListResponse(BaseModel):
    """Paginated post list."""
    posts: list[PostResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class PostStats(BaseModel):
    """Post statistics."""
    total_posts: int
    analyzed_posts: int
    unanalyzed_posts: int
    posts_by_subreddit: dict
    posts_by_category: dict


@router.get("", response_model=PostListResponse)
async def list_posts(
    subreddit: Optional[str] = None,
    category: Optional[str] = None,
    analyzed: Optional[bool] = None,
    min_score: int = 0,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """
    List posts with filters.

    Supports filtering by subreddit, category, analysis status, and minimum score.
    """
    # Build query
    query = select(Post)

    if subreddit:
        query = query.where(Post.subreddit == subreddit.lower().replace("r/", ""))
    if category:
        query = query.where(Post.category == category)
    if analyzed is not None:
        query = query.where(Post.analyzed == analyzed)
    if min_score > 0:
        query = query.where(Post.score >= min_score)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # Apply pagination and sorting
    query = query.order_by(desc(Post.created_utc))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(query)
    posts = result.scalars().all()

    return PostListResponse(
        posts=[
            PostResponse(
                id=p.id,
                subreddit=p.subreddit,
                title=p.title,
                body=p.body[:500] if p.body else None,  # Truncate body in list
                author=p.author,
                score=p.score,
                upvote_ratio=p.upvote_ratio,
                num_comments=p.num_comments,
                permalink=p.permalink,
                url=p.url,
                created_utc=p.created_utc,
                collected_at=p.collected_at,
                analyzed=p.analyzed,
                category=p.category,
                reddit_url=p.reddit_url,
            )
            for p in posts
        ],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.get("/stats", response_model=PostStats)
async def get_post_stats(session: AsyncSession = Depends(get_session)):
    """Get aggregate post statistics."""
    # Total counts
    total = (await session.execute(select(func.count(Post.id)))).scalar() or 0
    analyzed = (await session.execute(
        select(func.count(Post.id)).where(Post.analyzed == True)
    )).scalar() or 0

    # By subreddit
    subreddit_query = (
        select(Post.subreddit, func.count(Post.id))
        .group_by(Post.subreddit)
        .order_by(desc(func.count(Post.id)))
    )
    subreddit_result = await session.execute(subreddit_query)
    posts_by_subreddit = {row[0]: row[1] for row in subreddit_result}

    # By category
    category_query = (
        select(Post.category, func.count(Post.id))
        .where(Post.category.isnot(None))
        .group_by(Post.category)
    )
    category_result = await session.execute(category_query)
    posts_by_category = {row[0]: row[1] for row in category_result}

    return PostStats(
        total_posts=total,
        analyzed_posts=analyzed,
        unanalyzed_posts=total - analyzed,
        posts_by_subreddit=posts_by_subreddit,
        posts_by_category=posts_by_category,
    )


@router.get("/{post_id}", response_model=PostDetailResponse)
async def get_post(
    post_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get a single post with its comments."""
    query = (
        select(Post)
        .where(Post.id == post_id)
        .options(selectinload(Post.comments), selectinload(Post.insights))
    )
    result = await session.execute(query)
    post = result.scalar_one_or_none()

    if not post:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")

    # Sort comments by score
    sorted_comments = sorted(post.comments, key=lambda c: c.score, reverse=True)

    return PostDetailResponse(
        id=post.id,
        subreddit=post.subreddit,
        title=post.title,
        body=post.body,
        author=post.author,
        score=post.score,
        upvote_ratio=post.upvote_ratio,
        num_comments=post.num_comments,
        permalink=post.permalink,
        url=post.url,
        created_utc=post.created_utc,
        collected_at=post.collected_at,
        analyzed=post.analyzed,
        category=post.category,
        reddit_url=post.reddit_url,
        comments=[
            CommentResponse(
                id=c.id,
                body=c.body,
                author=c.author,
                score=c.score,
                created_utc=c.created_utc,
            )
            for c in sorted_comments[:50]  # Limit comments returned
        ],
        insight_count=len(post.insights),
    )


@router.delete("/{post_id}")
async def delete_post(
    post_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Delete a post and all related data (comments, insights).
    """
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")

    await session.delete(post)
    await session.commit()

    return {"message": f"Post {post_id} deleted"}
