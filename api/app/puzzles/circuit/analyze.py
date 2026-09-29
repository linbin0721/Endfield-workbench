"""Offline orchestration for already decoded circuit screenshots.

This module intentionally has no image decoding, OCR model construction,
database, task worker or HTTP dependency. It composes deterministic visual
stages with the domain model, bounded solver and independent validator.
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import ValidationError

from app.catalog.circuit_rules import normalize_circuit_code
from app.puzzles.circuit.model import (
    RULE_VERSION,
    CircuitCell,
    CircuitChannel,
    CircuitFixedCell,
    CircuitPiece,
    CircuitPuzzle,
    CircuitSolution,
)
from app.puzzles.circuit.ocr import (
    SymbolTargets,
    extract_symbol_targets,
    read_circuit_question_code,
)
from app.puzzles.circuit.solve import solve_circuit
from app.puzzles.circuit.verify import validate_solution
from app.puzzles.circuit.vision import (
    BoardCellMap,
    BoardGeometry,
    InventoryState,
    extract_bar_channel_hues,
    extract_bar_stacks,
    extract_bar_targets,
    extract_board_cells,
    extract_inventory,
    group_bar_ensembles,
    locate_bar_board,
    locate_symbol_board,
)


AnalysisOutcome = Literal["recognized", "incomplete", "no_board", "already_completed"]
RecognitionNotation = Literal["bars", "digits", "roman", "mixed"]
_OUTCOMES = {"recognized", "incomplete", "no_board", "already_completed"}


@dataclass(frozen=True)
class BarImageAnalysis:
    """One immutable result of the short-bar-only offline pipeline."""

    outcome: AnalysisOutcome
    puzzle: CircuitPuzzle | None = None
    solution: CircuitSolution | None = None
    channel_hues: tuple[float, ...] = ()
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_analysis_fields(
            self.outcome,
            self.puzzle,
            self.solution,
            self.channel_hues,
            self.issues,
            "bar image",
        )


@dataclass(frozen=True)
class DecodedImageAnalysis:
    """Immutable OCR-aware result for one already decoded BGR screenshot."""

    outcome: AnalysisOutcome
    notation: RecognitionNotation | None = None
    question_code: str | None = None
    question_code_confidence: float | None = None
    puzzle: CircuitPuzzle | None = None
    solution: CircuitSolution | None = None
    channel_hues: tuple[float, ...] = ()
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_analysis_fields(
            self.outcome,
            self.puzzle,
            self.solution,
            self.channel_hues,
            self.issues,
            "decoded image",
        )
        if self.notation not in {None, "bars", "digits", "roman", "mixed"}:
            raise ValueError(f"unknown decoded image notation {self.notation!r}")
        if self.outcome == "recognized" and self.notation is None:
            raise ValueError("recognized decoded analysis must have notation")
        if self.outcome == "no_board" and self.notation is not None:
            raise ValueError("a no_board decoded analysis cannot have notation")
        if self.question_code is None:
            if self.question_code_confidence is not None:
                raise ValueError("a missing question code cannot have confidence")
        else:
            if normalize_circuit_code(self.question_code) != self.question_code:
                raise ValueError("a question code must already be canonical")
            if (
                isinstance(self.question_code_confidence, bool)
                or not isinstance(self.question_code_confidence, numbers.Real)
                or not math.isfinite(float(self.question_code_confidence))
                or not 0.0 <= float(self.question_code_confidence) <= 1.0
            ):
                raise ValueError("question code confidence must be finite in 0..1")


@dataclass(frozen=True)
class _CoreAnalysis:
    outcome: AnalysisOutcome
    puzzle: CircuitPuzzle | None = None
    solution: CircuitSolution | None = None
    channel_hues: tuple[float, ...] = ()
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_analysis_fields(
            self.outcome,
            self.puzzle,
            self.solution,
            self.channel_hues,
            self.issues,
            "core",
        )


@dataclass(frozen=True)
class _BoardInputs:
    cells: BoardCellMap
    inventory: InventoryState


def _validate_analysis_fields(
    outcome: str,
    puzzle: CircuitPuzzle | None,
    solution: CircuitSolution | None,
    channel_hues: tuple[float, ...],
    issues: tuple[str, ...],
    label: str,
) -> None:
    if outcome not in _OUTCOMES:
        raise ValueError(f"unknown {label} outcome {outcome!r}")
    if not isinstance(issues, tuple) or any(
        not isinstance(issue, str) for issue in issues
    ):
        raise ValueError("issues must be a tuple of strings")
    if not isinstance(channel_hues, tuple) or any(
        isinstance(hue, bool)
        or not isinstance(hue, numbers.Real)
        or not math.isfinite(float(hue))
        or not 0.0 <= float(hue) < 180.0
        for hue in channel_hues
    ):
        raise ValueError("channel hues must be a tuple of finite OpenCV hues")
    if outcome == "recognized":
        if not isinstance(puzzle, CircuitPuzzle) or not isinstance(
            solution, CircuitSolution
        ):
            raise ValueError("recognized analysis must carry a puzzle and solution")
        expected = [channel.index for channel in puzzle.channels]
        if len(channel_hues) != len(expected) or list(range(len(channel_hues))) != expected:
            raise ValueError("recognized analysis hues must match puzzle channels")
        if any(
            float(channel_hues[index]) >= float(channel_hues[index + 1])
            for index in range(len(channel_hues) - 1)
        ):
            raise ValueError("recognized analysis hues must be strictly ascending")
    elif puzzle is not None or solution is not None or channel_hues:
        raise ValueError("only recognized analysis may carry a puzzle, solution or hues")


def _incomplete(issue: str) -> _CoreAnalysis:
    return _CoreAnalysis(outcome="incomplete", issues=(issue,))


def _validate_limits(time_limit_seconds: float, max_nodes: int) -> None:
    if (
        isinstance(time_limit_seconds, bool)
        or not isinstance(time_limit_seconds, numbers.Real)
        or not math.isfinite(float(time_limit_seconds))
        or float(time_limit_seconds) <= 0.0
    ):
        raise ValueError("time_limit_seconds must be a positive finite number")
    if isinstance(max_nodes, bool) or not isinstance(max_nodes, int) or max_nodes < 1:
        raise ValueError("max_nodes must be a positive integer")


def _inspect_board(
    image: np.ndarray,
    geometry: BoardGeometry,
    channel_hues: tuple[float, ...],
) -> _BoardInputs | _CoreAnalysis:
    """Apply the shared cell, inventory and completion-state semantics."""
    cells = extract_board_cells(image, geometry, channel_hues)
    if cells is None:
        return _incomplete("board cell classification is incomplete")
    inventory = extract_inventory(image, geometry, channel_hues)
    if inventory is None:
        return _incomplete("inventory recognition is incomplete")

    has_placed = any(cell.kind == "placed" for row in cells.cells for cell in row)
    has_inventory = bool(inventory.pieces)
    inventory_empty = (
        inventory.slot_count > 0
        and inventory.empty_count == inventory.slot_count
        and not inventory.pieces
    )
    if has_placed:
        if has_inventory:
            return _incomplete("board and inventory describe a mid-state")
        if inventory_empty:
            return _CoreAnalysis(
                outcome="already_completed",
                issues=("the board is already completed",),
            )
        return _incomplete("placed board cells require a confirmed empty inventory")
    if inventory_empty or not has_inventory:
        return _incomplete("empty inventory has no completed-board evidence")
    return _BoardInputs(cells=cells, inventory=inventory)


def _build_and_solve(
    geometry: BoardGeometry,
    channel_hues: tuple[float, ...],
    row_targets: tuple[tuple[int, ...], ...],
    column_targets: tuple[tuple[int, ...], ...],
    board: _BoardInputs,
    *,
    time_limit_seconds: float,
    max_nodes: int,
) -> _CoreAnalysis:
    """Build the domain statement and enforce the common final solve gates."""
    blocked_cells: list[CircuitCell] = []
    fixed_cells: list[CircuitFixedCell] = []
    for row_index, row in enumerate(board.cells.cells):
        for column_index, cell in enumerate(row):
            if cell.kind == "blocked":
                blocked_cells.append(CircuitCell(row=row_index, column=column_index))
            elif cell.kind == "fixed":
                if cell.channel is None:
                    return _incomplete("fixed board cell has no channel")
                fixed_cells.append(
                    CircuitFixedCell(
                        row=row_index,
                        column=column_index,
                        channel=cell.channel,
                    )
                )

    try:
        puzzle = CircuitPuzzle(
            rule_version=RULE_VERSION,
            rows=geometry.rows,
            columns=geometry.columns,
            channels=[
                CircuitChannel(
                    index=index,
                    row_targets=list(row_targets[index]),
                    column_targets=list(column_targets[index]),
                )
                for index in range(len(channel_hues))
            ],
            blocked_cells=blocked_cells,
            fixed_cells=fixed_cells,
            pieces=[
                CircuitPiece(
                    channel=piece.channel,
                    cells=[
                        CircuitCell(row=row, column=column)
                        for row, column in piece.cells
                    ],
                )
                for piece in board.inventory.pieces
            ],
        )
    except ValidationError as error:
        issue_type = error.errors()[0]["type"]
        return _incomplete(f"domain model rejected the recognized statement: {issue_type}")

    result = solve_circuit(puzzle, float(time_limit_seconds), max_nodes)
    if result.outcome == "unsatisfiable":
        return _incomplete("recognized statement is unsatisfiable")
    if result.outcome == "timeout":
        return _incomplete(f"solver reached its {result.limit_reason} limit")
    solution = result.solution
    if solution is None:
        raise RuntimeError("solver returned solved without a solution")
    try:
        validate_solution(puzzle, solution)
    except ValueError as error:
        return _incomplete(f"independent solution validation failed: {error}")
    return _CoreAnalysis(
        outcome="recognized",
        puzzle=puzzle,
        solution=solution,
        channel_hues=tuple(float(hue) for hue in channel_hues),
    )


def _analyze_bar_core(
    image: np.ndarray,
    *,
    time_limit_seconds: float,
    max_nodes: int,
) -> tuple[_CoreAnalysis, BoardGeometry | None]:
    stacks = extract_bar_stacks(image)
    ensembles = group_bar_ensembles(stacks)
    geometry = locate_bar_board(image, ensembles)
    if geometry is None:
        return (
            _CoreAnalysis(
                outcome="no_board",
                issues=("short-bar board geometry was not found",),
            ),
            None,
        )

    channel_hues = extract_bar_channel_hues(geometry, ensembles)
    if channel_hues is None:
        return _incomplete("board-adjacent channel hues are incomplete"), geometry
    state = _inspect_board(image, geometry, channel_hues)
    if isinstance(state, _CoreAnalysis):
        return state, geometry

    targets = extract_bar_targets(geometry, ensembles)
    if targets is None:
        return _incomplete("short-bar targets are incomplete"), geometry
    if targets.channel_hues != channel_hues:
        return (
            _incomplete("channel identities disagree between visual stages"),
            geometry,
        )
    return (
        _build_and_solve(
            geometry,
            channel_hues,
            targets.row_targets,
            targets.column_targets,
            state,
            time_limit_seconds=time_limit_seconds,
            max_nodes=max_nodes,
        ),
        geometry,
    )


def _analyze_symbol_core(
    targets: SymbolTargets | None,
    geometry: BoardGeometry,
    channel_hues: tuple[float, ...],
    state: _BoardInputs,
    *,
    time_limit_seconds: float,
    max_nodes: int,
) -> tuple[_CoreAnalysis, RecognitionNotation | None]:
    if targets is None:
        return _incomplete("symbol targets are incomplete"), None
    if targets.channel_hues != channel_hues:
        return _incomplete("channel identities disagree between visual stages"), None
    return (
        _build_and_solve(
            geometry,
            channel_hues,
            targets.row_targets,
            targets.column_targets,
            state,
            time_limit_seconds=time_limit_seconds,
            max_nodes=max_nodes,
        ),
        targets.notation,
    )


def analyze_bar_image(
    image: np.ndarray, *, time_limit_seconds: float, max_nodes: int
) -> BarImageAnalysis:
    """Recognize and solve one already decoded short-bar screenshot."""
    _validate_limits(time_limit_seconds, max_nodes)
    core, _ = _analyze_bar_core(
        image,
        time_limit_seconds=time_limit_seconds,
        max_nodes=max_nodes,
    )
    return BarImageAnalysis(
        outcome=core.outcome,
        puzzle=core.puzzle,
        solution=core.solution,
        channel_hues=core.channel_hues,
        issues=core.issues,
    )


def analyze_decoded_image(
    image: np.ndarray,
    ocr: object,
    *,
    time_limit_seconds: float,
    max_nodes: int,
) -> DecodedImageAnalysis:
    """Recognize either symbol or bar notation in one decoded BGR image."""
    _validate_limits(time_limit_seconds, max_nodes)

    layout = locate_symbol_board(image)
    notation: RecognitionNotation | None = None
    geometry: BoardGeometry | None
    if layout is not None:
        geometry = layout.geometry
        state = _inspect_board(image, geometry, layout.channel_hues)
        if isinstance(state, _CoreAnalysis):
            core = state
        else:
            targets = extract_symbol_targets(image, layout, ocr)
            core, notation = _analyze_symbol_core(
                targets,
                geometry,
                layout.channel_hues,
                state,
                time_limit_seconds=time_limit_seconds,
                max_nodes=max_nodes,
            )
    else:
        core, geometry = _analyze_bar_core(
            image,
            time_limit_seconds=time_limit_seconds,
            max_nodes=max_nodes,
        )
        if geometry is not None:
            notation = "bars"

    code = read_circuit_question_code(image, geometry, ocr)
    issues = list(core.issues)
    if code.ambiguous:
        issues.append("question code recognition is ambiguous")
    elif code.saw_code_like and code.code is None:
        issues.append("question code confidence is too low")
    return DecodedImageAnalysis(
        outcome=core.outcome,
        notation=notation,
        question_code=code.code,
        question_code_confidence=code.confidence,
        puzzle=core.puzzle,
        solution=core.solution,
        channel_hues=core.channel_hues,
        issues=tuple(issues),
    )
