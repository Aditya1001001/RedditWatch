"""Collection orchestration service."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.reddit import RedditCollector
from app.config import Config, get_config
from app.database import async_session_maker
from app.models import Comment, MonitoredSubreddit, Post

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

    async def collect_subreddit(
        self,
        session: AsyncSession,
        subreddit_name: str,
        include_comments: bool = True,
    ) -> dict:
        """
        Collect posts (and optionally comments) from a subreddit.

        Returns collection statistics.
        """
        stats = {
            "subreddit": subreddit_name,
            "posts_collected": 0,
            "posts_new": 0,
            "comments_collected": 0,
        }

        # Collect posts
        posts = await self.reddit.collect_posts(
            subreddit_name,
            limit=self.config.collection.posts_per_subreddit,
            sort=self.config.collection.sort_by,
        )

        for post in posts:
            # Check if post already exists
            existing = await session.get(Post, post.id)
            if existing:
                # Update score and comment count
                existing.score = post.score
                existing.num_comments = post.num_comments
                stats["posts_collected"] += 1
            else:
                # New post
                session.add(post)
                stats["posts_collected"] += 1
                stats["posts_new"] += 1

                # Collect comments for new posts
                if include_comments and self.config.collection.include_comments:
                    comments = await self.reddit.collect_comments(
                        post.id,
                        subreddit_name,
                        limit=self.config.collection.max_comments_per_post,
                    )
                    for comment in comments:
                        existing_comment = await session.get(Comment, comment.id)
                        if not existing_comment:
                            session.add(comment)
                            stats["comments_collected"] += 1

        # Update subreddit stats
        subreddit = await session.get(MonitoredSubreddit, subreddit_name)
        if subreddit:
            subreddit.last_collected = datetime.now(timezone.utc)
            subreddit.post_count += stats["posts_new"]

        await session.flush()

        logger.info(
            f"Collected from r/{subreddit_name}: "
            f"{stats['posts_new']} new posts, {stats['comments_collected']} comments"
        )

        return stats

    async def collect_all(self) -> dict:
        """
        Collect from all enabled subreddits.

        Returns aggregate statistics.
        """
        total_stats = {
            "subreddits_processed": 0,
            "posts_collected": 0,
            "posts_new": 0,
            "comments_collected": 0,
            "errors": [],
        }

        async with async_session_maker() as session:
            subreddits = await self.get_monitored_subreddits(session, enabled_only=True)

            for subreddit in subreddits:
                try:
                    stats = await self.collect_subreddit(
                        session,
                        subreddit.name,
                        include_comments=self.config.collection.include_comments,
                    )
                    total_stats["subreddits_processed"] += 1
                    total_stats["posts_collected"] += stats["posts_collected"]
                    total_stats["posts_new"] += stats["posts_new"]
                    total_stats["comments_collected"] += stats["comments_collected"]
                except Exception as e:
                    logger.error(f"Error collecting from r/{subreddit.name}: {e}")
                    total_stats["errors"].append({
                        "subreddit": subreddit.name,
                        "error": str(e),
                    })

            await session.commit()

        logger.info(
            f"Collection complete: {total_stats['subreddits_processed']} subreddits, "
            f"{total_stats['posts_new']} new posts"
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
