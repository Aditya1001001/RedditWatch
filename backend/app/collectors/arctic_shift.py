"""Arctic Shift fallback collector for when Reddit's API returns 403.

Uses the Arctic Shift archive API (arctic-shift.photon-reddit.com) which mirrors
Reddit posts in near-real-time. No API key required.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.models import Post

logger = logging.getLogger(__name__)

BASE_URL = "https://arctic-shift.photon-reddit.com/api"


class ArcticShiftCollector:
    """Collects posts from the Arctic Shift Reddit archive API."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self._client

    async def close(self):
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _parse_post(self, post_data: dict, subreddit_name: str) -> Optional[Post]:
        """Parse an Arctic Shift post into a Post model. Same fields as Reddit JSON."""
        if post_data.get("stickied", False):
            return None

        post_id = post_data.get("id", "")
        if not post_id:
            return None

        # Arctic Shift may have removed posts with empty selftext
        if post_data.get("removed_by_category"):
            return None

        return Post(
            id=post_id,
            subreddit=subreddit_name.lower(),
            title=post_data.get("title", ""),
            body=post_data.get("selftext") if post_data.get("is_self") else None,
            author=post_data.get("author", "[deleted]"),
            score=post_data.get("score", 0),
            upvote_ratio=post_data.get("upvote_ratio"),
            num_comments=post_data.get("num_comments", 0),
            permalink=post_data.get("permalink", ""),
            url=post_data.get("url") if not post_data.get("is_self") else None,
            link_flair_text=post_data.get("link_flair_text"),
            created_utc=datetime.fromtimestamp(
                post_data.get("created_utc", 0), tz=timezone.utc
            ),
        )

    async def collect_posts(
        self,
        subreddit_name: str,
        limit: int = 100,
        sort: str = "hot",
        time_filter: Optional[str] = None,
    ) -> list[Post]:
        """Collect recent posts from a subreddit via Arctic Shift.

        Arctic Shift's search API supports sorting by created_utc (newest first)
        and score. Maps Reddit sort modes as best we can.
        """
        client = await self._get_client()

        params = {
            "subreddit": subreddit_name,
            "limit": min(limit, 100),
        }

        if sort == "new":
            params["sort"] = "desc"
            params["sort_type"] = "created_utc"
        elif sort == "top":
            params["sort"] = "desc"
            params["sort_type"] = "score"
            # Map time_filter to after parameter
            if time_filter:
                now = datetime.now(timezone.utc)
                windows = {"hour": 1/24, "day": 1, "week": 7, "month": 30, "year": 365}
                days = windows.get(time_filter, 7)
                after_ts = int((now - timedelta(days=days)).timestamp())
                params["after"] = after_ts
        else:
            # "hot" / "rising" — just get recent high-score posts
            params["sort"] = "desc"
            params["sort_type"] = "score"
            after_ts = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
            params["after"] = after_ts

        try:
            response = await client.get(f"{BASE_URL}/posts/search", params=params)
            if response.status_code != 200:
                logger.error(f"Arctic Shift HTTP {response.status_code} for r/{subreddit_name}")
                return []

            data = response.json()
            posts = []
            for item in data.get("data", []):
                post = self._parse_post(item, subreddit_name)
                if post:
                    posts.append(post)

            logger.info(f"Arctic Shift: {len(posts)} posts from r/{subreddit_name} ({sort})")
            return posts

        except Exception as e:
            logger.error(f"Arctic Shift collection failed for r/{subreddit_name}: {e}")
            return []

    async def collect_posts_deep(
        self,
        subreddit_name: str,
        limit: int = 500,
        since_days: int = 30,
    ) -> list[Post]:
        """Deep collect using Arctic Shift pagination.

        Fetches up to `limit` posts from the last `since_days` days,
        paginating with the `after` cursor.
        """
        client = await self._get_client()
        all_posts: list[Post] = []
        seen_ids: set[str] = set()

        after_ts = int((datetime.now(timezone.utc) - timedelta(days=since_days)).timestamp())
        per_page = 100
        pages = (limit + per_page - 1) // per_page

        # Collect newest first, then by score
        for sort_type in ["created_utc", "score"]:
            params = {
                "subreddit": subreddit_name,
                "limit": per_page,
                "sort": "desc",
                "sort_type": sort_type,
                "after": after_ts,
            }

            for page in range(pages):
                try:
                    response = await client.get(f"{BASE_URL}/posts/search", params=params)
                    if response.status_code != 200:
                        logger.error(f"Arctic Shift page {page + 1} HTTP {response.status_code}")
                        break

                    data = response.json()
                    items = data.get("data", [])
                    if not items:
                        break

                    new_count = 0
                    for item in items:
                        post = self._parse_post(item, subreddit_name)
                        if post and post.id not in seen_ids:
                            seen_ids.add(post.id)
                            all_posts.append(post)
                            new_count += 1

                    if new_count == 0:
                        break

                    # Use last post's created_utc as cursor for next page
                    last_ts = items[-1].get("created_utc", 0)
                    if sort_type == "created_utc":
                        params["before"] = last_ts
                    else:
                        break  # Score sort doesn't paginate cleanly

                    if len(all_posts) >= limit:
                        break

                except Exception as e:
                    logger.error(f"Arctic Shift deep page {page + 1} failed: {e}")
                    break

        logger.info(
            f"Arctic Shift deep: {len(all_posts)} posts from r/{subreddit_name} "
            f"(last {since_days} days)"
        )
        return all_posts[:limit]
