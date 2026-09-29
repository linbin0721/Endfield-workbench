"""Offline short-bar circuit orchestration coverage (EW-006 B1b3c)."""

import dataclasses

import numpy as np
import pytest

from app.puzzles.circuit import analyze as analyze_module
from app.puzzles.circuit.analyze import BarImageAnalysis, analyze_bar_image
from app.puzzles.circuit.model import (
    CircuitPlacement,
    CircuitSolution,
    CircuitSolveResult,
)
from app.puzzles.circuit.verify import validate_solution
from app.puzzles.circuit.vision import (
    BarTargets,
    BoardCellMap,
    BoardGeometry,
    CellClass,
    InventoryPiece,
    InventoryState,
)


IMAGE = np.zeros((20, 20, 3), dtype=np.uint8)
HUES = (10.0,)
GEOMETRY = BoardGeometry(
    left=0.0,
    top=0.0,
    right=20.0,
    bottom=20.0,
    step=10.0,
    rows=2,
    columns=2,
    row_centers=(5.0, 15.0),
    column_centers=(5.0, 15.0),
    evidence_ratio=1.0,
    score_margin=1.0,
)
TARGETS = BarTargets(
    channel_hues=HUES,
    row_targets=((2, 0),),
    column_targets=((1, 1),),
    residual_ratio=0.0,
)
EMPTY_CELLS = BoardCellMap(
    cells=(
        (
            CellClass(kind="empty", channel=None, confidence=1.0),
            CellClass(kind="empty", channel=None, confidence=1.0),
        ),
        (
            CellClass(kind="empty", channel=None, confidence=1.0),
            CellClass(kind="empty", channel=None, confidence=1.0),
        ),
    ),
    minimum_confidence=1.0,
)
PLACED_CELLS = BoardCellMap(
    cells=(
        (
            CellClass(kind="placed", channel=0, confidence=1.0),
            CellClass(kind="placed", channel=0, confidence=1.0),
        ),
        EMPTY_CELLS.cells[1],
    ),
    minimum_confidence=1.0,
)
PIECE = InventoryPiece(
    slot_index=0,
    channel=0,
    cells=((0, 0), (0, 1)),
    rows=1,
    columns=2,
    iou=1.0,
    center_x=1.0,
    center_y=1.0,
)
INVENTORY = InventoryState(
    slot_count=1,
    empty_count=0,
    pieces=(PIECE,),
    minimum_confidence=1.0,
)
EMPTY_INVENTORY = InventoryState(
    slot_count=1,
    empty_count=1,
    pieces=(),
    minimum_confidence=1.0,
)


def patch_visual_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    geometry: BoardGeometry | None = GEOMETRY,
    hues: tuple[float, ...] | None = HUES,
    cells: BoardCellMap | None = EMPTY_CELLS,
    inventory: InventoryState | None = INVENTORY,
    targets: BarTargets | None = TARGETS,
) -> None:
    monkeypatch.setattr(analyze_module, "extract_bar_stacks", lambda image: ("stack",))
    monkeypatch.setattr(
        analyze_module, "group_bar_ensembles", lambda stacks: ("ensemble",)
    )
    monkeypatch.setattr(
        analyze_module,
        "locate_bar_board",
        lambda image, ensembles: geometry,
    )
    monkeypatch.setattr(
        analyze_module,
        "extract_bar_channel_hues",
        lambda board, ensembles: hues,
    )
    monkeypatch.setattr(
        analyze_module,
        "extract_board_cells",
        lambda image, board, channel_hues: cells,
    )
    monkeypatch.setattr(
        analyze_module,
        "extract_inventory",
        lambda image, board, channel_hues: inventory,
    )
    monkeypatch.setattr(
        analyze_module,
        "extract_bar_targets",
        lambda board, ensembles: targets,
    )


def run_analysis() -> BarImageAnalysis:
    return analyze_bar_image(IMAGE, time_limit_seconds=1.0, max_nodes=10_000)


def test_recognized_result_builds_solves_and_independently_validates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_visual_pipeline(monkeypatch)

    result = run_analysis()

    assert result.outcome == "recognized"
    assert result.puzzle is not None
    assert result.solution is not None
    assert result.issues == ()
    assert result.puzzle.rows == result.puzzle.columns == 2
    assert [(cell.row, cell.column) for cell in result.puzzle.blocked_cells] == []
    assert result.puzzle.pieces[0].channel == 0
    validate_solution(result.puzzle, result.solution)


def test_recognized_result_maps_blocked_and_fixed_cells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cells = BoardCellMap(
        cells=(
            EMPTY_CELLS.cells[0],
            (
                CellClass(kind="fixed", channel=0, confidence=1.0),
                CellClass(kind="blocked", channel=None, confidence=1.0),
            ),
        ),
        minimum_confidence=1.0,
    )
    targets = dataclasses.replace(
        TARGETS,
        row_targets=((2, 1),),
        column_targets=((2, 1),),
    )
    patch_visual_pipeline(monkeypatch, cells=cells, targets=targets)

    result = run_analysis()

    assert result.outcome == "recognized"
    assert result.puzzle is not None and result.solution is not None
    assert [(cell.row, cell.column) for cell in result.puzzle.blocked_cells] == [
        (1, 1)
    ]
    assert [
        (cell.row, cell.column, cell.channel) for cell in result.puzzle.fixed_cells
    ] == [(1, 0, 0)]
    validate_solution(result.puzzle, result.solution)


def test_no_board_is_the_only_pre_geometry_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_visual_pipeline(monkeypatch, geometry=None)

    result = run_analysis()

    assert result.outcome == "no_board"
    assert result.puzzle is result.solution is None


