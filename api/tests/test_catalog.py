"""Unit and API tests for the question-number catalog."""

from __future__ import annotations

import hashlib
import json
import threading
import time

from fastapi.testclient import TestClient
import pytest

from app.catalog.rules import complete_puzzle, normalize_code, puzzle_fingerprint
from app.catalog.service import CatalogService
from app.config import Settings
from app.main import create_app
from app.puzzles.balloon.recognize import BalloonRecognitionResult
from catalog_fakes import (
    ExplodingCatalogStore,
    MemoryCatalogStore,
    UnavailableCatalogStore,
    fake_recognition_job,
)


USABLE = ((1, 3), (2, 1), (2, 2), (2, 3), (3, 3))
ALTERNATIVE_USABLE = ((0, 2), (4, 2), (2, 0), (2, 4), (2, 2))


def board(rows: int = 5, columns: int = 5, usable: tuple[tuple[int, int], ...] = USABLE) -> dict:
    cells = ["blocked"] * (rows * columns)
    for row, column in usable:
        cells[row * columns + column] = "usable"
    return {"outcome": "draft", "rows": rows, "columns": columns, "cells": cells}


def draft(*, code: str | None = "WL-A1001", confidence: float | None = 0.996,
          lifts: tuple[int, ...] = (3, 1), counts: tuple[int | None, ...] = (1, 4),
          target: int | None = 7, rows: int = 5, columns: int = 5,
          usable: tuple[tuple[int, int], ...] = USABLE, unknown_cell: bool = False) -> dict:
    payload = board(rows, columns, usable)
    if unknown_cell:
        payload["cells"] = [None if index == 0 else cell for index, cell in enumerate(payload["cells"])]
    payload["inventory"] = [{"lift": lift, "count": count} for lift, count in zip(lifts, counts)]
    payload["target_total_lift"] = target
    payload["question_code"] = code
    payload["question_code_confidence"] = confidence
    payload["issues"] = []
    return payload


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def service_with(store) -> CatalogService:  # noqa: ANN001 - test double
    return CatalogService(store)


@pytest.mark.parametrize("raw,expected", [
    ("WL-A1001", "WL-A1001"),
    ("wl-a1001", "WL-A1001"),
    (" WL - A 1001 ", "WL-A1001"),
    ("WLA1001", "WL-A1001"),
    ("WL-A1001.", "WL-A1001"),
    ("[WL-A2014]", "WL-A2014"),
])
def test_normalize_code_accepts_canonical_forms(raw: str, expected: str) -> None:
    assert normalize_code(raw) == expected


@pytest.mark.parametrize("raw", ["WL-A10011", "WL-B1001", "A1001", "", "WL-A100", "1001", None, 1001])
def test_normalize_code_rejects_other_forms(raw: object) -> None:
    assert normalize_code(raw) is None


def test_complete_puzzle_requires_full_board_inventory_and_target() -> None:
    result = BalloonRecognitionResult.model_validate(draft())
    assert complete_puzzle(result) is not None
    # Real recognition results use None for cells without a white placement
    # outline. They must normalize exactly like explicit blocked cells.
    implicit_blocked = BalloonRecognitionResult.model_validate(draft(unknown_cell=True))
    assert complete_puzzle(implicit_blocked) is not None
    realistic = draft()
    realistic["cells"] = [None if cell == "blocked" else cell for cell in realistic["cells"]]
    assert complete_puzzle(BalloonRecognitionResult.model_validate(realistic)) is not None
    assert complete_puzzle(BalloonRecognitionResult.model_validate(draft(counts=(1, None)))) is None
    assert complete_puzzle(BalloonRecognitionResult.model_validate(draft(target=None))) is None
    assert complete_puzzle(BalloonRecognitionResult.model_validate(draft(target=8))) is None
    assert complete_puzzle(BalloonRecognitionResult.model_validate(
        {**draft(), "outcome": "no_board"})) is None


