import os
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.tasks import QueueFull, TaskManager


def work(seconds: float, fail: bool = False) -> dict[str, int]:
    time.sleep(seconds)
    if fail:
        raise RuntimeError("private worker error")
    return {"pid": os.getpid()}


def until(manager: TaskManager, task_id: str, statuses: set[str], timeout: float = 10) -> object:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = manager.get(task_id)
        if task and task.status in statuses:
            return task
        time.sleep(0.02)
    raise AssertionError(f"task {task_id} did not reach {statuses}")


def test_capacity_cancel_and_real_spawn_process() -> None:
    manager = TaskManager(Settings(max_workers=1, max_queued=1, result_ttl_seconds=10, max_retained=10))
    try:
        running = manager.submit(work, 0.5)
        queued = manager.submit(work, 0)
        assert running.status == "running"
        assert queued.status == "queued"
        with pytest.raises(QueueFull):
            manager.submit(work, 0)
        cancelled = manager.cancel(queued.id)
        assert cancelled.status == "cancelled" and cancelled.computation_stopped
        replacement = manager.submit(work, 0)
        assert replacement.status == "queued"
        finished = until(manager, running.id, {"succeeded"})
        assert finished.result["pid"] != os.getpid()
        assert until(manager, replacement.id, {"succeeded"}).result["pid"] != os.getpid()
    finally:
        manager.close()


def test_running_cancel_keeps_slot_and_failure_releases_it() -> None:
    manager = TaskManager(Settings(max_workers=1, max_queued=0, result_ttl_seconds=10, max_retained=10))
    try:
        first = manager.submit(work, 0.4)
        cancelling = manager.cancel(first.id)
        assert cancelling.status == "running"
        assert cancelling.cancellation_requested and not cancelling.computation_stopped
        with pytest.raises(QueueFull):
            manager.submit(work, 0)
        assert until(manager, first.id, {"cancelled"}).computation_stopped
        failed = manager.submit(work, 0, True)
        result = until(manager, failed.id, {"failed"})
        assert result.error.code == "TASK_FAILED"
        assert "private worker error" not in result.error.message
        assert until(manager, manager.submit(work, 0).id, {"succeeded"}).status == "succeeded"
    finally:
        manager.close()


def test_retention_and_ttl() -> None:
    manager = TaskManager(Settings(max_workers=1, max_queued=1, result_ttl_seconds=1, max_retained=1))
    try:
        first = manager.submit(work, 0)
        until(manager, first.id, {"succeeded"})
        second = manager.submit(work, 0)
        until(manager, second.id, {"succeeded"})
        assert manager.get(first.id) is None
        assert manager.get(second.id) is not None
        time.sleep(1.05)
        assert manager.get(second.id) is None
    finally:
        manager.close()


def test_api_stays_responsive_while_worker_runs() -> None:
    app = create_app(Settings(max_workers=1, max_queued=0))
    with TestClient(app) as client:
        task = app.state.tasks.submit(work, 0.5)
        started = time.monotonic()
        assert client.get("/api/v1/health").json() == {"status": "ok"}
        assert time.monotonic() - started < 0.3
        response = client.get(f"/api/v1/tasks/{task.id}")
        assert response.status_code == 200
        assert response.json()["status"] == "running"
        cancelled = client.delete(f"/api/v1/tasks/{task.id}").json()
        assert cancelled["cancellation_requested"] and not cancelled["computation_stopped"]
        assert until(app.state.tasks, task.id, {"cancelled"}).computation_stopped


def test_completed_input_release_and_idle_ttl_cleanup() -> None:
    manager = TaskManager(Settings(max_workers=1, max_queued=1, result_ttl_seconds=1, max_retained=10))
    try:
        running = manager.submit(work, 0.3)
        queued = manager.submit(work, 0)
        manager.cancel(queued.id)
        assert manager._tasks[queued.id].work is None
        assert manager._tasks[queued.id].args == ()
        until(manager, running.id, {"succeeded"})
        assert manager._tasks[running.id].work is None
        assert manager._tasks[running.id].args == ()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and manager._tasks:
            time.sleep(0.02)
        assert manager._tasks == {}
    finally:
        manager.close()
