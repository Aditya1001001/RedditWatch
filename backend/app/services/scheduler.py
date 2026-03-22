"""Scheduled collection service using APScheduler."""

import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_config

logger = logging.getLogger(__name__)


class CollectionScheduler:
    """Manages scheduled Reddit data collection jobs."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._last_results: dict[str, dict] = {}

    @property
    def running(self) -> bool:
        return self.scheduler.running

    def setup_jobs(self) -> None:
        """Configure all scheduled jobs based on config."""
        config = get_config()
        interval = config.collection.interval_minutes

        # Job 1: Regular collection (hot + new, single page) — every interval_minutes
        self.scheduler.add_job(
            self._run_regular_collection,
            IntervalTrigger(minutes=interval),
            id="regular_collection",
            name="Regular collection (hot + new)",
            replace_existing=True,
        )

        # Job 2: Deep collection (all sort/time combos with pagination) — daily at 3 AM
        self.scheduler.add_job(
            self._run_deep_collection,
            CronTrigger(hour=3, minute=0),
            id="deep_collection",
            name="Deep collection (all sort modes)",
            replace_existing=True,
        )

        # Job 3: Comment refresh for high-engagement posts — every 2 hours
        self.scheduler.add_job(
            self._run_comment_refresh,
            IntervalTrigger(hours=2),
            id="comment_refresh",
            name="Comment refresh (high-engagement posts)",
            replace_existing=True,
        )

        # Job 4: Young post refresh (< 5 days old) — every 4 hours
        young_interval = config.collection.young_post_refresh_interval_hours
        self.scheduler.add_job(
            self._run_young_post_refresh,
            IntervalTrigger(hours=young_interval),
            id="young_post_refresh",
            name="Young post refresh (< 5 days old)",
            replace_existing=True,
        )

        # Job 5: Auto-analysis safety net — every 30 minutes
        if config.analysis.auto_analyze:
            self.scheduler.add_job(
                self._maybe_run_analysis,
                IntervalTrigger(minutes=30),
                id="auto_analysis",
                name="Auto-analysis (safety net)",
                replace_existing=True,
            )

        logger.info(
            f"Scheduler configured: regular every {interval}min, "
            f"deep daily at 3AM, comment refresh every 2h, "
            f"young post refresh every {young_interval}h"
        )

    async def _run_regular_collection(self) -> None:
        """Run a regular (non-deep) collection."""
        from app.services.collector import get_collector

        logger.info("Scheduler: starting regular collection")
        try:
            collector = get_collector()
            result = await collector.collect_all(deep=False)
            self._last_results["regular_collection"] = {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                **result,
            }
            logger.info(
                f"Scheduler: regular collection done — "
                f"{result['posts_new']} new posts from {result['subreddits_processed']} subs"
            )
            await self._maybe_run_analysis()
        except Exception as e:
            logger.error(f"Scheduler: regular collection failed: {e}")
            self._last_results["regular_collection"] = {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
            }

    async def _run_deep_collection(self) -> None:
        """Run a deep (multi-sort, paginated) collection."""
        from app.services.collector import get_collector

        logger.info("Scheduler: starting deep collection")
        try:
            collector = get_collector()
            result = await collector.collect_all(deep=True)
            self._last_results["deep_collection"] = {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                **result,
            }
            logger.info(
                f"Scheduler: deep collection done — "
                f"{result['posts_new']} new posts from {result['subreddits_processed']} subs"
            )
            await self._maybe_run_analysis()
        except Exception as e:
            logger.error(f"Scheduler: deep collection failed: {e}")
            self._last_results["deep_collection"] = {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
            }

    async def _run_comment_refresh(self) -> None:
        """Refresh comments for high-engagement posts."""
        from app.services.collector import get_collector

        logger.info("Scheduler: starting comment refresh")
        try:
            collector = get_collector()
            result = await collector.refresh_hot_conversations(
                min_score=10, min_comments=5, limit=20
            )
            self._last_results["comment_refresh"] = {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                **result,
            }
            logger.info(
                f"Scheduler: comment refresh done — "
                f"{result['comments_new']} new comments from {result['posts_refreshed']} posts"
            )
        except Exception as e:
            logger.error(f"Scheduler: comment refresh failed: {e}")
            self._last_results["comment_refresh"] = {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
            }

    async def _maybe_run_analysis(self) -> None:
        """Trigger analysis if auto_analyze is enabled and no analysis is already running."""
        config = get_config()
        if not config.analysis.auto_analyze:
            return

        from app.services.tasks import get_task_tracker

        tracker = get_task_tracker()
        if tracker.get_active_task("analysis"):
            logger.debug("Scheduler: analysis already running, skipping")
            return

        from app.services.analyzer import get_analyzer

        logger.info("Scheduler: starting auto-analysis")
        try:
            task_info = tracker.create_task("analysis")
            analyzer = get_analyzer()

            async def _run():
                return await analyzer.analyze_unanalyzed_posts(
                    limit=config.analysis.batch_size,
                    min_score=config.analysis.min_score_threshold,
                )

            tracker.run_background(task_info, _run())
        except Exception as e:
            logger.error(f"Scheduler: auto-analysis failed to start: {e}")

    async def _run_young_post_refresh(self) -> None:
        """Refresh engagement data for posts less than 5 days old."""
        from app.services.collector import get_collector

        logger.info("Scheduler: starting young post refresh")
        try:
            collector = get_collector()
            result = await collector.refresh_young_posts()
            self._last_results["young_post_refresh"] = {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                **result,
            }
            logger.info(
                f"Scheduler: young post refresh done — "
                f"{result['posts_updated']} updated out of {result['posts_checked']} checked"
            )
        except Exception as e:
            logger.error(f"Scheduler: young post refresh failed: {e}")
            self._last_results["young_post_refresh"] = {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
            }

    def start(self) -> None:
        """Start the scheduler."""
        if not self.scheduler.running:
            self.setup_jobs()
            self.scheduler.start()
            logger.info("Collection scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Collection scheduler stopped")

    def trigger_job(self, job_id: str) -> bool:
        """Manually trigger a specific job. Returns True if job was found."""
        job = self.scheduler.get_job(job_id)
        if job is None:
            return False
        job.modify(next_run_time=datetime.now(timezone.utc))
        logger.info(f"Manually triggered job: {job_id}")
        return True

    def get_job_summaries(self) -> list[dict]:
        """Get summary info for all scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run.isoformat() if next_run else None,
                "last_result": self._last_results.get(job.id),
            })
        return jobs

    def get_status(self) -> dict:
        """Get full scheduler status."""
        return {
            "running": self.scheduler.running,
            "jobs": self.get_job_summaries(),
        }


# Global scheduler instance
_scheduler: Optional[CollectionScheduler] = None


def get_scheduler() -> CollectionScheduler:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = CollectionScheduler()
    return _scheduler


async def shutdown_scheduler() -> None:
    """Shutdown the global scheduler."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.stop()
        _scheduler = None
