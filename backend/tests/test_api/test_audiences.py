"""Tests for audience-specific API behavior."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.audiences import AskRequest, ask_about_audience
from app.models import Audience, Insight, MonitoredSubreddit, Post


@pytest.mark.asyncio
async def test_ask_response_includes_source_evidence(db_session, monkeypatch):
    subreddit = MonitoredSubreddit(name="saas", display_name="r/SaaS", enabled=True)
    audience = Audience(name="SaaS Starter", active=True)
    audience.subreddits.append(subreddit)
    post = Post(
        id="ask1",
        subreddit="saas",
        title="Pricing is confusing",
        score=20,
        num_comments=5,
        analyzed=True,
        analysis_status="complete",
        permalink="/r/SaaS/comments/ask1/pricing/",
        created_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    insight = Insight(
        post_id="ask1",
        type="pain_point",
        theme_key="pricing_confusion",
        title="Pricing confusion",
        description="Founders struggle with pricing pages.",
        quote="pricing looks simple until procurement asks about seats",
        quote_author="opsbuyer",
        intensity_score=80,
        permalink=post.permalink,
    )
    db_session.add_all([subreddit, audience, post, insight])
    await db_session.flush()

    search_service = SimpleNamespace(
        search_async=AsyncMock(
            return_value=[
                {
                    "metadata": {
                        "insight_id": insight.id,
                        "subreddit": "saas",
                    }
                }
            ]
        )
    )
    monkeypatch.setattr(
        "app.services.search.get_search_service",
        lambda: search_service,
    )

    provider = SimpleNamespace(
        model="test-model",
        generate=AsyncMock(
            return_value=SimpleNamespace(
                content="Pricing is a repeated pain signal.",
                model="test-model",
            )
        ),
    )
    monkeypatch.setattr(
        "app.llm.factory.get_llm_provider",
        AsyncMock(return_value=provider),
    )

    response = await ask_about_audience(
        audience.id,
        AskRequest(question="What should I pay attention to first?"),
        db_session,
    )

    assert response["answer"] == "Pricing is a repeated pain signal."
    assert response["model"] == "test-model"
    assert response["sources"][0]["insight_id"] == insight.id
    assert response["sources"][0]["quote"] == insight.quote
    assert response["sources"][0]["reddit_url"] == "https://reddit.com/r/SaaS/comments/ask1/pricing/"
