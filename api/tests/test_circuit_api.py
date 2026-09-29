"""HTTP and task-queue integration for the source-circuit API."""

from __future__ import annotations

import copy
import json
import time

from fastapi.testclient import TestClient
import pytest

from app.catalog.circuit_service import CircuitCatalogService
from app.catalog.service import CatalogService
from app.config import Settings
from app.main import create_app
from app.puzzles.circuit.model import CircuitPuzzle, CircuitSolution
from app.puzzles.circuit.verify import validate_solution
from circuit_catalog_fakes import (
    MemoryCircuitCatalogStore,
    UnavailableCircuitCatalogStore,
    fake_circuit_recognition_job,
)
from catalog_fakes import MemoryCatalogStore


PUZZLE = {
    "rule_version": "line-count-v1",
    "rows": 2,
    "columns": 2,
    "channels": [
        {"index": 0, "row_targets": [2, 0], "column_targets": [1, 1]}
    ],
    "blocked_cells": [],
    "fixed_cells": [],
    "pieces": [
        {
            "channel": 0,
            "cells": [
                {"row": 0, "column": 0},
                {"row": 0, "column": 1},
            ],
        }
    ],
}

VERTICAL_PUZZLE = {
    **PUZZLE,
    "channels": [
        {"index": 0, "row_targets": [1, 1], "column_targets": [2, 0]}
    ],
}


def recognition(puzzle: dict = PUZZLE) -> dict:
    return {
        "outcome": "recognized",
        "puzzle": copy.deepcopy(puzzle),
        "notation": "digits",
        "question_code": "V40020",
        "question_code_confidence": 0.99,
        "catalog": None,
        "issues": [],
    }


def settings(**changes) -> Settings:  # noqa: ANN003
    values = {
        "cors_origins": ("http://localhost:5173",),
        "max_workers": 1,
        "recognize_time_limit_seconds": 7,
        "solve_time_limit_seconds": 2,
        "solve_max_nodes": 12345,
    }
    values.update(changes)
    return Settings(**values)


def wait_for_task(client: TestClient, task_id: str) -> dict:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        task = client.get(f"/api/v1/tasks/{task_id}").json()
        if task["status"] in {"succeeded", "failed", "cancelled"}:
            return task
        time.sleep(0.02)
    raise AssertionError("circuit task did not finish")


def test_circuit_routes_take_priority_while_capability_stays_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.main.recognize_circuit_job", fake_circuit_recognition_job
    )
    store = MemoryCircuitCatalogStore()
    service = CircuitCatalogService(store)
    with TestClient(create_app(settings(), circuit_catalog=service)) as client:
        capability = {
            item["id"]: item for item in client.get("/api/v1/puzzles").json()
        }["circuit"]
        assert capability == {
            "id": "circuit",
            "name": "源石电路",
            "recognition_available": False,
            "solving_available": False,
            "supported_rule_versions": [],
            "rules_note": "尚未开放",
        }

        created = client.post(
            "/api/v1/puzzles/circuit/recognize",
            files={"image": ("shot.json", json.dumps(recognition()).encode(), "image/png")},
        )
        assert created.status_code == 202
        solved = client.post("/api/v1/puzzles/circuit/solve", json=PUZZLE)
        assert solved.status_code == 202
        assert client.post("/api/v1/puzzles/unknown/recognize").status_code == 404
        assert client.post("/api/v1/puzzles/unknown/solve", json={}).status_code == 404


def test_recognition_uses_four_worker_arguments_and_api_finalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.main.recognize_circuit_job", fake_circuit_recognition_job
    )
    store = MemoryCircuitCatalogStore()
    service = CircuitCatalogService(store)
    with TestClient(create_app(settings(), circuit_catalog=service)) as client:
        payload = json.dumps(recognition()).encode()
        created = client.post(
            "/api/v1/puzzles/circuit/recognize",
            files={"image": ("shot.json", payload, "image/png")},
        )
        assert created.status_code == 202
        task = wait_for_task(client, created.json()["id"])
        assert task["status"] == "succeeded", task
        result = task["result"]
        assert "limits=7,2,12345" in result["issues"]
        assert result["catalog"]["recorded"] is True
        assert result["catalog"]["matched_status"] == "provisional"
        assert store.records == 1

        entry = client.get("/api/v1/puzzles/circuit/catalog/△-V40020")
        assert entry.status_code == 200
        assert entry.json()["code"] == "V40020"
        assert len(entry.json()["candidates"]) == 1


def test_circuit_recognition_upload_validation() -> None:
    with TestClient(create_app(settings())) as client:
        missing = client.post("/api/v1/puzzles/circuit/recognize", data={})
        assert missing.status_code == 422
        assert missing.json()["error"]["code"] == "INVALID_REQUEST"
        empty = client.post(
            "/api/v1/puzzles/circuit/recognize",
            files={"image": ("empty.png", b"", "image/png")},
        )
        assert empty.status_code == 422
        assert empty.json()["error"]["code"] == "INVALID_REQUEST"
        malformed = client.post(
            "/api/v1/puzzles/circuit/recognize",
            content=b"not multipart",
            headers={"Content-Type": "multipart/form-data; boundary=broken"},
        )
        assert malformed.status_code == 422
        assert malformed.json()["error"]["code"] == "INVALID_REQUEST"
        extra = client.post(
            "/api/v1/puzzles/circuit/recognize",
            files={
                "image": ("x.png", b"x", "image/png"),
                "other": ("y.png", b"y", "image/png"),
            },
        )
        assert extra.status_code == 422
        assert extra.json()["error"]["code"] == "INVALID_REQUEST"


