"""LLM-based analysis service for extracting insights from Reddit posts."""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.llm.factory import get_llm_provider
from app.models import Comment, Insight, Post

logger = logging.getLogger(__name__)

# System prompt for post analysis
ANALYSIS_SYSTEM_PROMPT = """You are an expert market researcher analyzing Reddit posts to find business opportunities.

Your task is to extract actionable insights from posts and comments. Focus on:
1. Pain points - Problems people are frustrated about
2. Solution requests - People actively looking for tools/products
3. Product mentions - References to existing products (with sentiment)
4. Opportunities - Gaps in the market or underserved needs

Be specific and quote directly from the source when possible."""

# Prompt template for analyzing a single post
ANALYZE_POST_PROMPT = """Analyze this Reddit post from r/{subreddit} and extract insights.

POST TITLE: {title}

POST BODY:
{body}

TOP COMMENTS:
{comments}

---

Extract insights in this exact JSON format:
{{
    "category": "pain_point" | "solution_request" | "product_mention" | "opportunity" | "general",
    "insights": [
        {{
            "type": "pain_point" | "solution_request" | "product_mention" | "opportunity",
            "theme_key": "lowercase_underscore_theme",
            "title": "Short descriptive title",
            "description": "Detailed description of the insight",
            "quote": "Exact quote from post or comment",
            "quote_author": "username",
            "intensity_score": 0-100,
            "product_name": "Product name if product_mention",
            "sentiment": "positive" | "negative" | "neutral" | "mixed"
        }}
    ]
}}

Rules:
- theme_key must be lowercase with underscores (e.g., "pricing_confusion", "onboarding_friction")
- intensity_score: 0-30 mild annoyance, 31-60 moderate frustration, 61-80 significant pain, 81-100 severe/urgent
- Only include product_name and sentiment for product_mention type
- Quote must be verbatim from the text
- Return empty insights array if nothing actionable found
- Maximum 5 insights per post

Return ONLY valid JSON, no other text."""


