"""Pure rules, models and service tests for the source-circuit catalog."""

from __future__ import annotations

import copy
import hashlib
import threading
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.catalog.circuit_models import (
    CircuitCatalogCandidate,
    CircuitCatalogEntry,
    CircuitCatalogMatch,
)
from app.catalog.circuit_rules import (
    circuit_puzzle_fingerprint,
    normalize_circuit_code,
)
from app.catalog.circuit_service import CircuitCatalogService
from app.catalog.circuit_store import CircuitObservation
from app.puzzles.circuit.model import CircuitSolveResult
from app.puzzles.circuit.presentation import CircuitDisplayColor
from circuit_catalog_fakes import (
    ExplodingCircuitCatalogStore,
    MemoryCircuitCatalogStore,
    UnavailableCircuitCatalogStore,
)


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
            "cells": [{"row": 0, "column": 0}, {"row": 0, "column": 1}],
        }
    ],
}

VERTICAL_PUZZLE = {
    **PUZZLE,
    "channels": [
        {"index": 0, "row_targets": [1, 1], "column_targets": [2, 0]}
    ],
}

PALETTE = [{"channel": 0, "hue_degrees": 80.0}]


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def direct_observation(
    puzzle: dict,
    image: str,
    hues: tuple[float, ...] | None = None,
) -> CircuitObservation:
    if hues is None:
        hues = tuple(80.0 + index * 100.0 for index in range(len(puzzle["channels"])))
    return CircuitObservation(
        code="V40020",
        image_sha256=digest(image),
        fingerprint=circuit_puzzle_fingerprint(puzzle),
        puzzle=copy.deepcopy(puzzle),
        display_palette=tuple(
            CircuitDisplayColor(channel=index, hue_degrees=hue)
            for index, hue in enumerate(hues)
        ),
    )


def recognition(
    puzzle: dict = PUZZLE,
    *,
    outcome: str = "recognized",
    code: str | None = "V40020",
) -> dict:
    payload = {
        "outcome": outcome,
        "display_palette": [],
        "question_code": code,
        "question_code_confidence": 0.99 if code is not None else None,
        "issues": [],
    }
    if outcome == "recognized":
        payload.update(
            puzzle=copy.deepcopy(puzzle),
            notation="digits",
            display_palette=copy.deepcopy(PALETTE),
        )
    elif outcome not in {"no_board", "timeout", "invalid_image", "failed"}:
        payload["notation"] = "digits"
    return payload


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("V40020", "V40020"),
        ("△-V40020", "V40020"),
        (" ▲ — WL 0020 ", "WL0020"),
        ("∆-WL0020", "WL0020"),
    ],
)
def test_normalize_circuit_code_accepts_frozen_grammar(
    raw: str, expected: str
) -> None:
    assert normalize_circuit_code(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["v40020", "WL-A0020", "V4O020", "V40020 extra", "△--V40020", None],
)
def test_normalize_circuit_code_rejects_guesses(raw: object) -> None:
    assert normalize_circuit_code(raw) is None


def rich_puzzle() -> dict:
    return {
        "rule_version": "line-count-v1",
        "rows": 4,
        "columns": 4,
        "channels": [
            {
                "index": 0,
                "row_targets": [1, 2, 0, 1],
                "column_targets": [3, 1, 0, 0],
            },
            {
                "index": 1,
                "row_targets": [1, 1, 1, 0],
                "column_targets": [0, 0, 3, 0],
            },
        ],
        "blocked_cells": [{"row": 3, "column": 3}],
        "fixed_cells": [{"row": 3, "column": 0, "channel": 0}],
        "pieces": [
            {
                "channel": 0,
                "cells": [
                    {"row": 0, "column": 0},
                    {"row": 1, "column": 0},
                    {"row": 1, "column": 1},
                ],
            },
            {
                "channel": 1,
                "cells": [
                    {"row": 0, "column": 0},
                    {"row": 1, "column": 0},
                ],
            },
            {"channel": 1, "cells": [{"row": 0, "column": 0}]},
        ],
    }


