"""Shared test fixtures for RedditWatch."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base


@pytest.fixture(scope="session")
def event_loop():
    """Create a shared event loop for all tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Import models to register them
    from app.models import comment, insight, post, subreddit, theme  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Create a test database session."""
    session_maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def sample_post(db_session):
    """Create a sample post in the test database."""
    from app.models import Post

    post = Post(
        id="test123",
        subreddit="saas",
        title="What's the hardest part of building a SaaS?",
        body="I've been working on my SaaS for 6 months and pricing is killing me.",
        author="test_user",
        score=42,
        upvote_ratio=0.92,
        num_comments=15,
        permalink="/r/saas/comments/test123/whats_the_hardest_part/",
        created_utc=datetime(2026, 1, 30, tzinfo=timezone.utc),
    )
    db_session.add(post)
    await db_session.flush()
    return post


@pytest_asyncio.fixture
async def sample_comments(db_session, sample_post):
    """Create sample comments for the test post."""
    from app.models import Comment

    comments = [
        Comment(
            id="comment1",
            post_id=sample_post.id,
            parent_id=sample_post.id,
            body="Definitely pricing. I changed mine 5 times.",
            author="commenter1",
            score=25,
            depth=0,
        ),
        Comment(
            id="comment2",
            post_id=sample_post.id,
            parent_id=sample_post.id,
            body="Onboarding is the real killer. Users sign up and never come back.",
            author="commenter2",
            score=18,
            depth=0,
        ),
    ]
    for c in comments:
        db_session.add(c)
    await db_session.flush()
    return comments


@pytest_asyncio.fixture
async def sample_insights(db_session, sample_post):
    """Create sample insights for testing."""
    from app.models import Insight

    insights = [
        Insight(
            post_id=sample_post.id,
            type="pain_point",
            theme_key="pricing_confusion",
            title="SaaS pricing complexity",
            description="Founders struggle with pricing strategy",
            quote="pricing is killing me",
            quote_author="test_user",
            intensity_score=75,
            permalink=sample_post.permalink,
        ),
        Insight(
            post_id=sample_post.id,
            type="opportunity",
            theme_key="onboarding_friction",
            title="Onboarding improvement opportunity",
            description="Users churn after signup",
            quote="Users sign up and never come back",
            quote_author="commenter2",
            intensity_score=60,
            permalink=sample_post.permalink,
        ),
    ]
    for ins in insights:
        db_session.add(ins)
    await db_session.flush()
    return insights


@pytest.fixture
def mock_llm():
    """Create a mock LLM provider."""
    llm = AsyncMock()
    llm.name = "mock"
    llm.model_name = "mock-model"
    llm.generate_json = AsyncMock(return_value={
        "category": "pain_point",
        "insights": [
            {
                "type": "pain_point",
                "theme_key": "pricing_confusion",
                "title": "Pricing is confusing",
                "description": "Users struggle with pricing tiers",
                "quote": "pricing is killing me",
                "quote_author": "test_user",
                "intensity_score": 75,
            }
        ]
    })
    return llm


@pytest.fixture
def mock_reddit_response():
    """Create a mock Reddit API response."""
    return {
        "data": {
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "id": "abc123",
                        "subreddit": "saas",
                        "title": "Test Post",
                        "selftext": "Test body",
                        "author": "testuser",
                        "score": 42,
                        "upvote_ratio": 0.95,
                        "num_comments": 10,
                        "permalink": "/r/saas/comments/abc123/test_post/",
                        "is_self": True,
                        "stickied": False,
                        "created_utc": 1706648400,
                    }
                }
            ]
        }
    }