def test_completed_board_does_not_require_decodable_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_visual_pipeline(
        monkeypatch,
        cells=PLACED_CELLS,
        inventory=EMPTY_INVENTORY,
        targets=None,
    )
    monkeypatch.setattr(
        analyze_module,
        "extract_bar_targets",
        lambda board, ensembles: pytest.fail("completion must not decode targets"),
    )

    result = run_analysis()

    assert result.outcome == "already_completed"
    assert result.puzzle is result.solution is None


def test_placed_cells_with_inventory_are_a_mid_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_visual_pipeline(monkeypatch, cells=PLACED_CELLS)

    result = run_analysis()

    assert result.outcome == "incomplete"
    assert "mid-state" in result.issues[0]
    assert result.puzzle is result.solution is None


def test_empty_inventory_without_placed_cells_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_visual_pipeline(monkeypatch, inventory=EMPTY_INVENTORY)

    result = run_analysis()

    assert result.outcome == "incomplete"
    assert "no completed-board evidence" in result.issues[0]


@pytest.mark.parametrize(
    ("stage", "issue"),
    [
        ("hues", "channel hues"),
        ("cells", "cell classification"),
        ("inventory", "inventory recognition"),
        ("targets", "targets"),
    ],
)
def test_incomplete_visual_stage_returns_no_partial_statement(
    monkeypatch: pytest.MonkeyPatch, stage: str, issue: str
) -> None:
    values = {
        "hues": HUES,
        "cells": EMPTY_CELLS,
        "inventory": INVENTORY,
        "targets": TARGETS,
    }
    values[stage] = None
    patch_visual_pipeline(
        monkeypatch,
        hues=values["hues"],  # type: ignore[arg-type]
        cells=values["cells"],  # type: ignore[arg-type]
        inventory=values["inventory"],  # type: ignore[arg-type]
        targets=values["targets"],  # type: ignore[arg-type]
    )

    result = run_analysis()

    assert result.outcome == "incomplete"
    assert issue in result.issues[0]
    assert result.puzzle is result.solution is None


def test_domain_model_rejection_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_targets = dataclasses.replace(
        TARGETS,
        row_targets=((1, 0),),
        column_targets=((1, 0),),
    )
    patch_visual_pipeline(monkeypatch, targets=invalid_targets)

    result = run_analysis()

    assert result.outcome == "incomplete"
    assert "domain model rejected" in result.issues[0]
    assert result.puzzle is result.solution is None


def test_unsatisfiable_statement_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_visual_pipeline(monkeypatch)
    monkeypatch.setattr(
        analyze_module,
        "solve_circuit",
        lambda puzzle, seconds, nodes: CircuitSolveResult(outcome="unsatisfiable"),
    )

    result = run_analysis()

    assert result.outcome == "incomplete"
    assert "unsatisfiable" in result.issues[0]


@pytest.mark.parametrize("reason", ["time", "work"])
def test_solver_limits_are_incomplete(
    monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    patch_visual_pipeline(monkeypatch)
    monkeypatch.setattr(
        analyze_module,
        "solve_circuit",
        lambda puzzle, seconds, nodes: CircuitSolveResult(
            outcome="timeout", limit_reason=reason
        ),
    )

    result = run_analysis()

    assert result.outcome == "incomplete"
    assert reason in result.issues[0]


def test_independent_validation_failure_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_visual_pipeline(monkeypatch)
    solution = CircuitSolution(
        placements=[CircuitPlacement(piece_index=0, row=0, column=0, rotation=0)]
    )
    monkeypatch.setattr(
        analyze_module,
        "solve_circuit",
        lambda puzzle, seconds, nodes: CircuitSolveResult(
            outcome="solved", solution=solution
        ),
    )

    def reject(puzzle, candidate) -> None:
        raise ValueError("forged solution")

    monkeypatch.setattr(analyze_module, "validate_solution", reject)

    result = run_analysis()

    assert result.outcome == "incomplete"
    assert "independent solution validation failed" in result.issues[0]
    assert result.puzzle is result.solution is None


@pytest.mark.parametrize(
    ("seconds", "nodes"),
    [
        (0.0, 1),
        (-1.0, 1),
        (float("nan"), 1),
        (True, 1),
        (1.0, 0),
        (1.0, -1),
        (1.0, 1.5),
        (1.0, True),
    ],
)
def test_invalid_limits_raise_value_error(seconds: object, nodes: object) -> None:
    with pytest.raises(ValueError):
        analyze_bar_image(
            IMAGE,
            time_limit_seconds=seconds,  # type: ignore[arg-type]
            max_nodes=nodes,  # type: ignore[arg-type]
        )


def test_visual_programming_errors_are_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_visual_pipeline(monkeypatch)

    def fail(image, board, channel_hues):
        raise RuntimeError("visual bug")

    monkeypatch.setattr(analyze_module, "extract_board_cells", fail)
    with pytest.raises(RuntimeError, match="visual bug"):
        run_analysis()


def test_bar_image_analysis_is_frozen_and_enforces_result_invariants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_visual_pipeline(monkeypatch)
    recognized = run_analysis()
    assert BarImageAnalysis.__dataclass_params__.frozen is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        recognized.outcome = "incomplete"  # type: ignore[misc]
    with pytest.raises(ValueError, match="unknown"):
        BarImageAnalysis(outcome="failed")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must carry"):
        BarImageAnalysis(outcome="recognized")
    with pytest.raises(ValueError, match="only recognized"):
        BarImageAnalysis(outcome="incomplete", puzzle=recognized.puzzle)
    with pytest.raises(ValueError, match="tuple of strings"):
        BarImageAnalysis(outcome="incomplete", issues=["bad"])  # type: ignore[arg-type]
