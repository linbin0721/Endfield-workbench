"""Presentation-only color contract tests for source circuit."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.catalog.circuit_models import CircuitCatalogCandidate
from app.catalog.circuit_rules import circuit_puzzle_fingerprint
from app.puzzles.circuit.presentation import CircuitDisplayColor
from app.puzzles.circuit.recognize import CircuitRecognitionResult


PUZZLE = {
    "rule_version": "line-count-v1",
    "rows": 2,
    "columns": 2,
    "channels": [
        {"index": 0, "row_targets": [1, 0], "column_targets": [1, 0]},
        {"index": 1, "row_targets": [0, 1], "column_targets": [0, 1]},
    ],
    "blocked_cells": [],
    "fixed_cells": [],
    "pieces": [
        {"channel": 0, "cells": [{"row": 0, "column": 0}]},
        {"channel": 1, "cells": [{"row": 0, "column": 0}]},
    ],
}
PALETTE = [
    {"channel": 0, "hue_degrees": 20.0},
    {"channel": 1, "hue_degrees": 220.5},
]


def recognized(palette: list[dict] = PALETTE) -> dict:
    return {
        "outcome": "recognized",
        "puzzle": PUZZLE,
        "display_palette": palette,
        "notation": "mixed",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"channel": True, "hue_degrees": 20.0},
        {"channel": -1, "hue_degrees": 20.0},
        {"channel": 4, "hue_degrees": 20.0},
        {"channel": 0, "hue_degrees": True},
        {"channel": 0, "hue_degrees": "20"},
        {"channel": 0, "hue_degrees": float("nan")},
        {"channel": 0, "hue_degrees": float("inf")},
        {"channel": 0, "hue_degrees": -0.01},
        {"channel": 0, "hue_degrees": 360.0},
        {"channel": 0, "hue_degrees": 20.0, "future": True},
    ],
)
def test_display_color_rejects_invalid_values(payload: dict) -> None:
    with pytest.raises(ValidationError):
        CircuitDisplayColor.model_validate(payload)


def test_recognition_requires_one_ordered_color_per_puzzle_channel() -> None:
    result = CircuitRecognitionResult.model_validate(recognized())
    assert result.model_dump(mode="json")["display_palette"] == PALETTE
    assert CircuitRecognitionResult.model_validate_json(
        result.model_dump_json()
    ) == result

    invalid_palettes = [
        [],
        [PALETTE[0]],
        [PALETTE[0], PALETTE[0]],
        list(reversed(PALETTE)),
    ]
    for palette in invalid_palettes:
        with pytest.raises(ValidationError, match="palette"):
            CircuitRecognitionResult.model_validate(recognized(palette))


def test_nonrecognized_result_must_not_expose_a_palette() -> None:
    assert CircuitRecognitionResult(outcome="incomplete").display_palette == []
    with pytest.raises(ValidationError, match="display palette"):
        CircuitRecognitionResult(
            outcome="incomplete", display_palette=[PALETTE[0]]
        )


def test_catalog_candidate_allows_legacy_empty_or_complete_palette() -> None:
    now = datetime.now(timezone.utc)
    base = {
        "fingerprint": circuit_puzzle_fingerprint(PUZZLE),
        "puzzle": PUZZLE,
        "status": "provisional",
        "observations": 1,
        "first_seen": now,
        "last_seen": now,
    }
    assert CircuitCatalogCandidate(**base).display_palette == []
    assert CircuitCatalogCandidate(
        **base, display_palette=PALETTE
    ).model_dump(mode="json")["display_palette"] == PALETTE
    with pytest.raises(ValidationError, match="palette"):
        CircuitCatalogCandidate(**base, display_palette=[PALETTE[1]])

    reordered_puzzle = {**PUZZLE, "channels": list(reversed(PUZZLE["channels"]))}
    reordered = {**base, "puzzle": reordered_puzzle}
    assert CircuitCatalogCandidate(
        **reordered, display_palette=PALETTE
    ).display_palette[0].channel == 0
