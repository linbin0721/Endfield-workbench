"""PostgreSQL-backed store tests.

They run against a real server when ``CATALOG_TEST_DSN`` is set, for example a
throwaway ``postgres:17-alpine`` container on a private Docker network:

    CATALOG_TEST_DSN=postgresql://user:pass@host:5432/db python -m pytest tests/test_catalog_store.py
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time

from fastapi.testclient import TestClient
import psycopg
import pytest

from app.catalog.rules import complete_puzzle, puzzle_fingerprint
from app.catalog.service import CatalogService
from app.catalog.store import CatalogUnavailable, Observation, PostgresCatalogStore
from app.config import Settings
from app.main import create_app
from app.puzzles.balloon.recognize import BalloonRecognitionResult
from catalog_fakes import fake_recognition_job


DSN = os.getenv("CATALOG_TEST_DSN")

pytestmark = pytest.mark.skipif(not DSN, reason="CATALOG_TEST_DSN is not set")

USABLE = ((1, 3), (2, 1), (2, 2), (2, 3), (3, 3))
ALTERNATIVE_USABLE = ((0, 2), (4, 2), (2, 0), (2, 4), (2, 2))


def puzzle(lifts: tuple[int, ...] = (3, 1), counts: tuple[int, ...] = (1, 4),
           usable: tuple[tuple[int, int], ...] = USABLE) -> dict:
    cells = ["blocked"] * 25
    for row, column in usable:
        cells[row * 5 + column] = "usable"
    payload = {"outcome": "draft", "rows": 5, "columns": 5, "cells": cells,
               "inventory": [{"lift": lift, "count": count} for lift, count in zip(lifts, counts)],
               "target_total_lift": sum(lift * count for lift, count in zip(lifts, counts)),
               "issues": []}
    complete = complete_puzzle(BalloonRecognitionResult.model_validate(payload))
    assert complete is not None
    return complete


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def recognition_payload(lifts: tuple[int, ...] = (3, 1), counts: tuple[int, ...] = (1, 4),
                        usable: tuple[tuple[int, int], ...] = USABLE) -> dict:
    cells = ["blocked"] * 25
    for row, column in usable:
        cells[row * 5 + column] = "usable"
    return {"outcome": "draft", "rows": 5, "columns": 5, "cells": cells,
            "inventory": [{"lift": lift, "count": count} for lift, count in zip(lifts, counts)],
            "target_total_lift": sum(lift * count for lift, count in zip(lifts, counts)),
            "question_code": "WL-A1001", "question_code_confidence": .997, "issues": []}


def observation(payload: dict, image: str, target: int = 7) -> Observation:
    return Observation(code="WL-A1001", image_sha256=digest(image),
                       fingerprint=puzzle_fingerprint(payload), puzzle=payload, target_total_lift=target)


@pytest.fixture()
def store() -> PostgresCatalogStore:
    created = PostgresCatalogStore(DSN, timeout=10, min_size=1, max_size=6)
    created.get("WL-A0000")  # creates the schema
    with psycopg.connect(DSN) as connection:
        connection.execute("TRUNCATE balloon_catalog_observation, balloon_catalog_candidate, "
                           "balloon_catalog_entry RESTART IDENTITY CASCADE")
        connection.commit()
    yield created
    created.close()


def test_missing_database_reports_unavailable() -> None:
    broken = PostgresCatalogStore("postgresql://nobody:nobody@127.0.0.1:1/none", timeout=.5)
    with pytest.raises(CatalogUnavailable):
        broken.get("WL-A1001")
    broken.close()


def test_record_dedup_upgrade_and_dispute(store: PostgresCatalogStore) -> None:
    first = puzzle()
    second = puzzle(lifts=(2, 1), counts=(2, 3), usable=ALTERNATIVE_USABLE)

    entry, recorded = store.record(observation(first, "image-one"))
    assert recorded is True and entry.status == "provisional" and entry.candidates[0].observations == 1

    entry, recorded = store.record(observation(first, "image-one"))
    assert recorded is False and entry.status == "provisional" and entry.candidates[0].observations == 1

    entry, recorded = store.record(observation(first, "image-two"))
    assert recorded is True and entry.status == "verified" and entry.candidates[0].observations == 2

    entry, recorded = store.record(observation(second, "image-three"))
    assert recorded is True and entry.status == "disputed" and len(entry.candidates) == 2
    assert {item.observations for item in entry.candidates} == {1, 2}
    assert {item.target_total_lift for item in entry.candidates} == {7}

    loaded = store.get("WL-A1001")
    assert loaded is not None and loaded.status == "disputed" and len(loaded.candidates) == 2
    assert store.get("WL-A9999") is None


def test_concurrent_identical_observations_are_idempotent(store: PostgresCatalogStore) -> None:
    payload = puzzle()
    outcomes: list[bool] = []
    lock = threading.Lock()

    def record() -> None:
        _, recorded = store.record(observation(payload, "same-image"))
        with lock:
            outcomes.append(recorded)

    threads = [threading.Thread(target=record) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes.count(True) == 1
    entry = store.get("WL-A1001")
    assert entry is not None and len(entry.candidates) == 1
    assert entry.candidates[0].observations == 1

    store.record(observation(payload, "other-image"))
    entry = store.get("WL-A1001")
    assert entry is not None and entry.status == "verified"
    assert entry.candidates[0].observations == 2


def test_http_recognition_records_and_serves_through_postgres(store: PostgresCatalogStore,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    """Full path: upload -> task -> API-process finalize -> PostgreSQL -> query API."""
    monkeypatch.setattr("app.main.recognize_balloon_job", fake_recognition_job)
    settings = Settings(cors_origins=("http://localhost:5173",), max_workers=1)
    with TestClient(create_app(settings, catalog=CatalogService(store))) as client:
        first = client.post("/api/v1/puzzles/balloon/recognize", files={
            "image": ("shot.json", json.dumps(recognition_payload()).encode(), "image/png")})
        assert first.status_code == 202
        task = _wait(client, first.json()["id"])
        assert task["status"] == "succeeded"
        assert task["result"]["catalog"]["recorded"] is True
        assert task["result"]["catalog"]["status"] == "provisional"

        entry = client.get("/api/v1/puzzles/balloon/catalog/WL-A1001")
        assert entry.status_code == 200
        assert entry.json()["candidates"][0]["observations"] == 1

        # A second, different screenshot of the same statement confirms it.
        second_payload = {**recognition_payload(), "issues": ["second image"]}
        second = client.post("/api/v1/puzzles/balloon/recognize", files={
            "image": ("shot2.json", json.dumps(second_payload).encode(), "image/png")})
        _wait(client, second.json()["id"])
        entry = client.get("/api/v1/puzzles/balloon/catalog/wl-a1001").json()
        assert entry["status"] == "verified"
        assert entry["candidates"][0]["observations"] == 2
        assert entry["candidates"][0]["puzzle"]["inventory"] == [{"lift": 3, "count": 1}, {"lift": 1, "count": 4}]


def _wait(client: TestClient, task_id: str) -> dict:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        task = client.get(f"/api/v1/tasks/{task_id}").json()
        if task["status"] in ("succeeded", "failed", "cancelled"):
            return task
        time.sleep(.05)
    raise AssertionError("task did not finish")