def test_fingerprint_ignores_ordering_only() -> None:
    first = complete_puzzle(BalloonRecognitionResult.model_validate(draft()))
    assert first is not None
    shuffled = {**first,
                "usable_cells": list(reversed(first["usable_cells"])),
                "inventory": list(reversed(first["inventory"]))}
    assert puzzle_fingerprint(first) == puzzle_fingerprint(shuffled)
    alternative = complete_puzzle(BalloonRecognitionResult.model_validate(
        draft(lifts=(2, 1), counts=(2, 3), usable=ALTERNATIVE_USABLE)))
    assert alternative is not None
    assert puzzle_fingerprint(alternative) != puzzle_fingerprint(first)


def test_first_observation_is_provisional_and_duplicate_digest_is_idempotent() -> None:
    store = MemoryCatalogStore()
    service = service_with(store)
    payload = draft()

    first = service.enrich_recognition(payload, digest("image-one"))
    assert first["catalog"]["recorded"] is True and first["catalog"]["duplicate"] is False
    assert first["catalog"]["status"] == "provisional"
    assert first["catalog"]["complete"] is True
    assert first["catalog"]["candidates"][0]["observations"] == 1
    assert first["catalog"]["matched_fingerprint"] == first["catalog"]["candidates"][0]["fingerprint"]

    repeated = service.enrich_recognition(payload, digest("image-one"))
    assert repeated["catalog"]["recorded"] is False and repeated["catalog"]["duplicate"] is True
    assert repeated["catalog"]["status"] == "provisional"
    assert repeated["catalog"]["candidates"][0]["observations"] == 1
    assert any("未重复计数" in issue for issue in repeated["catalog"]["issues"])
    assert store.records == 1


def test_second_distinct_digest_upgrades_candidate_to_verified() -> None:
    store = MemoryCatalogStore()
    service = service_with(store)
    payload = draft()

    service.enrich_recognition(payload, digest("image-one"))
    upgraded = service.enrich_recognition(payload, digest("image-two"))
    assert upgraded["catalog"]["status"] == "verified"
    assert upgraded["catalog"]["recorded"] is True
    assert upgraded["catalog"]["candidates"][0]["observations"] == 2
    assert any("已确认" in issue for issue in upgraded["catalog"]["issues"])

    duplicate = service.enrich_recognition(payload, digest("image-two"))
    assert duplicate["catalog"]["status"] == "verified"
    assert duplicate["catalog"]["candidates"][0]["observations"] == 2


def test_conflicting_statement_is_kept_as_dispute() -> None:
    store = MemoryCatalogStore()
    service = service_with(store)
    first = draft()
    second = draft(lifts=(2, 1), counts=(2, 3), usable=ALTERNATIVE_USABLE)

    service.enrich_recognition(first, digest("image-one"))
    conflicted = service.enrich_recognition(second, digest("image-two"))
    catalog = conflicted["catalog"]
    assert catalog["status"] == "disputed"
    assert len(catalog["candidates"]) == 2
    assert any("未覆盖" in issue for issue in catalog["issues"])
    fingerprints = {item["fingerprint"] for item in catalog["candidates"]}
    assert catalog["matched_fingerprint"] in fingerprints
    assert {item["observations"] for item in catalog["candidates"]} == {1}

    # Re-confirming the first statement must not remove the second candidate.
    third = service.enrich_recognition(first, digest("image-three"))
    assert third["catalog"]["status"] == "disputed"
    assert len(third["catalog"]["candidates"]) == 2
    assert store.records == 3


def test_incomplete_statement_reuses_unique_candidate() -> None:
    service = service_with(MemoryCatalogStore())
    service.enrich_recognition(draft(), digest("image-one"))

    incomplete = service.enrich_recognition(draft(counts=(1, None)), digest("image-two"))
    catalog = incomplete["catalog"]
    assert catalog["complete"] is False
    assert catalog["recorded"] is False
    assert catalog["status"] == "provisional"
    assert len(catalog["candidates"]) == 1
    assert any("唯一完整题面" in issue for issue in catalog["issues"])


