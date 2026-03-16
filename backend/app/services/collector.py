"""Collection orchestration service."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import func as sa_func

from app.collectors.reddit import RedditCollector
from app.config import Config, get_config
from app.database import async_session_maker
from app.models import Comment, MonitoredSubreddit, Post, SubscriberSnapshot

logger = logging.getLogger(__name__)


class CollectorService:
    """Orchestrates Reddit data collection."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
        self.reddit = RedditCollector()
        self._catalog: Optional[dict] = None

    async def close(self):
        """Clean up resources."""
        await self.reddit.close()

    def load_subreddit_catalog(self) -> dict:
        """Load the curated subreddit catalog."""
        if self._catalog is not None:
            return self._catalog

        catalog_path = Path(__file__).parent.parent / "data" / "subreddits.yaml"
        if catalog_path.exists():
            with open(catalog_path) as f:
                self._catalog = yaml.safe_load(f) or {}
        else:
            self._catalog = {}

        return self._catalog

    def get_catalog_flat(self) -> list[dict]:
        """Get flattened catalog with category info."""
        catalog = self.load_subreddit_catalog()
        result = []

        for category, subreddits in catalog.items():
            for sub in subreddits:
                result.append({
                    **sub,
                    "category": category,
                })

        return result

    async def test_reddit_connection(self) -> dict:
        """Test Reddit API connection."""
        return await self.reddit.test_connection()

    async def add_subreddit(
        self,
        session: AsyncSession,
        name: str,
        category: Optional[str] = None,
    ) -> MonitoredSubreddit:
        """
        Add a subreddit to monitor.

        Fetches subreddit info from Reddit and creates DB record.
        """
        # Normalize name (remove r/ prefix if present)
        name = name.lower().replace("r/", "").strip()

        # Check if already exists
        existing = await session.get(MonitoredSubreddit, name)
        if existing:
            logger.info(f"Subreddit r/{name} already being monitored")
            return existing

        # Get info from Reddit
        info = await self.reddit.get_subreddit_info(name)
        if not info:
            raise ValueError(f"Subreddit r/{name} not found or not accessible")

        # Create record
        subreddit = MonitoredSubreddit(
            name=name,
            display_name=info["display_name"],
            description=info["description"],
            subscribers=info["subscribers"],
            category=category,
            enabled=True,
        )

        session.add(subreddit)
        await session.flush()

        logger.info(f"Added subreddit r/{name} to monitoring")
        return subreddit

    async def remove_subreddit(
        self,
        session: AsyncSession,
        name: str,
    ) -> bool:
        """Remove a subreddit from monitoring."""
        name = name.lower().replace("r/", "").strip()

        subreddit = await session.get(MonitoredSubreddit, name)
        if subreddit:
            await session.delete(subreddit)
            logger.info(f"Removed subreddit r/{name} from monitoring")
            return True

        return False

    async def toggle_subreddit(
        self,
        session: AsyncSession,
        name: str,
        enabled: bool,
    ) -> Optional[MonitoredSubreddit]:
        """Enable or disable a subreddit."""
        name = name.lower().replace("r/", "").strip()

        subreddit = await session.get(MonitoredSubreddit, name)
        if subreddit:
            subreddit.enabled = enabled
            await session.flush()
            logger.info(f"{'Enabled' if enabled else 'Disabled'} subreddit r/{name}")

        return subreddit

    async def get_monitored_subreddits(
        self,
        session: AsyncSession,
        enabled_only: bool = False,
    ) -> list[MonitoredSubreddit]:
        """Get all monitored subreddits."""
        query = select(MonitoredSubreddit)
        if enabled_only:
            query = query.where(MonitoredSubreddit.enabled == True)
        query = query.order_by(MonitoredSubreddit.name)

        result = await session.execute(query)
        return list(result.scalars().all())

    async def _save_posts_to_db(
        self,
        session: AsyncSession,
        subreddit_name: str,
        posts: list[Post],
        include_comments: bool = True,
    ) -> dict:
        """
        Save a list of posts to the database, deduplicating and optionally fetching comments.

        Returns collection statistics.
        """
        stats = {
            "subreddit": subreddit_name,
            "posts_collected": 0,
            "posts_new": 0,
            "comments_collected": 0,
        }

        comment_min_score = self.config.collection.comment_min_score

        for post in posts:
            existing = await session.get(Post, post.id)
            if existing:
                existing.score = post.score
                existing.num_comments = post.num_comments
                stats["posts_collected"] += 1
            else:
                session.add(post)
                stats["posts_collected"] += 1
                stats["posts_new"] += 1

                # Only fetch comments for posts above the min score threshold
                if (
                    include_comments
                    and self.config.collection.include_comments
                    and post.score >= comment_min_score
                ):
                    comments = await self.reddit.collect_comments(
                        post.id,
                        subreddit_name,
                        limit=self.config.collection.max_comments_per_post,
                        max_depth=self.config.collection.max_comment_depth,
                        include_nested=True,
                    )
                    for comment in comments:
                        existing_comment = await session.get(Comment, comment.id)
                        if not existing_comment:
                            session.add(comment)
                            stats["comments_collected"] += 1

        # Update subreddit metadata
        subreddit = await session.get(MonitoredSubreddit, subreddit_name)
        if subreddit:
            subreddit.last_collected = datetime.now(timezone.utc)
            subreddit.post_count += stats["posts_new"]

        await session.flush()
        return stats

    async def _record_subscriber_snapshot(
        self,
        session: AsyncSession,
        subreddit_name: str,
    ) -> None:
        """Record a subscriber count snapshot for growth tracking.

        Fetches current subscriber count from Reddit, updates the
        MonitoredSubreddit record, and inserts a SubscriberSnapshot
        (skipping if same count already recorded today).
        """
        try:
            info = await self.reddit.get_subreddit_info(subreddit_name)
            if not info or not info.get("subscribers"):
                return

            count = info["subscribers"]

            # Update MonitoredSubreddit with latest count
            subreddit = await session.get(MonitoredSubreddit, subreddit_name)
            if subreddit:
                subreddit.subscribers = count

            # Check if we already have a snapshot with this count today
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            existing = await session.execute(
                select(SubscriberSnapshot)
                .where(SubscriberSnapshot.subreddit_name == subreddit_name)
                .where(SubscriberSnapshot.recorded_at >= today_start)
                .where(SubscriberSnapshot.subscriber_count == count)
            )
            if existing.scalar_one_or_none():
                return

            snapshot = SubscriberSnapshot(
                subreddit_name=subreddit_name,
                subscriber_count=count,
            )
            session.add(snapshot)
            await session.flush()
            logger.debug(f"Recorded subscriber snapshot for r/{subreddit_name}: {count}")
        except Exception as e:
            logger.warning(f"Failed to record subscriber snapshot for r/{subreddit_name}: {e}")

    async def collect_subreddit(
        self,
        session: AsyncSession,
        subreddit_name: str,
        include_comments: bool = True,
    ) -> dict:
        """
        Collect posts (and optionally comments) from a subreddit (single sort, single page).

        Returns collection statistics.
        """
        posts = await self.reddit.collect_posts(
            subreddit_name,
            limit=self.config.collection.posts_per_subreddit,
            sort=self.config.collection.sort_by,
        )

        if not posts:
            logger.warning(f"No posts returned for r/{subreddit_name} - possible rate limit")
            return {
                "subreddit": subreddit_name,
                "posts_collected": 0,
                "posts_new": 0,
                "comments_collected": 0,
            }

        stats = await self._save_posts_to_db(
            session, subreddit_name, posts, include_comments
        )

        # Record subscriber count snapshot for growth tracking
        await self._record_subscriber_snapshot(session, subreddit_name)

        logger.info(
            f"Collected from r/{subreddit_name}: "
            f"{stats['posts_new']} new posts, {stats['comments_collected']} comments"
        )
        return stats

    async def collect_subreddit_deep(
        self,
        session: AsyncSession,
        subreddit_name: str,
        include_comments: bool = True,
    ) -> dict:
        """
        Deep collect from a subreddit using multiple sort/time combos with pagination.

        Returns collection statistics.
        """
        posts = await self.reddit.collect_posts_deep(
            subreddit_name,
            sort_configs=self.config.collection.sort_modes,
            max_pages=self.config.collection.max_pages_per_sort,
            rate_limit_delay=self.config.collection.rate_limit_delay,
        )

        if not posts:
            logger.warning(f"No posts returned for deep collect r/{subreddit_name}")
            return {
                "subreddit": subreddit_name,
                "posts_collected": 0,
                "posts_new": 0,
                "comments_collected": 0,
            }

        stats = await self._save_posts_to_db(
            session, subreddit_name, posts, include_comments
        )

        # Record subscriber count snapshot for growth tracking
        await self._record_subscriber_snapshot(session, subreddit_name)

        logger.info(
            f"Deep collected from r/{subreddit_name}: "
            f"{stats['posts_new']} new posts, {stats['comments_collected']} comments"
        )
        return stats

    async def collect_all(self, deep: bool = False) -> dict:
        """
        Collect from all enabled subreddits with bounded concurrency.

        Args:
            deep: If True, use multi-sort paginated collection

        Returns aggregate statistics.
        """
        total_stats = {
            "subreddits_processed": 0,
            "posts_collected": 0,
            "posts_new": 0,
            "comments_collected": 0,
            "errors": [],
        }

        semaphore = asyncio.Semaphore(self.config.collection.concurrent_subreddits)

        async def _collect_one(subreddit_name: str) -> Optional[dict]:
            async with semaphore:
                try:
                    async with async_session_maker() as session:
                        if deep:
                            stats = await self.collect_subreddit_deep(
                                session,
                                subreddit_name,
                                include_comments=self.config.collection.include_comments,
                            )
                        else:
                            stats = await self.collect_subreddit(
                                session,
                                subreddit_name,
                                include_comments=self.config.collection.include_comments,
                            )
                        await session.commit()
                        return stats
                except Exception as e:
                    logger.error(f"Error collecting from r/{subreddit_name}: {e}")
                    return {"error": subreddit_name, "message": str(e)}

        async with async_session_maker() as session:
            subreddits = await self.get_monitored_subreddits(session, enabled_only=True)

        tasks = [_collect_one(sub.name) for sub in subreddits]
        results = await asyncio.gather(*tasks)

        for result in results:
            if result is None:
                continue
            if "error" in result:
                total_stats["errors"].append({
                    "subreddit": result["error"],
                    "error": result["message"],
                })
            else:
                total_stats["subreddits_processed"] += 1
                total_stats["posts_collected"] += result["posts_collected"]
                total_stats["posts_new"] += result["posts_new"]
                total_stats["comments_collected"] += result["comments_collected"]

        logger.info(
            f"Collection complete: {total_stats['subreddits_processed']} subreddits, "
            f"{total_stats['posts_new']} new posts"
        )

        return total_stats

    async def seed_collection(self) -> dict:
        """
        One-time deep scrape of all monitored subreddits.

        Uses all configured sort modes with pagination to build initial dataset.
        Returns aggregate statistics.
        """
        logger.info("Starting seed collection (deep scrape of all subreddits)...")
        return await self.collect_all(deep=True)

    async def refresh_comments(
        self,
        session: AsyncSession,
        post_id: str,
        subreddit_name: str,
    ) -> dict:
        """
        Refresh comments for an existing post.

        Re-fetches all comments including nested replies, updates existing
        comments' scores, and adds any new comments.

        Returns refresh statistics.
        """
        stats = {
            "post_id": post_id,
            "comments_updated": 0,
            "comments_new": 0,
            "comments_total": 0,
        }

        # Fetch fresh comments from Reddit
        comments = await self.reddit.collect_comments(
            post_id,
            subreddit_name,
            limit=self.config.collection.max_comments_per_post,
            max_depth=self.config.collection.max_comment_depth,
            include_nested=True,
        )

        stats["comments_total"] = len(comments)

        for comment in comments:
            existing = await session.get(Comment, comment.id)
            if existing:
                # Update score (engagement may have changed)
                if existing.score != comment.score:
                    existing.score = comment.score
                    stats["comments_updated"] += 1
            else:
                # New comment
                session.add(comment)
                stats["comments_new"] += 1

        await session.flush()

        logger.info(
            f"Refreshed comments for post {post_id}: "
            f"{stats['comments_new']} new, {stats['comments_updated']} updated"
        )

        return stats

    async def refresh_hot_conversations(
        self,
        min_score: int = 10,
        min_comments: int = 5,
        limit: int = 10,
    ) -> dict:
        """
        Refresh comments for high-engagement posts.

        Targets posts with high scores/comment counts that may have
        valuable new replies since initial collection.

        Args:
            min_score: Minimum post score to consider
            min_comments: Minimum comment count to consider
            limit: Maximum number of posts to refresh

        Returns:
            Aggregate refresh statistics
        """
        total_stats = {
            "posts_refreshed": 0,
            "comments_new": 0,
            "comments_updated": 0,
            "errors": [],
        }

        async with async_session_maker() as session:
            # Find high-engagement posts
            query = (
                select(Post)
                .where(Post.score >= min_score)
                .where(Post.num_comments >= min_comments)
                .order_by(Post.score.desc())
                .limit(limit)
            )
            result = await session.execute(query)
            posts = result.scalars().all()

            for post in posts:
                try:
                    stats = await self.refresh_comments(
                        session,
                        post.id,
                        post.subreddit,
                    )
                    total_stats["posts_refreshed"] += 1
                    total_stats["comments_new"] += stats["comments_new"]
                    total_stats["comments_updated"] += stats["comments_updated"]
                except Exception as e:
                    logger.error(f"Error refreshing comments for {post.id}: {e}")
                    total_stats["errors"].append({
                        "post_id": post.id,
                        "error": str(e),
                    })

            await session.commit()

        logger.info(
            f"Refreshed {total_stats['posts_refreshed']} hot conversations: "
            f"{total_stats['comments_new']} new comments"
        )

        return total_stats


# Global collector instance
_collector: Optional[CollectorService] = None


def get_collector() -> CollectorService:
    """Get the global collector service."""
    global _collector
    if _collector is None:
        _collector = CollectorService()
    return _collector


async def shutdown_collector():
    """Shutdown the global collector."""
    global _collector
    if _collector is not None:
        await _collector.close()
        _collector = None
