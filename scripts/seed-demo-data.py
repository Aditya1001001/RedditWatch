#!/usr/bin/env python3
"""Seed a deterministic RedditWatch demo dataset.

This creates a small SaaS Starter audience with source-like posts, comments,
and quote-backed market signals. It is for local demos and screen recordings;
it does not fetch Reddit or call an LLM.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.database import async_session_maker, init_db  # noqa: E402
from app.models import Audience, Comment, Insight, MonitoredSubreddit, Post  # noqa: E402


DEMO_SUBREDDITS = [
    {
        "name": "saas",
        "display_name": "r/SaaS",
        "description": "SaaS founders and operators discussing pricing, churn, product, and growth.",
        "subscribers": 627_709,
        "category": "startup_business",
    },
    {
        "name": "startups",
        "display_name": "r/startups",
        "description": "Startup founders discussing validation, MVPs, fundraising, and growth.",
        "subscribers": 2_014_249,
        "category": "startup_business",
    },
    {
        "name": "productmanagement",
        "display_name": "r/ProductManagement",
        "description": "Product managers discussing roadmap, research, prioritization, and tooling.",
        "subscribers": 256_162,
        "category": "product_design",
    },
    {
        "name": "marketing",
        "display_name": "r/marketing",
        "description": "Marketers discussing channels, attribution, positioning, and campaigns.",
        "subscribers": 1_920_714,
        "category": "marketing_growth",
    },
]


DEMO_POSTS = [
    Post(
        id="rw_demo_pricing",
        subreddit="saas",
        title="How do you explain SaaS pricing without confusing buyers?",
        body=(
            "We keep losing trials after the pricing page. People ask whether seats, "
            "usage, and add-ons are all separate. I need a clearer way to package this."
        ),
        author="founderpricing",
        score=84,
        upvote_ratio=0.91,
        num_comments=38,
        permalink="/r/SaaS/comments/rw_demo_pricing/pricing_confusion/",
        created_utc=datetime(2026, 6, 18, 15, 30, tzinfo=timezone.utc),
        analyzed=True,
        analysis_status="complete",
        signal_score=82,
        category="pain_point",
    ),
    Post(
        id="rw_demo_onboard",
        subreddit="productmanagement",
        title="Users sign up but never reach the activation step",
        body=(
            "Our activation metric is stuck. Interviews suggest people understand the "
            "value but cannot figure out what to do first inside the product."
        ),
        author="pm_researcher",
        score=57,
        upvote_ratio=0.88,
        num_comments=24,
        permalink="/r/ProductManagement/comments/rw_demo_onboard/activation_step/",
        created_utc=datetime(2026, 6, 19, 10, 15, tzinfo=timezone.utc),
        analyzed=True,
        analysis_status="complete",
        signal_score=74,
        category="pain_point",
    ),
    Post(
        id="rw_demo_attrib",
        subreddit="marketing",
        title="What are teams using for attribution now that reports disagree?",
        body=(
            "GA4, CRM, ad platforms, and warehouse dashboards all tell different stories. "
            "Leadership keeps asking which channel is actually working."
        ),
        author="channelops",
        score=63,
        upvote_ratio=0.9,
        num_comments=31,
        permalink="/r/marketing/comments/rw_demo_attrib/reports_disagree/",
        created_utc=datetime(2026, 6, 20, 9, 45, tzinfo=timezone.utc),
        analyzed=True,
        analysis_status="complete",
        signal_score=78,
        category="solution_request",
    ),
    Post(
        id="rw_demo_validation",
        subreddit="startups",
        title="How much evidence is enough before building the MVP?",
        body=(
            "I have calls, a waitlist, and some Reddit threads, but I still do not know "
            "whether this is real demand or just people being polite."
        ),
        author="earlybuilder",
        score=49,
        upvote_ratio=0.86,
        num_comments=27,
        permalink="/r/startups/comments/rw_demo_validation/enough_evidence/",
        created_utc=datetime(2026, 6, 21, 12, 5, tzinfo=timezone.utc),
        analyzed=True,
        analysis_status="complete",
        signal_score=70,
        category="advice_request",
    ),
]


DEMO_COMMENTS = [
    Comment(
        id="rw_c_pricing_1",
        post_id="rw_demo_pricing",
        parent_id="rw_demo_pricing",
        body="The worst part is when pricing looks simple until procurement asks about seats, credits, and add-ons.",
        author="opsbuyer",
        score=31,
        depth=0,
        created_utc=datetime(2026, 6, 18, 16, 5, tzinfo=timezone.utc),
    ),
    Comment(
        id="rw_c_pricing_2",
        post_id="rw_demo_pricing",
        parent_id="rw_demo_pricing",
        body="If I need a spreadsheet to understand the plan, I usually move on to another vendor.",
        author="teamlead42",
        score=22,
        depth=0,
        created_utc=datetime(2026, 6, 18, 16, 25, tzinfo=timezone.utc),
    ),
    Comment(
        id="rw_c_onboard_1",
        post_id="rw_demo_onboard",
        parent_id="rw_demo_onboard",
        body="The empty dashboard is where people quit. They need a concrete first task, not a tour.",
        author="activation_pm",
        score=28,
        depth=0,
        created_utc=datetime(2026, 6, 19, 11, 0, tzinfo=timezone.utc),
    ),
    Comment(
        id="rw_c_attrib_1",
        post_id="rw_demo_attrib",
        parent_id="rw_demo_attrib",
        body="We spend half the meeting arguing about which report is correct instead of deciding what to do next.",
        author="growth_ops",
        score=34,
        depth=0,
        created_utc=datetime(2026, 6, 20, 10, 30, tzinfo=timezone.utc),
    ),
    Comment(
        id="rw_c_validation_1",
        post_id="rw_demo_validation",
        parent_id="rw_demo_validation",
        body="A waitlist is weak evidence unless people describe the workaround they already use.",
        author="b2b_founder",
        score=26,
        depth=0,
        created_utc=datetime(2026, 6, 21, 13, 20, tzinfo=timezone.utc),
    ),
]


DEMO_INSIGHTS = [
    Insight(
        post_id="rw_demo_pricing",
        comment_id="rw_c_pricing_1",
        type="pain_point",
        theme_key="pricing_confusion",
        category="pricing",
        title="Pricing packages create buyer confusion",
        description="SaaS buyers struggle when pricing combines seats, credits, and add-ons without a clear packaging story.",
        quote="The worst part is when pricing looks simple until procurement asks about seats, credits, and add-ons.",
        quote_author="opsbuyer",
        quote_score=31,
        permalink="/r/SaaS/comments/rw_demo_pricing/pricing_confusion/",
        intensity_score=86,
        confidence_score=92,
        llm_provider="demo_seed",
        llm_model="source-backed-sample",
    ),
    Insight(
        post_id="rw_demo_pricing",
        comment_id="rw_c_pricing_2",
        type="product_mention",
        theme_key="pricing_confusion",
        category="pricing",
        title="Complex pricing pushes buyers toward alternatives",
        description="Confusing pricing is not just a comprehension problem; it can cause evaluators to abandon a vendor.",
        quote="If I need a spreadsheet to understand the plan, I usually move on to another vendor.",
        quote_author="teamlead42",
        quote_score=22,
        permalink="/r/SaaS/comments/rw_demo_pricing/pricing_confusion/",
        intensity_score=78,
        confidence_score=88,
        sentiment="negative",
        llm_provider="demo_seed",
        llm_model="source-backed-sample",
    ),
    Insight(
        post_id="rw_demo_onboard",
        comment_id="rw_c_onboard_1",
        type="pain_point",
        theme_key="activation_friction",
        category="onboarding",
        title="Empty-state onboarding blocks activation",
        description="Users understand the product promise but fail when the first in-product action is unclear.",
        quote="The empty dashboard is where people quit. They need a concrete first task, not a tour.",
        quote_author="activation_pm",
        quote_score=28,
        permalink="/r/ProductManagement/comments/rw_demo_onboard/activation_step/",
        intensity_score=82,
        confidence_score=91,
        llm_provider="demo_seed",
        llm_model="source-backed-sample",
    ),
    Insight(
        post_id="rw_demo_attrib",
        comment_id="rw_c_attrib_1",
        type="solution_request",
        theme_key="attribution_confidence",
        category="marketing",
        title="Teams need decision-ready attribution",
        description="Marketing teams are asking for attribution workflows that resolve conflicting reports into a decision.",
        quote="We spend half the meeting arguing about which report is correct instead of deciding what to do next.",
        quote_author="growth_ops",
        quote_score=34,
        permalink="/r/marketing/comments/rw_demo_attrib/reports_disagree/",
        intensity_score=80,
        confidence_score=90,
        llm_provider="demo_seed",
        llm_model="source-backed-sample",
    ),
    Insight(
        post_id="rw_demo_validation",
        comment_id="rw_c_validation_1",
        type="advice_request",
        theme_key="demand_validation",
        category="validation",
        title="Builders need stronger demand evidence than waitlists",
        description="Founders are looking for ways to distinguish polite interest from repeated workarounds and real buying intent.",
        quote="A waitlist is weak evidence unless people describe the workaround they already use.",
        quote_author="b2b_founder",
        quote_score=26,
        permalink="/r/startups/comments/rw_demo_validation/enough_evidence/",
        intensity_score=74,
        confidence_score=87,
        llm_provider="demo_seed",
        llm_model="source-backed-sample",
    ),
]


async def seed_demo_data() -> None:
    await init_db()

    async with async_session_maker() as session:
        post_ids = [post.id for post in DEMO_POSTS]
        comment_ids = [comment.id for comment in DEMO_COMMENTS]

        await session.execute(delete(Insight).where(Insight.post_id.in_(post_ids)))
        await session.execute(delete(Comment).where(Comment.id.in_(comment_ids)))
        await session.execute(delete(Post).where(Post.id.in_(post_ids)))

        for sub_data in DEMO_SUBREDDITS:
            existing = await session.get(MonitoredSubreddit, sub_data["name"])
            if existing:
                for key, value in sub_data.items():
                    setattr(existing, key, value)
                existing.enabled = True
            else:
                session.add(MonitoredSubreddit(enabled=True, **sub_data))

        result = await session.execute(
            select(Audience)
            .options(selectinload(Audience.subreddits))
            .where(Audience.name == "SaaS Starter")
        )
        audience = result.scalar_one_or_none()
        if audience is None:
            audience = Audience(
                name="SaaS Starter",
                description="Demo audience for SaaS, startup, product, and marketing signals.",
                color="#5b9bd5",
                active=True,
            )
            session.add(audience)
            await session.flush()
        else:
            audience.description = "Demo audience for SaaS, startup, product, and marketing signals."
            audience.color = "#5b9bd5"
            audience.active = True

        audience.subreddits.clear()
        for sub_data in DEMO_SUBREDDITS:
            sub = await session.get(MonitoredSubreddit, sub_data["name"])
            if sub:
                audience.subreddits.append(sub)

        for post in DEMO_POSTS:
            session.add(post)
        for comment in DEMO_COMMENTS:
            session.add(comment)
        for insight in DEMO_INSIGHTS:
            session.add(insight)

        await session.commit()

    try:
        from app.services.search import get_search_service

        async with async_session_maker() as session:
            rows = await session.execute(select(Insight, Post.subreddit).join(Post))
            insight_data = [
                {
                    "id": insight.id,
                    "text": f"{insight.title}. {insight.description or ''} {insight.quote or ''}",
                    "type": insight.type,
                    "theme_key": insight.theme_key,
                    "intensity_score": insight.intensity_score or 0,
                    "post_id": insight.post_id,
                    "subreddit": subreddit,
                }
                for insight, subreddit in rows
            ]
        stats = get_search_service().reindex_all(insight_data)
        print(f"Indexed {stats['indexed_count']} signals in ChromaDB.")
    except Exception as exc:
        print(f"Warning: demo data saved, but ChromaDB reindex failed: {exc}")

    print("Demo data loaded: SaaS Starter audience with 4 posts and 5 source-backed signals.")


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
