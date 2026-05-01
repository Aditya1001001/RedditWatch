"""Reddit data collector using HTTP requests (no API key required)."""

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree

import httpx

from app.collectors.arctic_shift import ArcticShiftCollector
from app.models import Comment, Post
from app.services.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

# User agents to rotate (helps avoid rate limiting)
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]


class RedditCollector:
    """
    Collects posts and comments from Reddit using HTTP requests.

    Uses old.reddit.com JSON endpoints which don't require API authentication.
    Falls back to RSS feeds or HTML scraping if rate limited.
    """

    def __init__(self, rate_limit_rpm: float = 8.0):
        self.base_url = "https://old.reddit.com"
        self.timeout = 30.0
        self._client: Optional[httpx.AsyncClient] = None
        self._rate_limiter = get_rate_limiter(rpm=rate_limit_rpm)
        self._arctic = ArcticShiftCollector()

    def _get_headers(self) -> dict:
        """Get request headers with random user agent."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/html",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
        await self._arctic.close()

    async def _request(self, url: str, params: Optional[dict] = None) -> httpx.Response:
        """
        Send a rate-limited GET request and feed response headers back.

        Raises httpx exceptions on network errors.
        """
        await self._rate_limiter.acquire()
        client = await self._get_client()
        response = await client.get(url, params=params, headers=self._get_headers())
        self._rate_limiter.update_from_headers(dict(response.headers))
        return response

    async def test_connection(self) -> dict:
        """Test if we can reach Reddit."""
        try:
            response = await self._request(
                f"{self.base_url}/r/test.json",
                params={"limit": 1},
            )

            if response.status_code == 200:
                return {"success": True, "message": "Reddit connection successful"}
            elif response.status_code == 429:
                return {"success": False, "message": "Rate limited - try again later"}
            else:
                return {"success": False, "message": f"HTTP {response.status_code}"}

        except Exception as e:
            return {"success": False, "message": f"Connection failed: {str(e)}"}

    async def get_subreddit_info(self, subreddit_name: str) -> Optional[dict]:
        """Get information about a subreddit."""
        try:
            response = await self._request(
                f"{self.base_url}/r/{subreddit_name}/about.json",
            )

            if response.status_code != 200:
                logger.error(f"Failed to get subreddit info: HTTP {response.status_code}")
                return None

            data = response.json()
            sub_data = data.get("data", {})

            # Extract icon URL: prefer community_icon, fall back to icon_img
            icon_url = None
            community_icon = sub_data.get("community_icon") or ""
            # community_icon often has query params appended after the URL
            if community_icon:
                icon_url = community_icon.split("?")[0]
            if not icon_url:
                icon_url = sub_data.get("icon_img") or None

            return {
                "name": sub_data.get("display_name", subreddit_name),
                "display_name": f"r/{sub_data.get('display_name', subreddit_name)}",
                "description": (sub_data.get("public_description") or "")[:500],
                "subscribers": sub_data.get("subscribers", 0),
                "icon_url": icon_url,
                "created_utc": datetime.fromtimestamp(
                    sub_data.get("created_utc", 0), tz=timezone.utc
                ) if sub_data.get("created_utc") else None,
            }

        except Exception as e:
            logger.error(f"Failed to get subreddit info for r/{subreddit_name}: {e}")
            return None

    async def search_subreddits(self, query: str, limit: int = 25) -> list[dict]:
        """Search for subreddits by name/topic via Reddit's search API."""
        try:
            response = await self._request(
                f"{self.base_url}/subreddits/search.json",
                params={"q": query, "limit": limit, "include_over_18": "false"},
            )

            if response.status_code != 200:
                logger.error(f"Subreddit search failed: HTTP {response.status_code}")
                return []

            data = response.json()
            results = []
            for item in data.get("data", {}).get("children", []):
                sub_data = item.get("data", {})
                icon_url = None
                community_icon = sub_data.get("community_icon") or ""
                if community_icon:
                    icon_url = community_icon.split("?")[0]
                if not icon_url:
                    icon_url = sub_data.get("icon_img") or None

                results.append({
                    "name": sub_data.get("display_name", ""),
                    "display_name": f"r/{sub_data.get('display_name', '')}",
                    "description": (sub_data.get("public_description") or "")[:500],
                    "subscribers": sub_data.get("subscribers", 0),
                    "icon_url": icon_url,
                })

            return results

        except Exception as e:
            logger.error(f"Subreddit search failed for query '{query}': {e}")
            return []

    async def fetch_popular_subreddits(
        self, max_pages: int = 10, per_page: int = 100
    ) -> list[dict]:
        """Fetch popular subreddits with pagination."""
        all_subs = []
        after_cursor = None

        for page in range(max_pages):
            params = {"limit": min(per_page, 100)}
            if after_cursor:
                params["after"] = after_cursor

            try:
                response = await self._request(
                    f"{self.base_url}/subreddits/popular.json",
                    params=params,
                )

                if response.status_code != 200:
                    logger.error(
                        f"Popular subreddits page {page + 1} failed: "
                        f"HTTP {response.status_code}"
                    )
                    break

                data = response.json()
                listing = data.get("data", {})
                after_cursor = listing.get("after")

                for item in listing.get("children", []):
                    sub_data = item.get("data", {})
                    icon_url = None
                    community_icon = sub_data.get("community_icon") or ""
                    if community_icon:
                        icon_url = community_icon.split("?")[0]
                    if not icon_url:
                        icon_url = sub_data.get("icon_img") or None

                    all_subs.append({
                        "name": sub_data.get("display_name", ""),
                        "display_name": f"r/{sub_data.get('display_name', '')}",
                        "description": (sub_data.get("public_description") or "")[:500],
                        "subscribers": sub_data.get("subscribers", 0),
                        "icon_url": icon_url,
                    })

                if not after_cursor:
                    break

            except Exception as e:
                logger.error(f"Popular subreddits page {page + 1} failed: {e}")
                break

        logger.info(f"Fetched {len(all_subs)} popular subreddits ({page + 1} pages)")
        return all_subs

    async def fetch_posts_by_id(self, post_ids: list[str]) -> list[Post]:
        """
        Fetch fresh metadata for posts by their IDs using Reddit's /by_id/ endpoint.

        Fetches up to 100 posts per API call. Useful for refreshing score,
        num_comments, and upvote_ratio on existing posts.

        Args:
            post_ids: List of Reddit post IDs (without t3_ prefix)

        Returns:
            List of Post model instances with current metadata
        """
        all_posts = []

        # Batch into groups of 100 (Reddit API limit)
        for i in range(0, len(post_ids), 100):
            batch = post_ids[i : i + 100]
            fullnames = ",".join(f"t3_{pid}" for pid in batch)
            url = f"{self.base_url}/by_id/{fullnames}.json"

            try:
                response = await self._request(url)

                if response.status_code == 429:
                    logger.warning("Rate limited on /by_id/ fetch")
                    continue

                if response.status_code != 200:
                    logger.error(f"HTTP {response.status_code} for /by_id/ fetch")
                    continue

                data = response.json()
                children = data.get("data", {}).get("children", [])

                for item in children:
                    if item.get("kind") != "t3":
                        continue
                    post_data = item.get("data", {})
                    # Extract subreddit from the post data itself
                    subreddit_name = post_data.get("subreddit", "")
                    post = self._parse_post(post_data, subreddit_name)
                    if post:
                        all_posts.append(post)

            except Exception as e:
                logger.error(f"/by_id/ fetch failed for batch starting at {i}: {e}")

        logger.info(f"Fetched {len(all_posts)} posts by ID ({len(post_ids)} requested)")
        return all_posts

    async def collect_posts(
        self,
        subreddit_name: str,
        limit: int = 25,
        sort: str = "hot",
        time_filter: Optional[str] = None,
    ) -> list[Post]:
        """
        Collect posts from a subreddit using JSON endpoint (single page).

        Args:
            subreddit_name: Name of subreddit (without r/)
            limit: Number of posts to fetch (max 100)
            sort: Sort method (hot, new, top, rising)
            time_filter: Time filter for "top" sort (hour, day, week, month, year, all)

        Returns:
            List of Post model instances
        """
        posts = []

        try:
            # Try JSON endpoint first
            posts = await self._collect_posts_json(subreddit_name, limit, sort, time_filter)

            if not posts:
                # Fall back to RSS if JSON fails
                logger.warning(f"JSON failed for r/{subreddit_name}, trying RSS")
                posts = await self._collect_posts_rss(subreddit_name, limit)

            if not posts:
                # Fall back to Arctic Shift if Reddit is fully blocked
                logger.warning(f"Reddit blocked for r/{subreddit_name}, trying Arctic Shift")
                posts = await self._arctic.collect_posts(subreddit_name, limit, sort, time_filter)

        except Exception as e:
            logger.error(f"Failed to collect posts from r/{subreddit_name}: {e}")

        return posts

    def _parse_post(self, post_data: dict, subreddit_name: str) -> Optional[Post]:
        """Parse a single post from Reddit JSON data. Returns None if post should be skipped."""
        # Skip stickied posts (usually mod announcements)
        if post_data.get("stickied", False):
            return None

        post_id = post_data.get("id", "")
        if not post_id:
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

    async def _collect_posts_json(
        self,
        subreddit_name: str,
        limit: int,
        sort: str,
        time_filter: Optional[str] = None,
    ) -> list[Post]:
        """Collect posts using JSON endpoint (single page)."""
        posts = []

        # Map sort to URL path
        sort_path = sort if sort in ["hot", "new", "top", "rising"] else "hot"
        url = f"{self.base_url}/r/{subreddit_name}/{sort_path}.json"

        params = {"limit": min(limit, 100)}
        if sort == "top":
            params["t"] = time_filter or "week"

        try:
            response = await self._request(url, params=params)

            if response.status_code == 429:
                logger.warning(f"Rate limited on r/{subreddit_name}")
                return []

            if response.status_code != 200:
                logger.error(f"HTTP {response.status_code} for r/{subreddit_name}")
                return []

            data = response.json()
            children = data.get("data", {}).get("children", [])

            for item in children:
                if item.get("kind") != "t3":  # t3 = post
                    continue
                post = self._parse_post(item.get("data", {}), subreddit_name)
                if post:
                    posts.append(post)

            logger.info(f"Collected {len(posts)} posts from r/{subreddit_name} (JSON)")

        except Exception as e:
            logger.error(f"JSON collection failed for r/{subreddit_name}: {e}")

        return posts

    async def collect_posts_paginated(
        self,
        subreddit_name: str,
        sort: str = "hot",
        time_filter: Optional[str] = None,
        max_pages: int = 10,
        per_page: int = 100,
        rate_limit_delay: float = 1.0,
        since_date: Optional[datetime] = None,
    ) -> list[Post]:
        """
        Collect posts with pagination, following Reddit's `after` cursor.

        Args:
            subreddit_name: Name of subreddit (without r/)
            sort: Sort method (hot, new, top, rising)
            time_filter: Time filter for "top" sort
            max_pages: Maximum number of pages to fetch
            per_page: Posts per page (max 100)
            rate_limit_delay: Base delay between requests (seconds)
            since_date: If set with sort="new", paginate until posts are older
                than this date (overrides max_pages with a 200-page cap)

        Returns:
            List of Post model instances (up to max_pages * per_page)
        """
        all_posts = []
        after_cursor = None

        sort_path = sort if sort in ["hot", "new", "top", "rising"] else "hot"
        url = f"{self.base_url}/r/{subreddit_name}/{sort_path}.json"

        # When since_date is set on "new" sort, allow many more pages
        effective_max_pages = max_pages
        if since_date and sort == "new":
            effective_max_pages = 200

        for page in range(effective_max_pages):
            params = {"limit": min(per_page, 100)}
            if sort == "top" and time_filter:
                params["t"] = time_filter
            if after_cursor:
                params["after"] = after_cursor

            try:
                # Rate limiter handles pacing — no manual delay needed
                response = await self._request(url, params=params)

                if response.status_code == 429:
                    logger.warning(
                        f"Rate limited on r/{subreddit_name} page {page + 1}, "
                        f"backing off"
                    )
                    await asyncio.sleep(rate_limit_delay * 2)
                    response = await self._request(url, params=params)
                    if response.status_code != 200:
                        logger.error(f"Still rate limited after backoff on r/{subreddit_name}")
                        break

                if response.status_code != 200:
                    logger.error(
                        f"HTTP {response.status_code} for r/{subreddit_name} page {page + 1}"
                    )
                    break

                data = response.json()
                listing = data.get("data", {})
                children = listing.get("children", [])
                after_cursor = listing.get("after")

                page_posts = []
                for item in children:
                    if item.get("kind") != "t3":
                        continue
                    post = self._parse_post(item.get("data", {}), subreddit_name)
                    if post:
                        page_posts.append(post)

                # Date-based filtering: stop when posts are older than cutoff
                if since_date and sort == "new":
                    before_filter = len(page_posts)
                    page_posts = [p for p in page_posts if p.created_utc >= since_date]
                    if len(page_posts) < before_filter:
                        all_posts.extend(page_posts)
                        logger.info(
                            f"Date cutoff reached for r/{subreddit_name} on page {page + 1}"
                        )
                        break

                all_posts.extend(page_posts)

                # No more pages
                if not after_cursor or not page_posts:
                    break

            except Exception as e:
                logger.error(
                    f"Pagination failed for r/{subreddit_name} page {page + 1}: {e}"
                )
                break

        logger.info(
            f"Paginated collection: {len(all_posts)} posts from "
            f"r/{subreddit_name}/{sort_path} ({page + 1} pages)"
        )
        return all_posts

    async def collect_posts_deep(
        self,
        subreddit_name: str,
        sort_configs: Optional[list[dict]] = None,
        max_pages: int = 5,
        per_page: int = 100,
        rate_limit_delay: float = 1.0,
        modes_per_run: int = 3,
        since_date: Optional[datetime] = None,
    ) -> list[Post]:
        """
        Collect posts using multiple sort/time combos, deduplicated by post ID.

        Uses ``modes_per_run`` to rotate through sort modes across days so that
        each run is cheaper but all modes are still exercised over time.

        Args:
            subreddit_name: Name of subreddit (without r/)
            sort_configs: List of dicts with 'sort' and optional 't' keys.
                Defaults to hot, new, top/week, top/month, top/year.
            max_pages: Max pages per sort/time combo
            per_page: Posts per page
            rate_limit_delay: Base delay between requests
            modes_per_run: How many sort modes to use this run (rotates daily)
            since_date: If set, passed to paginated collection for date-based stopping

        Returns:
            Deduplicated list of Post model instances
        """
        if sort_configs is None:
            sort_configs = [
                {"sort": "hot"},
                {"sort": "new"},
                {"sort": "top", "t": "week"},
                {"sort": "top", "t": "month"},
                {"sort": "top", "t": "year"},
            ]

        # Rotate sort modes across days so we cover all eventually
        if modes_per_run < len(sort_configs):
            from datetime import date
            day_index = date.today().toordinal() % len(sort_configs)
            # Always include hot + new, rotate the top/* variants
            always = [c for c in sort_configs if c.get("sort") in ("hot", "new")]
            rotating = [c for c in sort_configs if c not in always]
            # Pick rotating modes based on day
            slots = max(0, modes_per_run - len(always))
            if rotating and slots > 0:
                start = day_index % len(rotating)
                picked = []
                for i in range(slots):
                    picked.append(rotating[(start + i) % len(rotating)])
                sort_configs = always + picked
            else:
                sort_configs = always[:modes_per_run]

        seen_ids: set[str] = set()
        unique_posts: list[Post] = []

        for config in sort_configs:
            sort_mode = config.get("sort", "hot")
            time_filter = config.get("t")

            posts = await self.collect_posts_paginated(
                subreddit_name,
                sort=sort_mode,
                time_filter=time_filter,
                max_pages=max_pages,
                per_page=per_page,
                rate_limit_delay=rate_limit_delay,
                since_date=since_date,
            )

            new_count = 0
            for post in posts:
                if post.id not in seen_ids:
                    seen_ids.add(post.id)
                    unique_posts.append(post)
                    new_count += 1

            label = f"{sort_mode}/{time_filter}" if time_filter else sort_mode
            logger.info(
                f"Deep collect r/{subreddit_name} [{label}]: "
                f"{len(posts)} total, {new_count} new unique"
            )

        # Fall back to Arctic Shift if Reddit returned nothing (likely 403 blocked)
        if not unique_posts:
            logger.warning(f"Reddit blocked for deep collect r/{subreddit_name}, trying Arctic Shift")
            unique_posts = await self._arctic.collect_posts_deep(subreddit_name)

        logger.info(
            f"Deep collection complete for r/{subreddit_name}: "
            f"{len(unique_posts)} unique posts from {len(sort_configs)} sort modes"
        )
        return unique_posts

    async def _collect_posts_rss(
        self,
        subreddit_name: str,
        limit: int,
    ) -> list[Post]:
        """Collect posts using RSS feed (fallback method)."""
        posts = []

        url = f"https://www.reddit.com/r/{subreddit_name}/.rss"

        try:
            response = await self._request(url)

            if response.status_code != 200:
                return []

            # Parse Atom XML
            root = ElementTree.fromstring(response.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            entries = root.findall("atom:entry", ns)[:limit]

            for entry in entries:
                # Extract post ID from link
                link = entry.find("atom:link", ns)
                if link is None:
                    continue

                href = link.get("href", "")
                # Extract ID from URL like /r/SaaS/comments/abc123/...
                match = re.search(r"/comments/([a-z0-9]+)/", href)
                post_id = match.group(1) if match else ""

                if not post_id:
                    continue

                title_el = entry.find("atom:title", ns)
                author_el = entry.find("atom:author/atom:name", ns)
                updated_el = entry.find("atom:updated", ns)
                content_el = entry.find("atom:content", ns)

                # Parse date
                created_utc = None
                if updated_el is not None and updated_el.text:
                    try:
                        created_utc = datetime.fromisoformat(
                            updated_el.text.replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

                # Extract body from HTML content (simplified)
                body = None
                if content_el is not None and content_el.text:
                    # Strip HTML tags (basic)
                    body = re.sub(r"<[^>]+>", "", content_el.text)[:5000]

                post = Post(
                    id=post_id,
                    subreddit=subreddit_name.lower(),
                    title=title_el.text if title_el is not None else "",
                    body=body,
                    author=(author_el.text or "[deleted]").replace("/u/", "") if author_el is not None else "[deleted]",
                    score=0,  # RSS doesn't include scores
                    num_comments=0,
                    permalink=href.replace("https://www.reddit.com", ""),
                    created_utc=created_utc,
                )
                posts.append(post)

            logger.info(f"Collected {len(posts)} posts from r/{subreddit_name} (RSS)")

        except Exception as e:
            logger.error(f"RSS collection failed for r/{subreddit_name}: {e}")

        return posts

    def _extract_comments_recursive(
        self,
        children: list,
        post_id: str,
        depth: int = 0,
        max_depth: int = 5,
        limit: int = 100,
    ) -> list[Comment]:
        """
        Recursively extract comments from Reddit's nested structure.

        Args:
            children: List of comment children from Reddit API
            post_id: Reddit post ID
            depth: Current depth in comment tree
            max_depth: Maximum depth to traverse
            limit: Maximum total comments to extract

        Returns:
            Flat list of Comment model instances with depth info
        """
        comments = []

        for item in children:
            if len(comments) >= limit:
                break

            if item.get("kind") != "t1":  # t1 = comment
                continue

            comment_data = item.get("data", {})

            # Skip deleted/removed comments
            body = comment_data.get("body", "")
            if body in ["[deleted]", "[removed]", ""]:
                continue

            # Extract parent ID (remove prefix)
            parent_id = comment_data.get("parent_id", "")
            if parent_id.startswith("t1_"):
                parent_id = parent_id[3:]
            elif parent_id.startswith("t3_"):
                parent_id = parent_id[3:]

            comment = Comment(
                id=comment_data.get("id", ""),
                post_id=post_id,
                parent_id=parent_id,
                body=body,
                author=comment_data.get("author", "[deleted]"),
                score=comment_data.get("score", 0),
                depth=depth,
                created_utc=datetime.fromtimestamp(
                    comment_data.get("created_utc", 0), tz=timezone.utc
                ),
            )
            comments.append(comment)

            # Recursively get replies if within depth limit
            if depth < max_depth:
                replies = comment_data.get("replies")
                if replies and isinstance(replies, dict):
                    reply_children = replies.get("data", {}).get("children", [])
                    if reply_children:
                        nested_comments = self._extract_comments_recursive(
                            reply_children,
                            post_id,
                            depth=depth + 1,
                            max_depth=max_depth,
                            limit=limit - len(comments),
                        )
                        comments.extend(nested_comments)

        return comments

    async def collect_comments(
        self,
        post_id: str,
        subreddit_name: str,
        limit: int = 50,
        max_depth: int = 5,
        include_nested: bool = True,
    ) -> list[Comment]:
        """
        Collect comments for a post, including nested replies.

        Args:
            post_id: Reddit post ID
            subreddit_name: Name of subreddit
            limit: Maximum number of comments to fetch
            max_depth: Maximum depth of nested replies (0 = top-level only)
            include_nested: Whether to include nested replies

        Returns:
            List of Comment model instances with depth information
        """
        comments = []

        url = f"{self.base_url}/r/{subreddit_name}/comments/{post_id}.json"
        params = {"limit": limit, "sort": "top", "depth": max_depth + 1 if include_nested else 1}

        try:
            response = await self._request(url, params=params)

            if response.status_code == 429:
                logger.warning(f"Rate limited fetching comments for {post_id}")
                return []

            if response.status_code != 200:
                return []

            data = response.json()

            # Response is an array: [post, comments]
            if len(data) < 2:
                return []

            comment_listing = data[1].get("data", {}).get("children", [])

            if include_nested:
                # Recursively extract nested comments
                comments = self._extract_comments_recursive(
                    comment_listing,
                    post_id,
                    depth=0,
                    max_depth=max_depth,
                    limit=limit,
                )
            else:
                # Only top-level comments (old behavior)
                for item in comment_listing[:limit]:
                    if item.get("kind") != "t1":
                        continue

                    comment_data = item.get("data", {})
                    body = comment_data.get("body", "")
                    if body in ["[deleted]", "[removed]", ""]:
                        continue

                    parent_id = comment_data.get("parent_id", "")
                    if parent_id.startswith("t1_"):
                        parent_id = parent_id[3:]
                    elif parent_id.startswith("t3_"):
                        parent_id = parent_id[3:]

                    comment = Comment(
                        id=comment_data.get("id", ""),
                        post_id=post_id,
                        parent_id=parent_id,
                        body=body,
                        author=comment_data.get("author", "[deleted]"),
                        score=comment_data.get("score", 0),
                        depth=0,
                        created_utc=datetime.fromtimestamp(
                            comment_data.get("created_utc", 0), tz=timezone.utc
                        ),
                    )
                    comments.append(comment)

            nested_count = sum(1 for c in comments if c.depth > 0)
            logger.debug(
                f"Collected {len(comments)} comments for post {post_id} "
                f"({nested_count} nested, max depth {max(c.depth for c in comments) if comments else 0})"
            )

        except Exception as e:
            logger.error(f"Failed to collect comments for post {post_id}: {e}")

        return comments

    async def collect_with_delay(
        self,
        subreddit_name: str,
        limit: int = 25,
        sort: str = "hot",
        time_filter: Optional[str] = None,
        include_comments: bool = True,
        max_comments_per_post: int = 30,
        delay_seconds: float = 2.0,
        comment_min_score: int = 0,
    ) -> tuple[list[Post], list[Comment]]:
        """
        Collect posts and comments with rate limit protection.

        Args:
            subreddit_name: Name of subreddit
            limit: Number of posts to fetch
            sort: Sort method
            time_filter: Time filter for "top" sort
            include_comments: Whether to fetch comments
            max_comments_per_post: Max comments per post
            delay_seconds: Delay between requests
            comment_min_score: Only fetch comments for posts above this score

        Returns:
            Tuple of (posts, comments)
        """
        all_comments = []

        # Collect posts
        posts = await self.collect_posts(subreddit_name, limit, sort, time_filter)

        if include_comments and posts:
            # Collect comments for high-scoring posts (rate limiter handles pacing)
            for post in posts:
                if post.score < comment_min_score:
                    continue
                comments = await self.collect_comments(
                    post.id, subreddit_name, max_comments_per_post
                )
                all_comments.extend(comments)

        return posts, all_comments
