"""LLM-based analysis service for extracting insights from Reddit posts."""

import difflib
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
from app.models.audience import Audience, audience_subreddits

logger = logging.getLogger(__name__)

# Valid insight types
VALID_INSIGHT_TYPES = {"pain_point", "solution_request", "product_mention", "opportunity", "advice_request", "idea", "money_talk"}
VALID_CATEGORIES = {"pain_point", "solution_request", "product_mention", "opportunity", "advice_request", "idea", "money_talk", "general"}
VALID_SENTIMENTS = {"positive", "negative", "neutral", "mixed"}

# System prompt for post analysis
ANALYSIS_SYSTEM_PROMPT = """You are an expert market researcher analyzing Reddit posts to find business opportunities.

CRITICAL: Every insight MUST be grounded in the source text. Quotes must be copied VERBATIM from the post or a comment — do not paraphrase, summarize, or fabricate. If no direct quote supports an insight, set quote to null.

The POST AUTHOR line tells you who wrote the post. When the author is promoting, showcasing, or seeking feedback on their own product, focus on the *community response* (comments) rather than the author's claims. Commenter voices are independent market signals; the author's voice is marketing.

Return empty insights array if the post is purely self-promotional with no actionable community signal.

Extract actionable insights in these categories:
1. Pain points — Problems people are genuinely frustrated about. The frustration must come from someone *experiencing* the problem — not a founder claiming they solved a problem.
2. Solution requests — People actively looking for tools/products to solve a problem they have. Not founders looking for beta testers or feedback.
3. Product mentions — References to products by people who are NOT the product's creator. If the post author is promoting their own product, that is not a product mention — it's self-promotion. Only extract product mentions from commenters or third-party references.
4. Opportunities — Gaps identified by the community through complaints, requests, or unmet needs. A founder claiming "there was nothing that did X so I built it" is marketing, not a market signal.
5. Advice requests — People asking for guidance, tips, how-to help, resource recommendations
6. Ideas — People suggesting tools/products that should exist, or ways things could work
7. Money talk — Discussions about pricing, spending, willingness to pay, budget constraints

Be specific. Prefer quoting over summarizing."""

# Prompt template for analyzing a single post
ANALYZE_POST_PROMPT = """Analyze this Reddit post from r/{subreddit} and extract insights.

POST AUTHOR: u/{author}
POST FLAIR: {flair}

POST METADATA:
Score: {score} | Comments: {num_comments} | Upvote ratio: {upvote_ratio}

POST TITLE: {title}

POST BODY:
{body}

TOP COMMENTS:
{comments}

---

Extract insights in this exact JSON format:
{{
    "category": "pain_point" | "solution_request" | "product_mention" | "opportunity" | "advice_request" | "idea" | "money_talk" | "general",
    "insights": [
        {{
            "type": "pain_point" | "solution_request" | "product_mention" | "opportunity" | "advice_request" | "idea" | "money_talk",
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

{existing_themes_block}

Rules:
- theme_key: PREFER reusing an existing theme from the list above. Only create a new theme_key if none of the existing ones fit. New keys must be lowercase with underscores.
- intensity_score: 0-30 mild annoyance, 31-60 moderate frustration, 61-80 significant pain, 81-100 severe/urgent
- Only include product_name and sentiment for product_mention type
- Quote must be verbatim from the text
- Return empty insights array if nothing actionable found
- Maximum 5 insights per post

Return ONLY valid JSON, no other text."""


# Consolidation prompts
CONSOLIDATION_SYSTEM_PROMPT = """You are a data analyst consolidating topic labels. Your job is to find genuine semantic duplicates in a list of theme keys and group them under a single canonical name."""

