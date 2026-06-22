"""Tests for post API response mapping."""

from datetime import datetime, timezone

from app.api.posts import post_to_response
from app.models import Post


def _post(body: str = "body") -> Post:
    return Post(
        id="abc123",
        subreddit="saas",
        title="Pricing feedback",
        body=body,
        author="founder",
        score=42,
        upvote_ratio=0.9,
        num_comments=12,
        permalink="/r/saas/comments/abc123/pricing_feedback/",
        created_utc=datetime(2026, 1, 30, tzinfo=timezone.utc),
        collected_at=datetime(2026, 1, 31, tzinfo=timezone.utc),
        analyzed=True,
        analysis_status="skipped",
        analysis_skip_reason="likely_self_promotion_low_response",
        signal_score=8,
        category="general",
    )


def test_post_to_response_truncates_list_body():
    response = post_to_response(_post("x" * 550))

    assert len(response.body) == 500
    assert response.body_truncated is True


def test_post_to_response_keeps_full_detail_body():
    response = post_to_response(_post("x" * 550), truncate_body=False)

    assert len(response.body) == 550
    assert response.body_truncated is False


def test_post_to_response_includes_analysis_metadata():
    response = post_to_response(_post())

    assert response.analysis_status == "skipped"
    assert response.analysis_skip_reason == "likely_self_promotion_low_response"
    assert response.signal_score == 8
    assert response.reddit_url == "https://reddit.com/r/saas/comments/abc123/pricing_feedback/"
