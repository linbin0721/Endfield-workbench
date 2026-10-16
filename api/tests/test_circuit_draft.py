"""EW-031 draft contract, OCR evidence and HTTP/catalog safety boundaries."""

import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.catalog.circuit_service import CircuitCatalogService
from app.main import create_app
from app.puzzles.circuit import analyze as pipeline
from app.puzzles.circuit.analyze import DecodedImageAnalysis
from app.puzzles.circuit.draft import CircuitDraft
from app.puzzles.circuit.model import CircuitPuzzle, CircuitSolveResult
from app.puzzles.circuit.ocr import PartialSymbolTargets, extract_symbol_targets
from app.puzzles.circuit.recognize import CircuitRecognitionResult
from app.puzzles.circuit.recognize_worker import result_from_analysis
from app.puzzles.circuit.vision import extract_bar_targets
from circuit_catalog_fakes import MemoryCircuitCatalogStore, fake_circuit_recognition_job
from test_circuit_analyze import (
    EMPTY_INVENTORY, HUES, PLACED_CELLS,
    SYMBOL_TARGETS, patch_symbol_pipeline, run_decoded,
)
from test_circuit_api import settings, wait_for_task
from test_circuit_ocr import FakeOCR, glyph, layout
from test_circuit_vision import fixed_geometry, single_channel_ensembles

FIXTURES = Path(__file__).with_name("fixtures")


def payload(name="missing"):
    return json.loads((FIXTURES / f"circuit-draft-{name}.json").read_text())


@pytest.mark.parametrize("name", ["missing", "rejected"])
def test_synthetic_fixtures_roundtrip_but_are_not_domain_puzzles(name):
    result = CircuitRecognitionResult.model_validate(payload(name))
    assert result.outcome == "incomplete" and result.draft is not None
    assert result.puzzle is None and result.display_palette == []
    assert CircuitRecognitionResult.model_validate_json(result.model_dump_json()) == result
    draft = result.draft
    # Removing the draft envelope must not bypass solve validation.
    with pytest.raises(ValidationError):
        CircuitPuzzle(
            rows=draft.rows, columns=draft.columns, rule_version=draft.rule_version,
            channels=[c.model_dump() for c in draft.channels], pieces=draft.pieces,
        )


@pytest.mark.parametrize("outcome", ["recognized", "no_board", "already_completed", "timeout", "invalid_image", "failed"])
def test_only_incomplete_may_carry_a_draft(outcome):
    data = payload()
    data.update(outcome=outcome, notation=None)
    with pytest.raises(ValidationError):
        CircuitRecognitionResult.model_validate(data)


@pytest.mark.parametrize("change", [
    {"rows": True}, {"rows": 2.0}, {"channels": []}, {"pieces": None},
    {"pieces": []}, {"palette": []}, {"cells": []}, {"missing": ["guess"]},
    {"missing": ["row_targets", "row_targets"]}, {"missing": ["rejected"]},
])
def test_draft_rejects_structural_or_reason_corruption(change):
    data = payload()["draft"]
    data.update(change)
    with pytest.raises(ValidationError):
        CircuitDraft.model_validate(data)


@pytest.mark.parametrize("field,value", [
    ("index", 1), ("row_targets", [True, 0]), ("row_targets", [1.5, 0]),
    ("row_targets", [3, 0]), ("row_targets", [None]),
])
def test_targets_are_nullable_strict_integers_with_matching_lengths(field, value):
    data = payload()["draft"]
    data["channels"][0][field] = value
    with pytest.raises(ValidationError):
        CircuitDraft.model_validate(data)


@pytest.mark.parametrize("cell", [
    {"kind": None, "channel": None}, {"kind": "placed", "channel": 0},
    {"kind": "fixed", "channel": None}, {"kind": "fixed", "channel": 1},
    {"kind": "empty", "channel": 0}, {"kind": "blocked", "channel": 0},
])
def test_v1_cells_never_have_unknown_class_or_fixed_channel(cell):
    data = payload()["draft"]
    data["cells"][0] = cell
    with pytest.raises(ValidationError):
        CircuitDraft.model_validate(data)


def test_worker_preserves_draft_but_does_not_export_a_solution_or_top_palette():
    draft = CircuitDraft.model_validate(payload()["draft"])
    result = result_from_analysis(DecodedImageAnalysis(outcome="incomplete", notation="digits", draft=draft))
    assert result.draft == draft
    assert result.puzzle is None and result.display_palette == []
    assert "solution" not in result.model_dump()
    with pytest.raises(ValueError):
        DecodedImageAnalysis(outcome="no_board", draft=draft)


@pytest.mark.parametrize("bad", [("1", 0.89), ("bad", 0.99), None, ("5", 0.99)])
def test_one_ocr_batch_keeps_known_values_and_never_turns_failed_glyph_into_zero(bad):
    source = layout((glyph("row", 0), glyph("column", 0)))
    ocr = FakeOCR([bad, ("2", 0.99)])
    result = extract_symbol_targets(np.zeros((140, 160, 3), dtype=np.uint8), source, ocr, allow_incomplete=True)
    assert isinstance(result, PartialSymbolTargets)
    assert result.row_targets == ((None, 0, 0),)
    assert result.column_targets == ((2, 0, 0, 0),)
    assert len(ocr.text_calls) == 1