def rotate_shape(cells: list[dict]) -> list[dict]:
    points = [(cell["column"], -cell["row"]) for cell in cells]
    minimum_row = min(row for row, _ in points)
    minimum_column = min(column for _, column in points)
    return [
        {"row": row - minimum_row, "column": column - minimum_column}
        for row, column in reversed(points)
    ]


def test_fingerprint_ignores_all_frozen_equivalences() -> None:
    original = rich_puzzle()
    equivalent = copy.deepcopy(original)
    equivalent["blocked_cells"].reverse()
    equivalent["fixed_cells"].reverse()
    equivalent["channels"].reverse()
    equivalent["pieces"].reverse()
    for piece in equivalent["pieces"]:
        piece["cells"] = rotate_shape(piece["cells"])

    # Globally swap channel names across targets, fixed cells and pieces.
    for channel in equivalent["channels"]:
        channel["index"] = 1 - channel["index"]
    for cell in equivalent["fixed_cells"]:
        cell["channel"] = 1 - cell["channel"]
    for piece in equivalent["pieces"]:
        piece["channel"] = 1 - piece["channel"]

    assert circuit_puzzle_fingerprint(original) == circuit_puzzle_fingerprint(
        equivalent
    )


def test_fingerprint_distinguishes_statement_changes_and_mirrors() -> None:
    original = rich_puzzle()
    variants = []

    changed_blocked = copy.deepcopy(original)
    changed_blocked["blocked_cells"] = [{"row": 2, "column": 3}]
    variants.append(changed_blocked)

    changed_fixed = copy.deepcopy(original)
    changed_fixed["fixed_cells"] = [{"row": 3, "column": 1, "channel": 0}]
    changed_fixed["channels"][0] = {
        "index": 0,
        "row_targets": [1, 2, 0, 1],
        "column_targets": [2, 2, 0, 0],
    }
    variants.append(changed_fixed)

    changed_target = copy.deepcopy(original)
    changed_target["channels"][1] = {
        "index": 1,
        "row_targets": [0, 2, 1, 0],
        "column_targets": [0, 1, 2, 0],
    }
    variants.append(changed_target)

    first = circuit_puzzle_fingerprint(original)
    assert all(circuit_puzzle_fingerprint(item) != first for item in variants)

    s_shape = {
        "rule_version": "line-count-v1",
        "rows": 3,
        "columns": 3,
        "channels": [
            {"index": 0, "row_targets": [2, 2, 0], "column_targets": [1, 2, 1]}
        ],
        "blocked_cells": [],
        "fixed_cells": [],
        "pieces": [{
            "channel": 0,
            "cells": [
                {"row": 0, "column": 1}, {"row": 0, "column": 2},
                {"row": 1, "column": 0}, {"row": 1, "column": 1},
            ],
        }],
    }
    z_shape = copy.deepcopy(s_shape)
    z_shape["pieces"][0]["cells"] = [
        {"row": 0, "column": 0}, {"row": 0, "column": 1},
        {"row": 1, "column": 1}, {"row": 1, "column": 2},
    ]
    assert circuit_puzzle_fingerprint(s_shape) != circuit_puzzle_fingerprint(z_shape)


def test_fingerprint_distinguishes_channel_association() -> None:
    puzzle = {
        "rule_version": "line-count-v1",
        "rows": 3,
        "columns": 3,
        "channels": [
            {"index": 0, "row_targets": [3, 0, 0], "column_targets": [1, 1, 1]},
            {"index": 1, "row_targets": [0, 1, 2], "column_targets": [2, 1, 0]},
        ],
        "blocked_cells": [], "fixed_cells": [],
        "pieces": [
            {"channel": 0, "cells": [
                {"row": 0, "column": 0}, {"row": 0, "column": 1},
                {"row": 0, "column": 2},
            ]},
            {"channel": 1, "cells": [
                {"row": 0, "column": 0}, {"row": 1, "column": 0},
                {"row": 1, "column": 1},
            ]},
        ],
    }
    reassigned = copy.deepcopy(puzzle)
    reassigned["pieces"][0]["channel"] = 1
    reassigned["pieces"][1]["channel"] = 0
    assert circuit_puzzle_fingerprint(puzzle) != circuit_puzzle_fingerprint(reassigned)


