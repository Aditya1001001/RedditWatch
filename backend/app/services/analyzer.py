"""LLM-based analysis service for extracting insights from Reddit posts."""

import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.llm.factory import get_llm_provider
from app.models import Comment, Insight, Post

logger = logging.getLogger(__name__)

# Valid insight types
VALID_INSIGHT_TYPES = {"pain_point", "solution_request", "product_mention", "opportunity"}
VALID_CATEGORIES = {"pain_point", "solution_request", "product_mention", "opportunity", "general"}
VALID_SENTIMENTS = {"positive", "negative", "neutral", "mixed"}

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


# --- Pydantic models for LLM output validation ---

class InsightData(BaseModel):
    """Validated insight data from LLM output."""
    type: str
    theme_key: str = "unknown"
    title: str = ""
    description: str = ""
    quote: Optional[str] = None
    quote_author: Optional[str] = None
    intensity_score: int = Field(default=50, ge=0, le=100)
    product_name: Optional[str] = None
    sentiment: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in VALID_INSIGHT_TYPES:
            return "pain_point"  # Default fallback
        return v

    @field_validator("theme_key")
    @classmethod
    def normalize_theme_key(cls, v: str) -> str:
        # Normalize: lowercase, replace spaces/hyphens with underscores, strip non-alnum
        v = v.lower().strip()
        v = re.sub(r"[\s\-]+", "_", v)
        v = re.sub(r"[^a-z0-9_]", "", v)
        return v[:100] if v else "unknown"

    @field_validator("intensity_score", mode="before")
    @classmethod
    def clamp_intensity(cls, v) -> int:
        try:
            v = int(v)
        except (ValueError, TypeError):
            return 50
        return max(0, min(100, v))

    @field_validator("sentiment")
    @classmethod
    def validate_sentiment(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.lower().strip()
        return v if v in VALID_SENTIMENTS else None


class AnalysisOutput(BaseModel):
    """Validated LLM analysis output."""
    category: str = "general"
    insights: list[InsightData] = Field(default_factory=list)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        v = v.lower().strip()
        return v if v in VALID_CATEGORIES else "general"

    @field_validator("insights")
    @classmethod
    def limit_insights(cls, v: list[InsightData]) -> list[InsightData]:
        return v[:5]  # Max 5 per post


def validate_llm_output(raw: dict) -> AnalysisOutput:
    """Validate and normalize LLM JSON output using Pydantic."""
    try:
        return AnalysisOutput(**raw)
    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"LLM output validation failed, returning empty: {e}")
        return AnalysisOutput()


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

        Uses savepoints for isolation so one post failure doesn't
        rollback the entire batch.
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
            raw_result = await llm.generate_json(prompt, system=ANALYSIS_SYSTEM_PROMPT)
            duration_ms = int((time.time() - start_time) * 1000)

            # Validate LLM output
            validated = validate_llm_output(raw_result)

            # Update post with analysis metadata
            post.category = validated.category
            post.analyzed = True
            post.analyzed_at = datetime.now(timezone.utc)
            post.analysis_duration_ms = duration_ms

            # Extract insights from validated output
            for item in validated.insights:
                insight = Insight(
                    post_id=post.id,
                    type=item.type,
                    theme_key=item.theme_key,
                    title=item.title,
                    description=item.description,
                    quote=item.quote,
                    quote_author=item.quote_author,
                    permalink=post.permalink,
                    intensity_score=item.intensity_score,
                    product_name=item.product_name,
                    sentiment=item.sentiment,
                    llm_provider=llm.name,
                    llm_model=llm.model_name,
                )
                session.add(insight)
                insights.append(insight)

            # Auto-index new insights in ChromaDB
            if insights:
                try:
                    from app.services.search import get_search_service
                    search = get_search_service()
                    batch = []
                    for ins in insights:
                        text = f"{ins.title}. {ins.description or ''}"
                        if ins.quote:
                            text += f' "{ins.quote}"'
                        batch.append({
                            "id": ins.id if ins.id else hash(ins.title),
                            "text": text,
                            "type": ins.type,
                            "theme_key": ins.theme_key,
                            "intensity_score": ins.intensity_score or 0,
                            "post_id": ins.post_id,
                        })
                    if batch:
                        search.add_insights_batch(batch)
                except (ValueError, RuntimeError, OSError) as idx_err:
                    logger.warning(f"Failed to auto-index insights: {idx_err}")

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

        Uses savepoints per post so a single failure doesn't lose progress.
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
                    # Use savepoint per post for isolation
                    async with session.begin_nested():
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
        sort_by: Optional[str] = None,
        subreddit_names: Optional[list[str]] = None,
    ) -> list[Insight]:
        """Get insights grouped by theme."""
        from sqlalchemy.orm import joinedload

        query = select(Insight).options(joinedload(Insight.post))

        if subreddit_names is not None:
            query = query.join(Post).where(Post.subreddit.in_(subreddit_names))

        # Apply sorting
        if sort_by == "intensity":
            query = query.order_by(Insight.intensity_score.desc().nullslast())
        elif sort_by == "date":
            query = query.order_by(Insight.created_at.desc())
        else:
            query = query.order_by(Insight.intensity_score.desc().nullslast())

        if theme_key:
            query = query.where(Insight.theme_key == theme_key)
        if insight_type:
            query = query.where(Insight.type == insight_type)

        query = query.limit(limit)

        result = await session.execute(query)
        return list(result.scalars().unique().all())

    async def get_theme_summary(
        self,
        session: AsyncSession,
        subreddit_names: Optional[list[str]] = None,
    ) -> list[dict]:
        """Get aggregated theme statistics using SQL GROUP BY."""
        from sqlalchemy import case, literal_column

        # Use SQL aggregation instead of loading all insights into Python
        theme_query = (
            select(
                Insight.theme_key,
                func.count(Insight.id).label("count"),
                func.avg(Insight.intensity_score).label("avg_intensity"),
            )
            .group_by(Insight.theme_key)
            .order_by(func.count(Insight.id).desc())
        )
        if subreddit_names is not None:
            theme_query = theme_query.join(Post).where(Post.subreddit.in_(subreddit_names))
        theme_result = await session.execute(theme_query)
        theme_rows = theme_result.all()

        # Get types per theme
        type_query = (
            select(Insight.theme_key, Insight.type)
            .distinct()
        )
        if subreddit_names is not None:
            type_query = type_query.join(Post).where(Post.subreddit.in_(subreddit_names))
        type_result = await session.execute(type_query)
        theme_types: dict[str, set[str]] = {}
        for row in type_result:
            theme_types.setdefault(row[0], set()).add(row[1])

        # Get top quotes per theme (limit 3 per theme)
        quote_query = (
            select(Insight.theme_key, Insight.quote, Insight.quote_author, Insight.intensity_score)
            .where(Insight.quote.isnot(None))
            .order_by(Insight.intensity_score.desc().nullslast())
        )
        if subreddit_names is not None:
            quote_query = quote_query.join(Post).where(Post.subreddit.in_(subreddit_names))
        quote_result = await session.execute(quote_query)
        theme_quotes: dict[str, list[dict]] = {}
        for row in quote_result:
            key = row[0]
            if key not in theme_quotes:
                theme_quotes[key] = []
            if len(theme_quotes[key]) < 3:
                theme_quotes[key].append({
                    "quote": row[1][:200] if row[1] else "",
                    "author": row[2],
                    "score": row[3],
                })

        # Build summary
        summary = []
        for row in theme_rows:
            key = row[0]
            count = row[1]
            avg_intensity = float(row[2] or 0)
            combined_score = round(count * avg_intensity / 10, 1)

            summary.append({
                "theme_key": key,
                "count": count,
                "avg_intensity": round(avg_intensity, 1),
                "combined_score": combined_score,
                "types": list(theme_types.get(key, set())),
                "top_quotes": theme_quotes.get(key, []),
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