def test_circuit_solve_task_returns_independently_valid_solution() -> None:
    with TestClient(create_app(settings())) as client:
        created = client.post("/api/v1/puzzles/circuit/solve", json=PUZZLE)
        assert created.status_code == 202
        task = wait_for_task(client, created.json()["id"])
        assert task["status"] == "succeeded", task
        assert task["result"]["outcome"] == "solved"
        puzzle = CircuitPuzzle.model_validate(PUZZLE)
        solution = CircuitSolution.model_validate(task["result"]["solution"])
        validate_solution(puzzle, solution)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {**PUZZLE, "rule_version": "bad"},
        {**PUZZLE, "solve_max_nodes": 999999},
    ],
)
def test_circuit_solve_rejects_invalid_json(body: dict) -> None:
    with TestClient(create_app(settings())) as client:
        response = client.post("/api/v1/puzzles/circuit/solve", json=body)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_circuit_catalog_serves_all_normal_variants() -> None:
    store = MemoryCircuitCatalogStore()
    service = CircuitCatalogService(store)
    service.enrich_recognition(recognition(PUZZLE), "a" * 64)
    service.enrich_recognition(recognition(VERTICAL_PUZZLE), "b" * 64)
    service.enrich_recognition(recognition(VERTICAL_PUZZLE), "c" * 64)

    with TestClient(create_app(settings(), circuit_catalog=service)) as client:
        response = client.get("/api/v1/puzzles/circuit/catalog/V40020")
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == "V40020"
        assert [item["status"] for item in body["candidates"]] == [
            "verified",
            "provisional",
        ]
        assert "status" not in body


def test_circuit_catalog_error_contract() -> None:
    with TestClient(
        create_app(
            settings(),
            circuit_catalog=CircuitCatalogService(MemoryCircuitCatalogStore()),
        )
    ) as client:
        invalid = client.get("/api/v1/puzzles/circuit/catalog/WL-A0020")
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "INVALID_CODE"
        assert "V 加五位数字" in invalid.json()["error"]["message"]
        assert "WL 加四位数字" in invalid.json()["error"]["message"]
        missing = client.get("/api/v1/puzzles/circuit/catalog/WL0020")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "CATALOG_NOT_FOUND"

    with TestClient(
        create_app(
            settings(),
            circuit_catalog=CircuitCatalogService(
                UnavailableCircuitCatalogStore()
            ),
        )
    ) as client:
        unavailable = client.get("/api/v1/puzzles/circuit/catalog/V40020")
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "CATALOG_UNAVAILABLE"

    with TestClient(
        create_app(settings(), circuit_catalog=CircuitCatalogService(None))
    ) as client:
        disabled = client.get("/api/v1/puzzles/circuit/catalog/V40020")
        assert disabled.status_code == 503
        assert disabled.json()["error"]["code"] == "CATALOG_UNAVAILABLE"


def test_lifespan_closes_both_injected_catalog_services() -> None:
    class TrackingBalloonStore(MemoryCatalogStore):
        def __init__(self) -> None:
            super().__init__()
            self.closes = 0

        def close(self) -> None:
            self.closes += 1

    balloon_store = TrackingBalloonStore()
    circuit_store = MemoryCircuitCatalogStore()
    with TestClient(
        create_app(
            settings(),
            catalog=CatalogService(balloon_store),
            circuit_catalog=CircuitCatalogService(circuit_store),
        )
    ):
        pass
    assert balloon_store.closes == 1
    assert circuit_store.closes == 1


def test_openapi_exposes_circuit_routes_and_strong_task_models() -> None:
    with TestClient(create_app(settings())) as client:
        schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert {
        "/api/v1/puzzles/circuit/recognize",
        "/api/v1/puzzles/circuit/solve",
        "/api/v1/puzzles/circuit/catalog/{code}",
    } <= set(paths)
    assert "multipart/form-data" in paths[
        "/api/v1/puzzles/circuit/recognize"
    ]["post"]["requestBody"]["content"]
    recognize_ref = paths["/api/v1/puzzles/circuit/recognize"]["post"][
        "responses"
    ]["202"]["content"]["application/json"]["schema"]["$ref"]
    solve_ref = paths["/api/v1/puzzles/circuit/solve"]["post"]["responses"][
        "202"
    ]["content"]["application/json"]["schema"]["$ref"]
    catalog_ref = paths["/api/v1/puzzles/circuit/catalog/{code}"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert recognize_ref.endswith("/CircuitRecognitionTaskView")
    assert solve_ref.endswith("/CircuitSolveTaskView")
    assert catalog_ref.endswith("/CircuitCatalogEntry")
    schemas = schema["components"]["schemas"]
    assert {
        "CircuitPuzzle",
        "CircuitRecognitionResult",
        "CircuitSolveResult",
        "CircuitCatalogEntry",
        "CircuitCatalogCandidate",
        "CircuitCatalogMatch",
    } <= set(schemas)
    assert schemas["CircuitRecognitionTaskView"]["properties"]["result"]
    assert schemas["CircuitSolveTaskView"]["properties"]["result"]