def test_known_but_conflicting_ocr_values_remain_editable_and_strict_mode_still_rejects():
    image = np.zeros((140, 160, 3), dtype=np.uint8)
    source = layout((glyph("row", 0), glyph("column", 0)))
    assert extract_symbol_targets(image, source, FakeOCR([("2", .99), ("1", .99)])) is None
    result = extract_symbol_targets(image, source, FakeOCR([("2", .99), ("1", .99)]), allow_incomplete=True)
    assert isinstance(result, PartialSymbolTargets)
    assert result.row_targets[0][0] == 2 and result.column_targets[0][0] == 1


@pytest.mark.parametrize("columns,expected", [
    (((0, 1, 0.), (0, 1, 0.), (3, 1, 0.)), (None, 0, 0, 1)),
    (((0, 5, 0.), (3, 1, 0.)), (None, 0, 0, 1)),
    (((0, 2, 0.), (3, 1, 0.)), (2, 0, 0, 1)),
])
def test_partial_bars_preserve_evidence_without_relaxing_strict_recognition(columns, expected):
    geometry = fixed_geometry()
    ensembles = single_channel_ensembles(geometry, columns, ((0, 1, 0.), (3, 1, 0.)))
    assert extract_bar_targets(geometry, ensembles) is None
    partial = extract_bar_targets(geometry, ensembles, allow_incomplete=True)
    assert partial.column_targets == (expected,)
    assert partial.row_targets == ((1, 0, 0, 1),)


def test_partial_analysis_exports_missing_values_without_calling_solver(monkeypatch):
    partial = PartialSymbolTargets(HUES, ((None, 0),), ((1, 1),), "digits")
    patch_symbol_pipeline(monkeypatch, targets=partial)
    monkeypatch.setattr(pipeline, "solve_circuit", lambda *a: pytest.fail("partial values cannot enter the solver"))
    result = run_decoded()
    assert result.outcome == "incomplete" and result.draft.missing == ["row_targets"]
    assert result.draft.channels[0].row_targets == [None, 0]
    assert result.puzzle is result.solution is None and result.channel_hues == ()


@pytest.mark.parametrize("stage,change", [
    ("cells", None), ("inventory", None), ("inventory", EMPTY_INVENTORY),
    ("cells", PLACED_CELLS),
])
def test_unsafe_board_inventory_or_midstate_still_has_no_draft(monkeypatch, stage, change):
    patch_symbol_pipeline(monkeypatch, **{stage: change})
    result = run_decoded()
    assert result.outcome == "incomplete" and result.draft is None


@pytest.mark.parametrize("reason", ["unsatisfiable", "solver_limit", "validation_failed", "rejected"])
def test_final_gate_failures_return_evidence_without_claiming_recognized(monkeypatch, reason):
    targets = dataclasses.replace(SYMBOL_TARGETS, row_targets=((1, 0),)) if reason == "rejected" else SYMBOL_TARGETS
    patch_symbol_pipeline(monkeypatch, targets=targets)
    if reason in {"unsatisfiable", "solver_limit"}:
        answer = CircuitSolveResult(outcome="unsatisfiable") if reason == "unsatisfiable" else CircuitSolveResult(outcome="timeout", limit_reason="work")
        monkeypatch.setattr(pipeline, "solve_circuit", lambda *a: answer)
    if reason == "validation_failed":
        def reject(*a):
            raise ValueError("synthetic independent validation failure")
        monkeypatch.setattr(pipeline, "validate_solution", reject)
    result = run_decoded()
    assert result.outcome == "incomplete" and result.draft.missing == [reason]
    assert result.puzzle is result.solution is None and result.channel_hues == ()


def test_draft_passes_real_task_http_envelope_without_catalog_record_or_solve_bypass(monkeypatch):
    monkeypatch.setattr("app.main.recognize_circuit_job", fake_circuit_recognition_job)
    store = MemoryCircuitCatalogStore()
    with TestClient(create_app(settings(), circuit_catalog=CircuitCatalogService(store))) as client:
        for name in ("missing", "rejected"):
            data = payload(name)
            data.update(question_code="V40020", question_code_confidence=.99)
            created = client.post("/api/v1/puzzles/circuit/recognize", files={"image": ("mock.json", json.dumps(data).encode(), "image/png")})
            assert created.status_code == 202
            task = wait_for_task(client, created.json()["id"])
            assert task["status"] == "succeeded"
            result = task["result"]
            assert result["draft"] == data["draft"]
            assert result["puzzle"] is None and result["display_palette"] == []
            assert result["catalog"]["recorded"] is False
            assert client.post("/api/v1/puzzles/circuit/solve", json=data["draft"]).status_code == 422
        assert store.records == 0
