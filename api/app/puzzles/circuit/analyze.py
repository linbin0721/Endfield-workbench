"""Offline orchestration for complete short-bar circuit screenshots.

This module intentionally has no image decoding, OCR, database, task worker or
HTTP dependency. It composes the deterministic visual stages with the domain
model, bounded solver and independent solution validator.
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import ValidationError

from app.puzzles.circuit.model import (
    RULE_VERSION,
    CircuitCell,
    CircuitChannel,
    CircuitFixedCell,
    CircuitPiece,
    CircuitPuzzle,
    CircuitSolution,
)
from app.puzzles.circuit.solve import solve_circuit
from app.puzzles.circuit.verify import validate_solution
from app.puzzles.circuit.vision import (
    extract_bar_channel_hues,
    extract_bar_stacks,
    extract_bar_targets,
    extract_board_cells,
    extract_inventory,
    group_bar_ensembles,
    locate_bar_board,
)


AnalysisOutcome = Literal["recognized", "incomplete", "no_board", "already_completed"]
_OUTCOMES = {"recognized", "incomplete", "no_board", "already_completed"}


@dataclass(frozen=True)
class BarImageAnalysis:
    """One immutable result of the short-bar-only offline pipeline."""

    outcome: AnalysisOutcome
    puzzle: CircuitPuzzle | None = None
    solution: CircuitSolution | None = None
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.outcome not in _OUTCOMES:
            raise ValueError(f"unknown bar image outcome {self.outcome!r}")
        if not isinstance(self.issues, tuple) or any(
            not isinstance(issue, str) for issue in self.issues
        ):
            raise ValueError("issues must be a tuple of strings")
        if self.outcome == "recognized":
            if not isinstance(self.puzzle, CircuitPuzzle) or not isinstance(
                self.solution, CircuitSolution
            ):
                raise ValueError("recognized analysis must carry a puzzle and solution")
        elif self.puzzle is not None or self.solution is not None:
            raise ValueError("only recognized analysis may carry a puzzle or solution")


def _incomplete(issue: str) -> BarImageAnalysis:
    return BarImageAnalysis(outcome="incomplete", issues=(issue,))


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


def analyze_bar_image(
    image: np.ndarray, *, time_limit_seconds: float, max_nodes: int
) -> BarImageAnalysis:
    """Recognize and solve one already decoded short-bar screenshot.

    Invalid limits and image arguments raise ``ValueError``. Once a board has
    been uniquely located, missing or contradictory visual/domain evidence is
    reported as ``incomplete``. A completed board may omit valid targets, but
    it still needs an independently confirmed empty inventory, unambiguous
    board cells and a placed multi-cell component from the visual layer.
    """
    _validate_limits(time_limit_seconds, max_nodes)

    stacks = extract_bar_stacks(image)
    ensembles = group_bar_ensembles(stacks)
    geometry = locate_bar_board(image, ensembles)
    if geometry is None:
        return BarImageAnalysis(
            outcome="no_board", issues=("short-bar board geometry was not found",)
        )

    channel_hues = extract_bar_channel_hues(geometry, ensembles)
    if channel_hues is None:
        return _incomplete("board-adjacent channel hues are incomplete")
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
            return BarImageAnalysis(
                outcome="already_completed",
                issues=("the board is already completed",),
            )
        return _incomplete("placed board cells require a confirmed empty inventory")
    if inventory_empty or not has_inventory:
        return _incomplete("empty inventory has no completed-board evidence")

    targets = extract_bar_targets(geometry, ensembles)
    if targets is None:
        return _incomplete("short-bar targets are incomplete")
    if targets.channel_hues != channel_hues:
        return _incomplete("channel identities disagree between visual stages")

    blocked_cells: list[CircuitCell] = []
    fixed_cells: list[CircuitFixedCell] = []
    for row_index, row in enumerate(cells.cells):
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
                    row_targets=list(targets.row_targets[index]),
                    column_targets=list(targets.column_targets[index]),
                )
                for index in range(len(targets.channel_hues))
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
                for piece in inventory.pieces
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
    return BarImageAnalysis(
        outcome="recognized",
        puzzle=puzzle,
        solution=solution,
    )