def test_incomplete_statement_with_dispute_lists_candidates() -> None:
    service = service_with(MemoryCatalogStore())
    service.enrich_recognition(draft(), digest("image-one"))
    service.enrich_recognition(draft(lifts=(2, 1), counts=(2, 3), usable=ALTERNATIVE_USABLE), digest("image-two"))

    incomplete = service.enrich_recognition(draft(counts=(1, None)), digest("image-three"))
    catalog = incomplete["catalog"]
    assert catalog["complete"] is False
    assert catalog["status"] == "disputed"
    assert len(catalog["candidates"]) == 2
    assert any("多个不同题面" in issue for issue in catalog["issues"])


def test_incomplete_statement_without_record_is_reported() -> None:
    service = service_with(MemoryCatalogStore())
    catalog = service.enrich_recognition(draft(counts=(1, None)), digest("image-one"))["catalog"]
    assert catalog["candidates"] == []
    assert catalog["status"] is None
    assert any("没有题号" in issue for issue in catalog["issues"])


def test_recognition_without_code_never_touches_catalog() -> None:
    store = MemoryCatalogStore()
    service = service_with(store)
    payload = draft(code=None, confidence=None)
    result = service.enrich_recognition(payload, digest("image-one"))
    assert result == {**payload, "catalog": None}
    assert store.records == 0 and store.lookups == 0


def test_unavailable_catalog_is_reported_but_result_survives() -> None:
    service = CatalogService(UnavailableCatalogStore())
    payload = service.enrich_recognition(draft(), digest("image-one"))
    assert payload["catalog"]["available"] is False
    assert payload["catalog"]["recorded"] is False
    assert payload["rows"] == 5 and payload["target_total_lift"] == 7
    assert any("目录暂时不可用" in issue for issue in payload["catalog"]["issues"])


def test_unsatisfiable_recognition_is_not_recorded() -> None:
    store = MemoryCatalogStore()
    service = service_with(store)
    payload = draft(rows=2, columns=2, usable=((0, 0),), lifts=(1,), counts=(1,), target=1)
    result = service.enrich_recognition(payload, digest("bad-board"))
    assert result["catalog"]["complete"] is False
    assert result["catalog"]["recorded"] is False
    assert result["catalog"]["candidates"] == []
    assert any("没有可行解" in issue and "未写入" in issue for issue in result["catalog"]["issues"])
    assert store.records == 0