CONSOLIDATION_PROMPT = """Below is a list of theme_keys with their occurrence counts:

{theme_list}

Find groups of theme_keys that are genuine semantic duplicates (e.g. "honest_marketing" and "honesty_in_marketing", or "pricing_frustration" and "price_frustration").

Return JSON in this exact format:
{{
    "groups": [
        {{
            "canonical": "the_best_key_to_keep",
            "members": ["the_best_key_to_keep", "duplicate_key_1", "duplicate_key_2"]
        }}
    ]
}}

Rules:
- Only group genuine semantic duplicates — do NOT merge merely related topics
- Each group must have 2 or more members
- "canonical" must be one of the members (prefer the highest-count or clearest name)
- A theme_key can only appear in one group
- If no duplicates exist, return {{"groups": []}}

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


class ThemeMergeGroup(BaseModel):
    """A group of duplicate theme_keys to merge."""
    canonical: str
    members: list[str]

    @field_validator("canonical")
    @classmethod
    def normalize_canonical(cls, v: str) -> str:
        v = v.lower().strip()
        v = re.sub(r"[\s\-]+", "_", v)
        v = re.sub(r"[^a-z0-9_]", "", v)
        return v[:100] if v else "unknown"


class ConsolidationOutput(BaseModel):
    """Validated LLM consolidation output."""
    groups: list[ThemeMergeGroup] = Field(default_factory=list)


def validate_llm_output(raw: dict) -> AnalysisOutput:
    """Validate and normalize LLM JSON output using Pydantic."""
    try:
        return AnalysisOutput(**raw)
    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"LLM output validation failed, returning empty: {e}")
        return AnalysisOutput()


def _validate_quote(quote: str, source_chunks: list[str], threshold: float = 0.7) -> bool:
    """Validate that a quote actually appears in the source text.

    Two-tier approach:
    1. Fast path: exact substring match (lowercased)
    2. Fuzzy path: SequenceMatcher longest match >= threshold of quote length
    """
    if not quote or not source_chunks:
        return False

    # Too short to meaningfully validate
    if len(quote) < 10:
        return True

    quote_lower = quote.lower()

    for chunk in source_chunks:
        if not chunk:
            continue
        chunk_lower = chunk.lower()

        # Fast path: exact substring
        if quote_lower in chunk_lower:
            return True

        # Fuzzy path: longest common substring
        matcher = difflib.SequenceMatcher(None, quote_lower, chunk_lower, autojunk=False)
        match = matcher.find_longest_match(0, len(quote_lower), 0, len(chunk_lower))
        if match.size >= len(quote_lower) * threshold:
            return True

    return False


class AnalyzerService:
    """Analyzes Reddit posts using LLM to extract insights."""

    def __init__(self):
        self._llm = None

    async def _get_llm(self):
        """Get or create LLM provider."""
        if self._llm is None:
            self._llm = await get_llm_provider()
        return self._llm

    async def _get_existing_themes(self, session: AsyncSession, subreddit: str) -> list[str]:
        """Get existing theme_keys relevant to this subreddit's context."""
        result = await session.execute(
            select(Insight.theme_key)
            .join(Post)
            .where(Post.subreddit == subreddit)
            .group_by(Insight.theme_key)
            .order_by(func.count(Insight.id).desc())
            .limit(30)
        )
        return [row[0] for row in result]

    async def analyze_post(
        self,
        session: AsyncSession,
        post: Post,
        include_comments: bool = True,
        existing_themes: Optional[list[str]] = None,
    ) -> list[Insight]:
        """
        Analyze a single post and extract insights.

        Uses savepoints for isolation so one post failure doesn't
        rollback the entire batch.
        """
        insights = []

        # Get comments if requested
        comments_text = ""
        top_comments = []
        reply_map: dict[str, Comment] = {}
        if include_comments:
            # Query 1: Top 15 top-level comments
            result = await session.execute(
                select(Comment)
                .where(and_(Comment.post_id == post.id, Comment.depth == 0))
                .order_by(Comment.score.desc())
                .limit(15)
            )
            top_comments = list(result.scalars().all())

            # Query 2: Best reply per high-score parent
            high_score_ids = [c.id for c in top_comments if c.score > 5]
            if high_score_ids:
                result = await session.execute(
                    select(Comment)
                    .where(and_(
                        Comment.post_id == post.id,
                        Comment.depth == 1,
                        Comment.parent_id.in_(high_score_ids),
                    ))
                    .order_by(Comment.score.desc())
                )
                all_replies = result.scalars().all()
                # Pick top 1 reply per parent
                for reply in all_replies:
                    if reply.parent_id not in reply_map:
                        reply_map[reply.parent_id] = reply

            # Format with threaded replies
            if top_comments:
                lines = []
                for c in top_comments:
                    op_tag = " [OP]" if c.author == post.author else ""
                    lines.append(f"[{c.author}]{op_tag} (score: {c.score}): {c.body[:800]}")
                    reply = reply_map.get(c.id)
                    if reply:
                        reply_op_tag = " [OP]" if reply.author == post.author else ""
                        lines.append(f"  \u21b3 [{reply.author}]{reply_op_tag} (score: {reply.score}): {reply.body[:800]}")
                    lines.append("")  # blank line between threads
                comments_text = "\n".join(lines)

        # Fetch existing themes if not provided
        if existing_themes is None:
            existing_themes = await self._get_existing_themes(session, post.subreddit)

        # Build existing themes block for prompt
        if existing_themes:
            themes_list = ", ".join(f'"{t}"' for t in existing_themes)
            existing_themes_block = f"EXISTING THEMES (reuse these when they fit, only create new ones if truly novel):\n{themes_list}"
        else:
            existing_themes_block = "No existing themes yet — create new theme_keys as needed (lowercase with underscores)."

        # Build prompt
        prompt = ANALYZE_POST_PROMPT.format(
            subreddit=post.subreddit,
            author=post.author or "[deleted]",
            flair=getattr(post, 'link_flair_text', None) or "(none)",
            score=post.score,
            num_comments=post.num_comments,
            upvote_ratio=f"{(post.upvote_ratio or 0) * 100:.0f}%",
            title=post.title,
            body=post.body[:4000] if post.body else "(no body text)",
            comments=comments_text or "(no comments)",
            existing_themes_block=existing_themes_block,
        )

        try:
            llm = await self._get_llm()

            # Track analysis timing
            start_time = time.time()
            raw_result = await llm.generate_json(prompt, system=ANALYSIS_SYSTEM_PROMPT)
            duration_ms = int((time.time() - start_time) * 1000)

            # Validate LLM output
            validated = validate_llm_output(raw_result)

            # Validate quotes against source text
            source_chunks = [post.title, post.body[:4000] if post.body else ""]
            source_chunks.extend(c.body[:800] for c in top_comments)
            source_chunks.extend(r.body[:800] for r in reply_map.values())
            for item in validated.insights:
                if item.quote and not _validate_quote(item.quote, source_chunks):
                    logger.debug(
                        f"Quote validation failed for post {post.id}: {item.quote[:80]!r}"
                    )
                    item.quote = None
                    item.quote_author = None

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
                            "subreddit": post.subreddit,
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
            # Only analyze posts from active (followed) audiences
            active_sub_names = (
                select(audience_subreddits.c.subreddit_name)
                .join(Audience, Audience.id == audience_subreddits.c.audience_id)
                .where(Audience.active == True)
                .distinct()
            )

            result = await session.execute(
                select(Post)
                .where(
                    and_(
                        Post.analyzed == False,
                        Post.score >= min_score,
                        Post.subreddit.in_(active_sub_names),
                    )
                )
                .order_by(Post.score.desc())
                .limit(limit)
            )
            posts = result.scalars().all()

            # Pre-fetch existing themes per subreddit (avoid redundant queries)
            themes_cache: dict[str, list[str]] = {}
            for post in posts:
                if post.subreddit not in themes_cache:
                    themes_cache[post.subreddit] = await self._get_existing_themes(session, post.subreddit)

            for post in posts:
                try:
                    # Use savepoint per post for isolation
                    async with session.begin_nested():
                        existing_themes = themes_cache.get(post.subreddit, [])
                        insights = await self.analyze_post(session, post, existing_themes=existing_themes)
                        # Accumulate newly created themes so subsequent posts can reuse them
                        for ins in insights:
                            if ins.theme_key and ins.theme_key not in existing_themes:
                                existing_themes.append(ins.theme_key)
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

    async def consolidate_themes(
        self,
        subreddit_names: Optional[list[str]] = None,
    ) -> dict:
        """Use LLM to find and merge semantically duplicate theme_keys."""
        from sqlalchemy import update, text

        async with async_session_maker() as session:
            # Fetch distinct theme_key counts, scoped to subreddits
            theme_query = (
                select(Insight.theme_key, func.count(Insight.id).label("cnt"))
                .group_by(Insight.theme_key)
                .order_by(func.count(Insight.id).desc())
            )
            if subreddit_names is not None:
                theme_query = theme_query.join(Post).where(Post.subreddit.in_(subreddit_names))
            result = await session.execute(theme_query)
            theme_rows = result.all()

            if len(theme_rows) < 2:
                return {"groups_merged": 0, "themes_before": len(theme_rows), "themes_after": len(theme_rows), "merges": []}

            themes_before = len(theme_rows)
            theme_counts = {row[0]: row[1] for row in theme_rows}

            # Format for LLM
            theme_list = "\n".join(f"{key} (count: {cnt})" for key, cnt in theme_counts.items())
            prompt = CONSOLIDATION_PROMPT.format(theme_list=theme_list)

            llm = await self._get_llm()
            raw_result = await llm.generate_json(prompt, system=CONSOLIDATION_SYSTEM_PROMPT)

            # Validate
            try:
                validated = ConsolidationOutput(**raw_result)
            except (ValueError, TypeError) as e:
                logger.warning(f"Consolidation output validation failed: {e}")
                return {"groups_merged": 0, "themes_before": themes_before, "themes_after": themes_before, "merges": []}

            # Apply merges
            merges = []
            merged_keys = set()
            for group in validated.groups:
                # Validate: 2+ members, canonical in members, all members exist
                if len(group.members) < 2:
                    continue
                if group.canonical not in group.members:
                    continue
                if not all(m in theme_counts for m in group.members):
                    continue
                # Skip if any member already merged
                if any(m in merged_keys for m in group.members):
                    continue

                old_keys = [m for m in group.members if m != group.canonical]
                merged_keys.update(old_keys)

                # Update insights: remap old keys to canonical
                if subreddit_names is not None:
                    # Scoped update: only remap insights whose post is in the audience subreddits
                    stmt = (
                        update(Insight)
                        .where(Insight.theme_key.in_(old_keys))
                        .where(Insight.post_id.in_(
                            select(Post.id).where(Post.subreddit.in_(subreddit_names))
                        ))
                        .values(theme_key=group.canonical)
                    )
                else:
                    stmt = (
                        update(Insight)
                        .where(Insight.theme_key.in_(old_keys))
                        .values(theme_key=group.canonical)
                    )
                await session.execute(stmt)
                merges.append({"canonical": group.canonical, "merged": old_keys})

            await session.commit()

        themes_after = themes_before - len(merged_keys)
        result = {
            "groups_merged": len(merges),
            "themes_before": themes_before,
            "themes_after": themes_after,
            "merges": merges,
        }
        logger.info(f"Theme consolidation: {result}")
        return result

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
        from sqlalchemy.orm import contains_eager

        query = select(Insight).join(Post).options(contains_eager(Insight.post))

        if subreddit_names is not None:
            query = query.where(Post.subreddit.in_(subreddit_names))

        # Apply sorting
        if sort_by == "engagement":
            query = query.order_by(Post.score.desc())
        elif sort_by == "intensity":
            query = query.order_by(Insight.intensity_score.desc().nullslast())
        elif sort_by == "date":
            query = query.order_by(Insight.created_at.desc())
        else:
            # Default: sort by post engagement (real community signal)
            query = query.order_by(Post.score.desc())

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