def test_catalog_models_enforce_status_and_shape() -> None:
    now = datetime.now(timezone.utc)
    fingerprint = circuit_puzzle_fingerprint(PUZZLE)
    candidate = CircuitCatalogCandidate(
        fingerprint=fingerprint,
        puzzle=PUZZLE,
        status="provisional",
        observations=1,
        first_seen=now,
        last_seen=now,
    )
    entry = CircuitCatalogEntry(
        code="V40020", candidates=[candidate], updated_at=now
    )
    assert entry.candidates[0].status == "provisional"
    with pytest.raises(ValidationError):
        CircuitCatalogCandidate(
            **candidate.model_dump(exclude={"status"}), status="verified"
        )
    with pytest.raises(ValidationError):
        CircuitCatalogEntry(
            code="WL-A0020", candidates=[], updated_at=now, status="provisional"
        )
    with pytest.raises(ValidationError):
        CircuitCatalogMatch(
            code="V40020",
            image_digest_mismatch=True,
            matched_fingerprint=fingerprint,
            matched_status="provisional",
        )


def test_observation_rejects_noncanonical_codes_digests_and_fingerprints() -> None:
    fingerprint = circuit_puzzle_fingerprint(PUZZLE)
    with pytest.raises(ValueError, match="canonical"):
        CircuitObservation(
            "△-V40020",
            digest("x"),
            fingerprint,
            PUZZLE,
            (CircuitDisplayColor(channel=0, hue_degrees=80),),
        )
    with pytest.raises(ValueError, match="digest"):
        CircuitObservation(
            "V40020",
            "not-a-digest",
            fingerprint,
            PUZZLE,
            (CircuitDisplayColor(channel=0, hue_degrees=80),),
        )
    with pytest.raises(ValueError, match="fingerprint"):
        CircuitObservation(
            "V40020",
            digest("x"),
            "0" * 64,
            PUZZLE,
            (CircuitDisplayColor(channel=0, hue_degrees=80),),
        )


def test_first_duplicate_and_second_observation_lifecycle() -> None:
    store = MemoryCircuitCatalogStore()
    service = CircuitCatalogService(store)

    first = service.enrich_recognition(recognition(), digest("one"))["catalog"]
    assert first["recorded"] is True
    assert first["matched_status"] == "provisional"
    assert first["candidates"][0]["observations"] == 1
    assert first["candidates"][0]["display_palette"] == PALETTE

    duplicate = service.enrich_recognition(recognition(), digest("one"))["catalog"]
    assert duplicate["duplicate"] is True and duplicate["recorded"] is False
    assert duplicate["candidates"][0]["observations"] == 1

    verified = service.enrich_recognition(recognition(), digest("two"))["catalog"]
    assert verified["recorded"] is True
    assert verified["matched_status"] == "verified"
    assert verified["candidates"][0]["observations"] == 2
    assert verified["candidates"][0]["display_palette"] == PALETTE


def test_memory_store_never_overwrites_a_nonempty_palette() -> None:
    store = MemoryCircuitCatalogStore()
    first, _ = store.record(direct_observation(PUZZLE, "first", (80.0,)))
    second, disposition = store.record(
        direct_observation(PUZZLE, "second", (240.0,))
    )

    assert disposition == "recorded"
    assert first.candidates[0].display_palette[0].hue_degrees == 80.0
    assert second.candidates[0].display_palette[0].hue_degrees == 80.0
    assert second.candidates[0].observations == 2


def test_memory_store_preserves_each_normal_variants_own_palette() -> None:
    store = MemoryCircuitCatalogStore()
    store.record(direct_observation(PUZZLE, "first", (80.0,)))
    entry, disposition = store.record(
        direct_observation(VERTICAL_PUZZLE, "variant", (240.0,))
    )

    assert disposition == "recorded"
    palettes = {
        candidate.fingerprint: candidate.display_palette[0].hue_degrees
        for candidate in entry.candidates
    }
    assert palettes == {
        circuit_puzzle_fingerprint(PUZZLE): 80.0,
        circuit_puzzle_fingerprint(VERTICAL_PUZZLE): 240.0,
    }


