"""In-memory task status tracking for background operations."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskInfo:
    """Represents a tracked background task."""

    __slots__ = (
        "task_id", "task_type", "status", "progress", "total",
        "result", "error", "created_at", "started_at", "completed_at",
        "_async_task",
    )

    def __init__(self, task_id: str, task_type: str):
        self.task_id = task_id
        self.task_type = task_type
        self.status = TaskStatus.PENDING
        self.progress: int = 0
        self.total: int = 0
        self.result: Optional[dict] = None
        self.error: Optional[str] = None
        self.created_at = datetime.now(timezone.utc)
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self._async_task: Optional[asyncio.Task] = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "progress": self.progress,
            "total": self.total,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class TaskTracker:
    """Tracks background task status in memory."""

    def __init__(self, max_completed: int = 50):
        self._tasks: dict[str, TaskInfo] = {}
        self._max_completed = max_completed

    def create_task(self, task_type: str) -> TaskInfo:
        """Create a new task and return its info."""
        task_id = str(uuid.uuid4())[:8]
        task = TaskInfo(task_id=task_id, task_type=task_type)
        self._tasks[task_id] = task
        self._cleanup_old()
        return task

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """Get task info by ID."""
        return self._tasks.get(task_id)

    def get_tasks_by_type(self, task_type: str) -> list[TaskInfo]:
        """Get all tasks of a given type."""
        return [t for t in self._tasks.values() if t.task_type == task_type]

    def get_active_task(self, task_type: str) -> Optional[TaskInfo]:
        """Get the currently running task of a given type, if any."""
        for task in self._tasks.values():
            if task.task_type == task_type and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                return task
        return None

    def run_background(
        self,
        task_info: TaskInfo,
        coro: Coroutine,
    ) -> TaskInfo:
        """Schedule a coroutine as a background task."""
        async def _wrapper():
            task_info.status = TaskStatus.RUNNING
            task_info.started_at = datetime.now(timezone.utc)
            try:
                task_info.result = await coro
                task_info.status = TaskStatus.COMPLETED
            except Exception as e:
                logger.error(f"Task {task_info.task_id} failed: {e}")
                task_info.status = TaskStatus.FAILED
                task_info.error = str(e)
            finally:
                task_info.completed_at = datetime.now(timezone.utc)

        task_info._async_task = asyncio.create_task(_wrapper())
        return task_info

    def _cleanup_old(self):
        """Remove old completed tasks to prevent memory growth."""
        completed = [
            t for t in self._tasks.values()
            if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
        ]
        if len(completed) > self._max_completed:
            # Sort by completion time, remove oldest
            completed.sort(key=lambda t: t.completed_at or t.created_at)
            for task in completed[: len(completed) - self._max_completed]:
                del self._tasks[task.task_id]


# Global task tracker instance
_tracker: Optional[TaskTracker] = None


def get_task_tracker() -> TaskTracker:
    """Get the global task tracker."""
    global _tracker
    if _tracker is None:
        _tracker = TaskTracker()
    return _tracker