def test_concurrent_observations_of_one_image_are_idempotent() -> None:
    store = MemoryCatalogStore()
    service = service_with(store)
    payload = draft()
    results: list[dict] = []
    lock = threading.Lock()

    def observe() -> None:
        enriched = service.enrich_recognition(payload, digest("same-image"))
        with lock:
            results.append(enriched)

    threads = [threading.Thread(target=observe) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert store.records == 1
    assert sum(1 for item in results if item["catalog"]["recorded"]) == 1
    entry = store.get("WL-A1001")
    assert entry is not None and len(entry.candidates) == 1
    assert entry.candidates[0].observations == 1


def make_client(catalog: CatalogService | None = None) -> TestClient:
    return TestClient(create_app(Settings(cors_origins=("http://localhost:5173",), max_workers=1), catalog=catalog))


def wait_for_task(client: TestClient, task_id: str) -> dict:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        task = client.get(f"/api/v1/tasks/{task_id}").json()
        if task["status"] in ("succeeded", "failed", "cancelled"):
            return task
        time.sleep(.05)
    raise AssertionError("task did not finish")


def test_catalog_endpoint_serves_normalized_records() -> None:
    store = MemoryCatalogStore()
    service = service_with(store)
    service.enrich_recognition(draft(), digest("image-one"))
    service.enrich_recognition(draft(), digest("image-two"))
    with make_client(service) as client:
        response = client.get("/api/v1/puzzles/balloon/catalog/wl-a1001")
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == "WL-A1001"
        assert body["status"] == "verified"
        assert len(body["candidates"]) == 1
        assert body["candidates"][0]["observations"] == 2
        assert body["candidates"][0]["target_total_lift"] == 7
        assert body["candidates"][0]["puzzle"]["inventory"] == [{"lift": 3, "count": 1}, {"lift": 1, "count": 4}]


def test_catalog_endpoint_errors() -> None:
    with make_client(service_with(MemoryCatalogStore())) as client:
        invalid = client.get("/api/v1/puzzles/balloon/catalog/WL-A123")
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "INVALID_CODE"
        missing = client.get("/api/v1/puzzles/balloon/catalog/WL-A9999")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "CATALOG_NOT_FOUND"
    with make_client(CatalogService(UnavailableCatalogStore())) as client:
        unavailable = client.get("/api/v1/puzzles/balloon/catalog/WL-A1001")
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "CATALOG_UNAVAILABLE"
    with make_client(CatalogService(None)) as client:
        disabled = client.get("/api/v1/puzzles/balloon/catalog/WL-A1001")
        assert disabled.status_code == 503
        assert disabled.json()["error"]["code"] == "CATALOG_UNAVAILABLE"


def test_recognition_endpoint_records_catalog_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    store = MemoryCatalogStore()
    service = service_with(store)
    monkeypatch.setattr("app.main.recognize_balloon_job", fake_recognition_job)
    with make_client(service) as client:
        upload = json.dumps(draft()).encode("utf-8")
        first = client.post("/api/v1/puzzles/balloon/recognize", files={"image": ("shot.json", upload, "image/png")})
        assert first.status_code == 202
        result = wait_for_task(client, first.json()["id"])["result"]
        assert result["catalog"]["code"] == "WL-A1001"
        assert result["catalog"]["recorded"] is True
        assert result["catalog"]["status"] == "provisional"
        assert result["question_code_confidence"] == pytest.approx(0.996)

        # Same statement, different bytes: a second distinct digest confirms it.
        upload_two = json.dumps({**draft(), "issues": ["second screenshot"]}).encode("utf-8")
        second = client.post("/api/v1/puzzles/balloon/recognize", files={"image": ("shot2.json", upload_two, "image/png")})
        result = wait_for_task(client, second.json()["id"])["result"]
        assert result["catalog"]["status"] == "verified"
        assert result["catalog"]["candidates"][0]["observations"] == 2

        entry = client.get("/api/v1/puzzles/balloon/catalog/WL-A1001").json()
        assert entry["status"] == "verified"


def test_recognition_endpoint_without_code_keeps_existing_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    store = MemoryCatalogStore()
    service = service_with(store)
    monkeypatch.setattr("app.main.recognize_balloon_job", fake_recognition_job)
    with make_client(service) as client:
        upload = json.dumps(draft(code=None, confidence=None)).encode("utf-8")
        created = client.post("/api/v1/puzzles/balloon/recognize", files={"image": ("shot.json", upload, "image/png")})
        result = wait_for_task(client, created.json()["id"])["result"]
        assert result["catalog"] is None
        assert result["outcome"] == "draft" and result["target_total_lift"] == 7
    assert store.records == 0 and store.lookups == 0


def test_recognition_survives_unexpected_catalog_bug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.main.recognize_balloon_job", fake_recognition_job)
    with make_client(CatalogService(ExplodingCatalogStore())) as client:
        upload = json.dumps(draft()).encode("utf-8")
        created = client.post("/api/v1/puzzles/balloon/recognize", files={"image": ("shot.json", upload, "image/png")})
        task = wait_for_task(client, created.json()["id"])
        assert task["status"] == "succeeded"
        # The finalize hook is guarded: the raw recognition result is kept.
        assert task["result"].get("catalog") is None
        assert task["result"]["target_total_lift"] == 7


def test_openapi_describes_catalog_contract() -> None:
    with make_client() as client:
        schema = client.get("/openapi.json").json()
        path = schema["paths"]["/api/v1/puzzles/balloon/catalog/{code}"]["get"]
        assert path["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/CatalogEntry")
        assert "503" in path["responses"]
        schemas = schema["components"]["schemas"]
        assert {"CatalogEntry", "CatalogCandidate", "CatalogMatch"} <= set(schemas)
        recognition = schemas["BalloonRecognitionResult"]["properties"]
        assert "question_code" in recognition and "catalog" in recognition