@pytest.mark.parametrize("duplicate", [False, True])
def test_memory_store_safely_backfills_an_exact_legacy_candidate(
    duplicate: bool,
) -> None:
    store = MemoryCircuitCatalogStore()
    store.record(direct_observation(PUZZLE, "first", (80.0,)))
    fingerprint = circuit_puzzle_fingerprint(PUZZLE)
    store._entries["V40020"]["candidates"][fingerprint]["display_palette"] = []

    image = "first" if duplicate else "second"
    entry, disposition = store.record(
        direct_observation(PUZZLE, image, (240.0,))
    )

    assert disposition == ("duplicate" if duplicate else "recorded")
    assert entry.candidates[0].display_palette[0].hue_degrees == 240.0
    assert entry.candidates[0].observations == (1 if duplicate else 2)


def test_memory_store_does_not_backfill_an_equivalent_different_json() -> None:
    store = MemoryCircuitCatalogStore()
    store.record(direct_observation(PUZZLE, "same", (80.0,)))
    fingerprint = circuit_puzzle_fingerprint(PUZZLE)
    store._entries["V40020"]["candidates"][fingerprint]["display_palette"] = []
    reordered = copy.deepcopy(PUZZLE)
    reordered["pieces"][0]["cells"].reverse()
    assert circuit_puzzle_fingerprint(reordered) == fingerprint
    assert reordered != PUZZLE

    entry, disposition = store.record(
        direct_observation(reordered, "same", (240.0,))
    )

    assert disposition == "duplicate"
    assert entry.candidates[0].display_palette == []


def test_memory_store_digest_mismatch_never_backfills_palette() -> None:
    store = MemoryCircuitCatalogStore()
    store.record(direct_observation(PUZZLE, "same", (80.0,)))
    fingerprint = circuit_puzzle_fingerprint(PUZZLE)
    store._entries["V40020"]["candidates"][fingerprint]["display_palette"] = []

    entry, disposition = store.record(
        direct_observation(VERTICAL_PUZZLE, "same", (240.0,))
    )

    assert disposition == "digest_mismatch"
    assert entry.candidates[0].display_palette == []


def test_same_code_variants_are_normal_and_confirm_independently() -> None:
    store = MemoryCircuitCatalogStore()
    service = CircuitCatalogService(store)
    service.enrich_recognition(recognition(PUZZLE), digest("a1"))
    service.enrich_recognition(recognition(VERTICAL_PUZZLE), digest("b1"))
    result = service.enrich_recognition(
        recognition(VERTICAL_PUZZLE), digest("b2")
    )["catalog"]

    assert len(result["candidates"]) == 2
    assert [item["status"] for item in result["candidates"]] == [
        "verified", "provisional"
    ]
    assert result["matched_status"] == "verified"
    assert not any("争议" in issue for issue in result["issues"])

    other = service.enrich_recognition(recognition(PUZZLE), digest("a2"))["catalog"]
    assert [item["status"] for item in other["candidates"]] == [
        "verified", "verified"
    ]


def test_digest_mismatch_preserves_history_without_claiming_match() -> None:
    store = MemoryCircuitCatalogStore()
    service = CircuitCatalogService(store)
    original = service.enrich_recognition(recognition(), digest("same"))["catalog"]
    changed = service.enrich_recognition(
        recognition(VERTICAL_PUZZLE), digest("same")
    )
    match = changed["catalog"]

    assert changed["puzzle"] == VERTICAL_PUZZLE
    assert match["complete"] is True
    assert match["image_digest_mismatch"] is True
    assert match["recorded"] is False and match["duplicate"] is False
    assert match["matched_fingerprint"] is None
    assert len(match["candidates"]) == 1
    assert match["candidates"][0]["fingerprint"] == original["matched_fingerprint"]
    assert store.records == 1


@pytest.mark.parametrize("outcome", ["incomplete", "already_completed", "no_board"])
def test_nonrecognized_results_only_lookup(outcome: str) -> None:
    store = MemoryCircuitCatalogStore()
    service = CircuitCatalogService(store)
    service.enrich_recognition(recognition(), digest("first"))
    result = service.enrich_recognition(
        recognition(outcome=outcome), digest("second")
    )["catalog"]
    assert result["complete"] is False
    assert result["recorded"] is False
    assert len(result["candidates"]) == 1
    assert store.records == 1


