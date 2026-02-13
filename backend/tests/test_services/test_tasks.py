"""Tests for the task tracker service."""

import asyncio

import pytest
import pytest_asyncio

from app.services.tasks import TaskInfo, TaskStatus, TaskTracker


class TestTaskTracker:
    """Tests for the in-memory task tracker."""

    def test_create_task(self):
        tracker = TaskTracker()
        task = tracker.create_task("collection")
        assert task.task_id is not None
        assert task.task_type == "collection"
        assert task.status == TaskStatus.PENDING

    def test_get_task(self):
        tracker = TaskTracker()
        task = tracker.create_task("collection")
        found = tracker.get_task(task.task_id)
        assert found is task

    def test_get_missing_task_returns_none(self):
        tracker = TaskTracker()
        assert tracker.get_task("nonexistent") is None

    def test_get_tasks_by_type(self):
        tracker = TaskTracker()
        tracker.create_task("collection")
        tracker.create_task("collection")
        tracker.create_task("analysis")

        assert len(tracker.get_tasks_by_type("collection")) == 2
        assert len(tracker.get_tasks_by_type("analysis")) == 1

    def test_get_active_task(self):
        tracker = TaskTracker()
        task = tracker.create_task("collection")
        task.status = TaskStatus.RUNNING

        active = tracker.get_active_task("collection")
        assert active is task

    def test_no_active_task_when_all_completed(self):
        tracker = TaskTracker()
        task = tracker.create_task("collection")
        task.status = TaskStatus.COMPLETED

        assert tracker.get_active_task("collection") is None

    def test_to_dict(self):
        tracker = TaskTracker()
        task = tracker.create_task("collection")
        d = task.to_dict()
        assert d["task_id"] == task.task_id
        assert d["task_type"] == "collection"
        assert d["status"] == "pending"

    @pytest.mark.asyncio
    async def test_run_background_success(self):
        tracker = TaskTracker()
        task = tracker.create_task("test")

        async def work():
            return {"result": "ok"}

        tracker.run_background(task, work())
        # Wait for task to complete
        await asyncio.sleep(0.1)

        assert task.status == TaskStatus.COMPLETED
        assert task.result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_run_background_failure(self):
        tracker = TaskTracker()
        task = tracker.create_task("test")

        async def failing_work():
            raise ValueError("something broke")

        tracker.run_background(task, failing_work())
        await asyncio.sleep(0.1)

        assert task.status == TaskStatus.FAILED
        assert "something broke" in task.error

    def test_cleanup_old_tasks(self):
        tracker = TaskTracker(max_completed=2)
        from datetime import datetime, timezone

        for i in range(5):
            task = tracker.create_task("test")
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime(2026, 1, 1, i, tzinfo=timezone.utc)

        # Force cleanup
        tracker._cleanup_old()
        completed = [t for t in tracker._tasks.values() if t.status == TaskStatus.COMPLETED]
        assert len(completed) <= 2
