"""One-process task coordinator with a fixed-size spawn process pool.

Only this API process owns task state. Workers receive pickleable callables and values.
"""

from collections import deque
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
import multiprocessing
from threading import Event, RLock, Thread
import time
from typing import Any, Callable
from uuid import uuid4

from app.config import Settings
from app.models import ErrorDetail, TaskView


class QueueFull(Exception):
    pass


@dataclass
class _Task:
    id: str
    work: Callable[..., Any] | None = field(repr=False)
    args: tuple[Any, ...] = field(repr=False)
    created_at: datetime
    status: str = "queued"
    completed_at: datetime | None = None
    completed_monotonic: float | None = None
    cancellation_requested: bool = False
    result: Any = None
    error: ErrorDetail | None = None

    def view(self) -> TaskView:
        return TaskView(
            id=self.id,
            status=self.status,
            created_at=self.created_at,
            completed_at=self.completed_at,
            cancellation_requested=self.cancellation_requested,
            computation_stopped=self.status in ("succeeded", "failed", "cancelled"),
            result=self.result,
            error=self.error,
        )


class TaskManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = RLock()
        self._pool = ProcessPoolExecutor(
            max_workers=settings.max_workers,
            mp_context=multiprocessing.get_context("spawn"),
        )
        self._tasks: dict[str, _Task] = {}
        self._pending: deque[str] = deque()
        self._running = 0
        self._closed = False
        self._stop_cleanup = Event()
        self._cleanup = Thread(target=self._cleanup_loop, name="task-result-cleanup", daemon=True)
        self._cleanup.start()

    def submit(self, work: Callable[..., Any], *args: Any) -> TaskView:
        """Internal engine hook; never exposed as an HTTP test endpoint."""
        with self._lock:
            if self._closed:
                raise RuntimeError("task manager is closed")
            self._prune_locked()
            if self._running >= self.settings.max_workers and len(self._pending) >= self.settings.max_queued:
                raise QueueFull()
            task = _Task(id=uuid4().hex, work=work, args=args, created_at=datetime.now(timezone.utc))
            self._tasks[task.id] = task
            self._pending.append(task.id)
            self._dispatch_locked()
            return task.view()

    def get(self, task_id: str) -> TaskView | None:
        with self._lock:
            self._prune_locked()
            task = self._tasks.get(task_id)
            return task.view() if task else None

    def cancel(self, task_id: str) -> TaskView | None:
        with self._lock:
            self._prune_locked()
            task = self._tasks.get(task_id)
            if task is None:
                return None
            if task.status == "queued":
                self._pending.remove(task_id)
                task.cancellation_requested = True
                self._finish_locked(task, "cancelled")
                self._dispatch_locked()
            elif task.status == "running":
                # The computation continues to hold its process until it finishes.
                task.cancellation_requested = True
            return task.view()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stop_cleanup.set()
            for task_id in self._pending:
                task = self._tasks[task_id]
                task.cancellation_requested = True
                self._finish_locked(task, "cancelled")
            self._pending.clear()
        self._cleanup.join()
        self._pool.shutdown(wait=True, cancel_futures=False)

    def _dispatch_locked(self) -> None:
        while not self._closed and self._pending and self._running < self.settings.max_workers:
            task = self._tasks[self._pending.popleft()]
            task.status = "running"
            self._running += 1
            try:
                future = self._pool.submit(task.work, *task.args)
            except Exception:
                self._running -= 1
                self._finish_locked(task, "failed", ErrorDetail(code="TASK_FAILED", message="计算任务启动失败"))
                continue
            future.add_done_callback(lambda completed, task_id=task.id: self._on_done(task_id, completed))

    def _on_done(self, task_id: str, future: Future[Any]) -> None:
        with self._lock:
            task = self._tasks[task_id]
            self._running -= 1
            try:
                result = future.result()
            except Exception:
                self._finish_locked(task, "cancelled" if task.cancellation_requested else "failed",
                    None if task.cancellation_requested else ErrorDetail(code="TASK_FAILED", message="计算失败"))
            else:
                if task.cancellation_requested:
                    self._finish_locked(task, "cancelled")
                else:
                    task.result = result
                    self._finish_locked(task, "succeeded")
            self._prune_locked()
            self._dispatch_locked()

    def _finish_locked(self, task: _Task, status: str, error: ErrorDetail | None = None) -> None:
        task.status = status
        task.error = error
        task.work = None
        task.args = ()
        task.completed_at = datetime.now(timezone.utc)
        task.completed_monotonic = time.monotonic()

    def _cleanup_loop(self) -> None:
        while not self._stop_cleanup.wait(min(self.settings.result_ttl_seconds, 30)):
            with self._lock:
                self._prune_locked()

    def _prune_locked(self) -> None:
        now = time.monotonic()
        finished = sorted(
            (task for task in self._tasks.values() if task.completed_monotonic is not None),
            key=lambda task: task.completed_monotonic or 0,
        )
        for task in finished:
            if now - (task.completed_monotonic or now) >= self.settings.result_ttl_seconds:
                del self._tasks[task.id]
        remaining = [task for task in finished if task.id in self._tasks]
        for task in remaining[:-self.settings.max_retained]:
            del self._tasks[task.id]
