"""Global token-bucket rate limiter for Reddit HTTP requests."""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token-bucket rate limiter.

    All Reddit HTTP requests must call ``await acquire()`` before firing.
    A single global instance is shared across the entire application so that
    concurrency level is irrelevant — requests are serialised at the bucket.

    The bucket also accepts feedback from Reddit's ``X-Ratelimit-*`` response
    headers via ``update_from_headers()`` for adaptive throttling.
    """

    def __init__(self, rpm: float = 8.0, burst: int = 10):
        """
        Args:
            rpm: Sustained requests per minute (token refill rate).
            burst: Maximum tokens in the bucket (allows short bursts).
        """
        self._rpm = rpm
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

        # Adaptive state fed by Reddit headers
        self._header_remaining: Optional[float] = None
        self._header_reset: Optional[float] = None  # monotonic time when window resets

        logger.info(f"Rate limiter initialised: {rpm} req/min, burst {burst}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def acquire(self) -> None:
        """Wait until a token is available, then consume one."""
        while True:
            async with self._lock:
                self._refill()

                # If Reddit headers say we're almost out, honour that
                if self._header_remaining is not None and self._header_remaining < 2:
                    wait = self._header_reset_wait()
                    if wait > 0:
                        logger.info(
                            f"Rate limiter: Reddit header says {self._header_remaining} "
                            f"remaining, pausing {wait:.1f}s"
                        )
                        # Fall through to sleep *outside* the lock
                    else:
                        # Reset already passed — clear stale header state
                        self._header_remaining = None
                        if self._tokens >= 1:
                            self._tokens -= 1
                            return
                        wait = (1 - self._tokens) / (self._rpm / 60.0)
                elif self._tokens >= 1:
                    self._tokens -= 1
                    return
                else:
                    # Calculate wait time for next token
                    wait = (1 - self._tokens) / (self._rpm / 60.0)

            # Sleep outside lock so other coroutines aren't blocked
            logger.debug(f"Rate limiter: waiting {wait:.1f}s")
            await asyncio.sleep(wait)

    def update_from_headers(self, headers: dict) -> None:
        """
        Feed Reddit's rate-limit response headers back into the limiter.

        Reddit sends:
          - X-Ratelimit-Remaining: requests left in current window
          - X-Ratelimit-Reset: seconds until window resets
          - X-Ratelimit-Used: requests used in current window
        """
        remaining = headers.get("x-ratelimit-remaining")
        reset = headers.get("x-ratelimit-reset")
        used = headers.get("x-ratelimit-used")

        if remaining is not None:
            try:
                self._header_remaining = float(remaining)
            except (ValueError, TypeError):
                self._header_remaining = None

        if reset is not None:
            try:
                self._header_reset = time.monotonic() + float(reset)
            except (ValueError, TypeError):
                self._header_reset = None

        if remaining is not None or used is not None:
            logger.debug(
                f"Rate limit headers: remaining={remaining}, "
                f"reset={reset}s, used={used}"
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _refill(self) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        new_tokens = elapsed * (self._rpm / 60.0)
        self._tokens = min(self._tokens + new_tokens, float(self._burst))
        self._last_refill = now

    def _header_reset_wait(self) -> float:
        """Seconds until the Reddit rate-limit window resets."""
        if self._header_reset is None:
            return 0
        return max(0, self._header_reset - time.monotonic())


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_instance: Optional[RateLimiter] = None


def get_rate_limiter(rpm: float = 8.0, burst: int = 10) -> RateLimiter:
    """Return (or create) the global rate limiter singleton."""
    global _instance
    if _instance is None:
        _instance = RateLimiter(rpm=rpm, burst=burst)
    return _instance


def reset_rate_limiter() -> None:
    """Reset the singleton (for testing / reconfiguration)."""
    global _instance
    _instance = None
