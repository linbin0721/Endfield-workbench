from collections import Counter
from itertools import product
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.puzzles.balloon.model import BalloonPuzzle, BalloonSolution
from app.puzzles.balloon.solve import solve_balloon
from app.puzzles.balloon.verify import validate_solution


def sample() -> dict:
    outer = [{"row": row, "column": column} for row in range(5) for column in range(5)
             if row in (0, 4) or column in (0, 4)]
    return {"rule_version": "center-torque-v1", "rows": 5, "columns": 5,
            "usable_cells": outer, "inventory": [{"lift": lift, "count": 3} for lift in (1, 2, 3, 6)]}


def brute_force_exists(puzzle: BalloonPuzzle) -> bool:
    expected = Counter({item.lift: item.count for item in puzzle.inventory})
    choices = [0, *expected]
    cells = [(item.row, item.column) for item in puzzle.usable_cells]
    for assignment in product(choices, repeat=len(cells)):
        if Counter(x for x in assignment if x) != expected:
            continue
        row_moment = sum(lift * (2 * row - puzzle.rows + 1) for (row, _), lift in zip(cells, assignment))
        column_moment = sum(lift * (2 * column - puzzle.columns + 1) for (_, column), lift in zip(cells, assignment))
        if row_moment == column_moment == 0:
            return True
    return False


def test_known_5x5_sample_and_independent_answer_validation() -> None:
    puzzle = BalloonPuzzle.model_validate(sample())
    result = solve_balloon(puzzle, 3, 300000)
    assert result.outcome == "solved"
    assert result.solution is not None
    validate_solution(puzzle, result.solution)
    assert result.solution.used_count == 12
    assert result.solution.total_lift == 36
    altered = result.solution.model_copy(deep=True)
    altered.placements[0].lift = 99
    with pytest.raises(ValueError):
        validate_solution(puzzle, altered)


def test_small_boards_against_independent_exhaustive_enumeration() -> None:
    cases = [
        (2, 2, [(0, 0), (0, 1), (1, 0), (1, 1)], [(1, 2)]),
        (2, 2, [(0, 0), (0, 1), (1, 0)], [(1, 2)]),
        (2, 3, [(0, 0), (0, 2), (1, 0), (1, 2)], [(1, 2)]),
        (2, 3, [(0, 0), (0, 1), (1, 2)], [(1, 1), (2, 1)]),
        (3, 3, [(0, 0), (0, 2), (2, 0), (2, 2)], [(1, 2), (2, 1)]),
    ]
    for rows, columns, cells, stock in cases:
        puzzle = BalloonPuzzle.model_validate({"rule_version": "center-torque-v1", "rows": rows, "columns": columns,
            "usable_cells": [{"row": r, "column": c} for r, c in cells],
            "inventory": [{"lift": lift, "count": count} for lift, count in stock]})
        expected = brute_force_exists(puzzle)
        result = solve_balloon(puzzle, 3, 300000)
        assert result.outcome == ("solved" if expected else "unsatisfiable")
        if result.solution:
            validate_solution(puzzle, result.solution)


@pytest.mark.parametrize("change", [
    {"rule_version": "special-multiplier-v1"},
    {"unknown": 1},
    {"usable_cells": [{"row": 0, "column": 0}, {"row": 0, "column": 0}]},
    {"usable_cells": [{"row": 5, "column": 0}]},
    {"inventory": [{"lift": 1, "count": 2}, {"lift": 1, "count": 1}]},
    {"inventory": [{"lift": 1, "count": 18}]},
])
def test_invalid_input(change: dict) -> None:
    with pytest.raises(ValidationError):
        BalloonPuzzle.model_validate({**sample(), **change})


def test_work_limit_is_timeout_not_unsatisfiable(monkeypatch: pytest.MonkeyPatch) -> None:
    result = solve_balloon(BalloonPuzzle.model_validate(sample()), 3, 1)
    assert result.outcome == "timeout"
    assert result.limit_reason == "work"
    clock = iter((0.0, 2.0))
    monkeypatch.setattr("app.puzzles.balloon.solve.time", SimpleNamespace(monotonic=lambda: next(clock)))
    timed = solve_balloon(BalloonPuzzle.model_validate(sample()), 1, 300000)
    assert timed.outcome == "timeout"
    assert timed.limit_reason == "time"


def test_http_submission_and_completed_result() -> None:
    app = create_app(Settings(max_workers=1, max_queued=1, solve_time_limit_seconds=3, solve_max_nodes=300000))
    with TestClient(app) as client:
        invalid = client.post("/api/v1/puzzles/balloon/solve", json={**sample(), "rule_version": "other"})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "INVALID_REQUEST"
        created = client.post("/api/v1/puzzles/balloon/solve", json=sample())
        assert created.status_code == 202
        task_id = created.json()["id"]
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            task = client.get(f"/api/v1/tasks/{task_id}").json()
            if task["status"] in ("succeeded", "failed", "cancelled"):
                break
            time.sleep(0.02)
        assert task["status"] == "succeeded", task
        assert task["result"]["outcome"] == "solved"
        solution = BalloonSolution.model_validate(task["result"]["solution"])
        validate_solution(BalloonPuzzle.model_validate(sample()), solution)


def test_http_timeout_finishes_worker_and_releases_slot() -> None:
    app = create_app(Settings(max_workers=1, max_queued=0, solve_max_nodes=1))
    with TestClient(app) as client:
        for _ in range(2):
            created = client.post("/api/v1/puzzles/balloon/solve", json=sample())
            assert created.status_code == 202
            task_id = created.json()["id"]
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                task = client.get(f"/api/v1/tasks/{task_id}").json()
                if task["status"] == "succeeded":
                    break
                time.sleep(0.02)
            assert task["status"] == "succeeded", task
            assert task["result"]["outcome"] == "timeout"
            assert task["result"]["limit_reason"] == "work"
