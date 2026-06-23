"""Tests for export endpoints and report generation."""

from datetime import datetime, timezone

import pytest

from app.api.export import generate_report
from app.models import Audience, Insight, MonitoredSubreddit, Post


@pytest.mark.asyncio
async def test_audience_report_scopes_post_counts(db_session):
    saas = MonitoredSubreddit(name="saas", display_name="r/SaaS", enabled=True)
    marketing = MonitoredSubreddit(
        name="marketing", display_name="r/marketing", enabled=True
    )
    audience = Audience(name="SaaS Starter", active=True)
    audience.subreddits.append(saas)

    db_session.add_all([saas, marketing, audience])
    db_session.add_all(
        [
            Post(
                id="saas1",
                subreddit="saas",
                title="Pricing is confusing",
                score=20,
                num_comments=5,
                analyzed=True,
                analysis_status="complete",
                created_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            Post(
                id="marketing1",
                subreddit="marketing",
                title="Attribution is hard",
                score=30,
                num_comments=8,
                analyzed=True,
                analysis_status="complete",
                created_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.add(
        Insight(
            post_id="saas1",
            type="pain_point",
            theme_key="pricing_confusion",
            title="Pricing confusion",
            description="Founders struggle with pricing.",
            intensity_score=70,
        )
    )
    await db_session.flush()

    response = await generate_report(audience_id=audience.id, session=db_session)
    body = response.body.decode()

    assert "**Posts analyzed**: 1 of 1" in body
    assert "**Market signals extracted**: 1" in body