class AnalyzerService:
    """Analyzes Reddit posts using LLM to extract insights."""

    def __init__(self):
        self._llm = None

    async def _get_llm(self):
        """Get or create LLM provider."""
        if self._llm is None:
            self._llm = await get_llm_provider()
        return self._llm

    async def analyze_post(
        self,
        session: AsyncSession,
        post: Post,
        include_comments: bool = True,
    ) -> list[Insight]:
        """
        Analyze a single post and extract insights.

        Args:
            session: Database session
            post: Post to analyze
            include_comments: Whether to include comments in analysis

        Returns:
            List of extracted Insight objects
        """
        insights = []

        # Get comments if requested
        comments_text = ""
        if include_comments:
            result = await session.execute(
                select(Comment)
                .where(Comment.post_id == post.id)
                .order_by(Comment.score.desc())
                .limit(10)
            )
            comments = result.scalars().all()
            if comments:
                comments_text = "\n\n".join([
                    f"[{c.author}] (score: {c.score}): {c.body[:500]}"
                    for c in comments
                ])

        # Build prompt
        prompt = ANALYZE_POST_PROMPT.format(
            subreddit=post.subreddit,
            title=post.title,
            body=post.body[:2000] if post.body else "(no body text)",
            comments=comments_text or "(no comments)",
        )

        try:
            llm = await self._get_llm()

            # Track analysis timing
            start_time = time.time()
            result = await llm.generate_json(prompt, system=ANALYSIS_SYSTEM_PROMPT)
            duration_ms = int((time.time() - start_time) * 1000)

            # Update post with analysis metadata
            post.category = result.get("category", "general")
            post.analyzed = True
            post.analyzed_at = datetime.now(timezone.utc)
            post.analysis_duration_ms = duration_ms

            # Extract insights
            for item in result.get("insights", []):
                insight = Insight(
                    post_id=post.id,
                    type=item.get("type", "pain_point"),
                    theme_key=item.get("theme_key", "unknown"),
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    quote=item.get("quote"),
                    quote_author=item.get("quote_author"),
                    permalink=post.permalink,
                    intensity_score=item.get("intensity_score", 50),
                    product_name=item.get("product_name"),
                    sentiment=item.get("sentiment"),
                    llm_provider=llm.name,
                    llm_model=llm.model_name,
                )
                session.add(insight)
                insights.append(insight)

            logger.info(
                f"Analyzed post {post.id}: category={post.category}, "
                f"insights={len(insights)}, duration={duration_ms}ms"
            )

        except Exception as e:
            logger.error(f"Failed to analyze post {post.id}: {e}")
            post.analyzed = True  # Mark as analyzed even on failure to avoid retry loops

        return insights

    async def analyze_unanalyzed_posts(
        self,
        limit: int = 10,
        min_score: int = 3,
    ) -> dict:
        """
        Analyze posts that haven't been analyzed yet.

        Args:
            limit: Maximum number of posts to analyze
            min_score: Minimum post score to consider

        Returns:
            Statistics about the analysis run
        """
        stats = {
            "posts_analyzed": 0,
            "insights_extracted": 0,
            "total_duration_ms": 0,
            "avg_duration_ms": 0,
            "errors": [],
        }

        run_start = time.time()

        async with async_session_maker() as session:
            # Get unanalyzed posts
            result = await session.execute(
                select(Post)
                .where(
                    and_(
                        Post.analyzed == False,
                        Post.score >= min_score,
                    )
                )
                .order_by(Post.score.desc())
                .limit(limit)
            )
            posts = result.scalars().all()

            for post in posts:
                try:
                    insights = await self.analyze_post(session, post)
                    stats["posts_analyzed"] += 1
                    stats["insights_extracted"] += len(insights)
                    if post.analysis_duration_ms:
                        stats["total_duration_ms"] += post.analysis_duration_ms
                except Exception as e:
                    logger.error(f"Error analyzing post {post.id}: {e}")
                    stats["errors"].append({
                        "post_id": post.id,
                        "error": str(e),
                    })

            await session.commit()

        # Calculate averages
        if stats["posts_analyzed"] > 0:
            stats["avg_duration_ms"] = stats["total_duration_ms"] // stats["posts_analyzed"]

        total_run_time = int((time.time() - run_start) * 1000)

        logger.info(
            f"Analysis complete: {stats['posts_analyzed']} posts, "
            f"{stats['insights_extracted']} insights, "
            f"total={total_run_time}ms, avg={stats['avg_duration_ms']}ms/post"
        )

        return stats

    async def get_insights_by_theme(
        self,
        session: AsyncSession,
        theme_key: Optional[str] = None,
        insight_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[Insight]:
        """Get insights grouped by theme."""
        query = select(Insight).order_by(Insight.intensity_score.desc())

        if theme_key:
            query = query.where(Insight.theme_key == theme_key)
        if insight_type:
            query = query.where(Insight.type == insight_type)

        query = query.limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_theme_summary(self, session: AsyncSession) -> list[dict]:
        """Get aggregated theme statistics."""
        # Get all insights
        result = await session.execute(select(Insight))
        insights = result.scalars().all()

        # Aggregate by theme_key
        themes = {}
        for insight in insights:
            key = insight.theme_key
            if key not in themes:
                themes[key] = {
                    "theme_key": key,
                    "count": 0,
                    "total_intensity": 0,
                    "types": set(),
                    "top_quotes": [],
                }
            themes[key]["count"] += 1
            themes[key]["total_intensity"] += insight.intensity_score or 0
            themes[key]["types"].add(insight.type)
            if insight.quote and len(themes[key]["top_quotes"]) < 3:
                themes[key]["top_quotes"].append({
                    "quote": insight.quote[:200],
                    "author": insight.quote_author,
                    "score": insight.intensity_score,
                })

        # Calculate averages and format
        summary = []
        for key, data in themes.items():
            avg_intensity = data["total_intensity"] / data["count"] if data["count"] > 0 else 0
            summary.append({
                "theme_key": key,
                "count": data["count"],
                "avg_intensity": round(avg_intensity, 1),
                "combined_score": round(data["count"] * avg_intensity / 10, 1),
                "types": list(data["types"]),
                "top_quotes": data["top_quotes"],
            })

        # Sort by combined score
        summary.sort(key=lambda x: x["combined_score"], reverse=True)

        return summary


# Global analyzer instance
_analyzer: Optional[AnalyzerService] = None


def get_analyzer() -> AnalyzerService:
    """Get the global analyzer service."""
    global _analyzer
    if _analyzer is None:
        _analyzer = AnalyzerService()
    return _analyzer
