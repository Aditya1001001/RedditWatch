"""Tests for API endpoints using the FastAPI test client."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import patch, AsyncMock

from app.database import Base, get_session
from app.main import app


@pytest_asyncio.fixture
async def test_app():
    """Create a test app with in-memory database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    from app.models import comment, insight, post, subreddit, theme  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_session():
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_session

    yield app

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_app):
    """Create an async test client."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
class TestHealthEndpoint:
    async def test_health_check(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "redditwatch"


@pytest.mark.asyncio
class TestCollectionEndpoints:
    async def test_collection_status(self, client):
        response = await client.get("/api/collect/status")
        assert response.status_code == 200

    async def test_trigger_collection_requires_followed_audience(self, client):
        """Collection should explain why it cannot run with no followed audience."""
        with patch("app.api.collect.get_collector") as mock:
            collector = AsyncMock()
            collector.collect_all = AsyncMock(return_value={
                "subreddits_processed": 0,
                "posts_collected": 0,
                "posts_new": 0,
                "comments_collected": 0,
                "errors": [],
            })
            mock.return_value = collector

            response = await client.post("/api/collect")
            assert response.status_code == 400
            data = response.json()
            assert "No followed audiences" in data["detail"]
            collector.collect_all.assert_not_called()


@pytest.mark.asyncio
class TestAnalysisEndpoints:
    async def test_analysis_status(self, client):
        response = await client.get("/api/analyze/status")
        assert response.status_code == 200
        data = response.json()
        assert "total_posts" in data
        assert "status" in data

    async def test_get_themes_empty(self, client):
        response = await client.get("/api/analyze/themes")
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_insights_empty(self, client):
        response = await client.get("/api/analyze/insights")
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.asyncio
class TestPostEndpoints:
    async def test_list_posts_empty(self, client):
        response = await client.get("/api/posts")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["posts"] == []

    async def test_post_not_found(self, client):
        response = await client.get("/api/posts/nonexistent")
        assert response.status_code == 404

    async def test_delete_post_not_found(self, client):
        response = await client.delete("/api/posts/nonexistent")
        assert response.status_code == 404

    async def test_post_stats(self, client):
        response = await client.get("/api/posts/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_posts"] == 0


@pytest.mark.asyncio
class TestSubredditEndpoints:
    async def test_list_subreddits_empty(self, client):
        response = await client.get("/api/subreddits")
        assert response.status_code == 200
        assert response.json() == []

    async def test_add_invalid_subreddit_name(self, client):
        response = await client.post(
            "/api/subreddits",
            json={"name": "a"},  # too short
        )
        assert response.status_code == 422

    async def test_add_subreddit_special_chars_rejected(self, client):
        response = await client.post(
            "/api/subreddits",
            json={"name": "bad name!"},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestRefreshEndpoints:
    async def test_refresh_post_not_found(self, client):
        response = await client.post("/api/collect/refresh/nonexistent")
        assert response.status_code == 404