def test_nonrecognized_result_lists_multiple_variants_or_none() -> None:
    store = MemoryCircuitCatalogStore()
    service = CircuitCatalogService(store)
    missing = service.enrich_recognition(
        recognition(outcome="incomplete"), digest("missing")
    )["catalog"]
    assert missing["candidates"] == []
    assert any("也没有" in issue for issue in missing["issues"])

    service.enrich_recognition(recognition(PUZZLE), digest("a"))
    service.enrich_recognition(recognition(VERTICAL_PUZZLE), digest("b"))
    variants = service.enrich_recognition(
        recognition(outcome="incomplete"), digest("c")
    )["catalog"]
    assert len(variants["candidates"]) == 2
    assert any("多个正常变体" in issue for issue in variants["issues"])


def test_no_code_never_touches_store() -> None:
    store = MemoryCircuitCatalogStore()
    payload = recognition(code=None)
    result = CircuitCatalogService(store).enrich_recognition(payload, digest("x"))
    assert result == {**payload, "catalog": None}
    assert store.records == 0 and store.lookups == 0


@pytest.mark.parametrize("store", [None, UnavailableCircuitCatalogStore()])
def test_missing_or_unavailable_store_does_not_block_recognition(store) -> None:  # noqa: ANN001
    result = CircuitCatalogService(store).enrich_recognition(
        recognition(), digest("x")
    )
    assert result["outcome"] == "recognized" and result["puzzle"] == PUZZLE
    assert result["catalog"]["available"] is False


def test_unexpected_store_bug_is_not_swallowed() -> None:
    with pytest.raises(RuntimeError, match="unexpected"):
        CircuitCatalogService(ExplodingCircuitCatalogStore()).enrich_recognition(
            recognition(), digest("x")
        )


@pytest.mark.parametrize("outcome", ["unsatisfiable", "timeout"])
def test_unsolved_recheck_does_not_write(
    outcome: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MemoryCircuitCatalogStore()
    reason = "time" if outcome == "timeout" else None
    monkeypatch.setattr(
        "app.catalog.circuit_service.solve_circuit",
        lambda *args: CircuitSolveResult(outcome=outcome, limit_reason=reason),
    )
    result = CircuitCatalogService(store).enrich_recognition(
        recognition(), digest(outcome)
    )["catalog"]
    assert result["complete"] is False and result["recorded"] is False
    assert store.records == 0


def test_independent_validation_failure_does_not_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryCircuitCatalogStore()

    def reject(*args) -> None:  # noqa: ANN002
        raise ValueError("forged solution")

    monkeypatch.setattr("app.catalog.circuit_service.validate_solution", reject)
    result = CircuitCatalogService(store).enrich_recognition(
        recognition(), digest("bad-solution")
    )["catalog"]
    assert result["complete"] is False and result["recorded"] is False
    assert store.records == 0
    assert any("独立校验" in issue for issue in result["issues"])


def test_memory_store_is_idempotent_under_concurrency() -> None:
    store = MemoryCircuitCatalogStore()
    service = CircuitCatalogService(store)
    results: list[dict] = []
    lock = threading.Lock()

    def observe() -> None:
        result = service.enrich_recognition(recognition(), digest("same"))
        with lock:
            results.append(result)

    threads = [threading.Thread(target=observe) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert store.records == 1
    assert sum(item["catalog"]["recorded"] for item in results) == 1
    entry = store.get("V40020")
    assert entry is not None and entry.candidates[0].observations == 1


def test_candidate_order_uses_first_seen_as_stable_tie_break() -> None:
    now = datetime.now(timezone.utc)
    first = CircuitCatalogCandidate(
        fingerprint=circuit_puzzle_fingerprint(PUZZLE), puzzle=PUZZLE,
        status="provisional", observations=1,
        first_seen=now, last_seen=now,
    )
    second = CircuitCatalogCandidate(
        fingerprint=circuit_puzzle_fingerprint(VERTICAL_PUZZLE), puzzle=VERTICAL_PUZZLE,
        status="provisional", observations=1,
        first_seen=now + timedelta(seconds=1), last_seen=now + timedelta(seconds=1),
    )
    assert first.first_seen < second.first_seen
