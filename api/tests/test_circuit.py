"""Synthetic coverage for the ``line-count-v1`` domain core (EW-006 batch A).

The fixtures build statements from a concrete covering, and the small cases are
cross-checked against a test-local exhaustive enumerator so solver outcomes do
not depend on the solver's own candidate tables.
"""

import copy
import json
import pickle
import random
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.puzzles.circuit.model import (
    CircuitPlacement,
    CircuitPuzzle,
    CircuitSolution,
    CircuitSolveResult,
)
from app.puzzles.circuit.solve import _piece_orientations, solve_circuit, solve_circuit_job
from app.puzzles.circuit.verify import validate_solution


ROTATIONS = (0, 90, 180, 270)
SOLVE_SECONDS = 5.0
SOLVE_NODES = 500_000


# ---------------------------------------------------------------------------
# fixtures and independent helpers


def rotate(cells, rotation):
    """Rotate local cells clockwise and re-normalize; test-side only."""
    current = sorted(cells)
    for _ in range(rotation // 90):
        current = [(column, -row) for row, column in current]
        min_row = min(row for row, _ in current)
        min_column = min(column for _, column in current)
        current = sorted((row - min_row, column - min_column) for row, column in current)
    return tuple(current)


def statement(rows, columns, channels, pieces, blocked=(), fixed=()):
    """Raw statement dict; channels is a list of (index, row_targets, column_targets)."""
    return {
        "rule_version": "line-count-v1",
        "rows": rows,
        "columns": columns,
        "channels": [
            {"index": index, "row_targets": row_targets, "column_targets": column_targets}
            for index, row_targets, column_targets in channels
        ],
        "blocked_cells": [{"row": row, "column": column} for row, column in blocked],
        "fixed_cells": [
            {"row": row, "column": column, "channel": channel} for row, column, channel in fixed
        ],
        "pieces": [
            {"channel": channel, "cells": [{"row": row, "column": column} for row, column in cells]}
            for channel, cells in pieces
        ],
    }


def build(rows, columns, channel_count, pieces, layout, blocked=(), fixed=()):
    """Statement whose targets come from a concrete covering layout.

    ``pieces`` is a list of (channel, local cells); ``layout`` is a list of
    (piece_index, row, column, rotation); ``fixed`` is (row, column, channel).
    """
    row_targets = [[0] * rows for _ in range(channel_count)]
    column_targets = [[0] * columns for _ in range(channel_count)]
    for index, row, column, rotation in layout:
        channel = pieces[index][0]
        for local_row, local_column in rotate(pieces[index][1], rotation):
            row_targets[channel][row + local_row] += 1
            column_targets[channel][column + local_column] += 1
    for row, column, channel in fixed:
        row_targets[channel][row] += 1
        column_targets[channel][column] += 1
    channels = [(index, row_targets[index], column_targets[index]) for index in range(channel_count)]
    return statement(rows, columns, channels, pieces, blocked, fixed)


def coverage_of(puzzle: CircuitPuzzle, solution: CircuitSolution) -> dict[tuple[int, int], int]:
    """Rebuild the board with the test-side rotation, independent of the solver."""
    coverage: dict[tuple[int, int], int] = {}
    for placement in solution.placements:
        piece = puzzle.pieces[placement.piece_index]
        for row, column in rotate([(cell.row, cell.column) for cell in piece.cells], placement.rotation):
            coverage[(placement.row + row, placement.column + column)] = piece.channel
    return coverage


def brute_force_solvable(puzzle: CircuitPuzzle) -> bool:
    """Exhaustive enumerator for small boards used as an independent oracle."""
    blocked = {(cell.row, cell.column) for cell in puzzle.blocked_cells}
    fixed = {(cell.row, cell.column): cell.channel for cell in puzzle.fixed_cells}
    targets = {
        channel.index: (tuple(channel.row_targets), tuple(channel.column_targets))
        for channel in puzzle.channels
    }
    row_counts = {index: [0] * puzzle.rows for index in targets}
    column_counts = {index: [0] * puzzle.columns for index in targets}
    covered = set(fixed)
    for (row, column), channel in fixed.items():
        row_counts[channel][row] += 1
        column_counts[channel][column] += 1

    options = []
    for piece in puzzle.pieces:
        placements = []
        seen = set()
        current = tuple(sorted((cell.row, cell.column) for cell in piece.cells))
        for rotation in ROTATIONS:
            if rotation:
                current = rotate(current, 90)
            if current in seen:
                continue
            seen.add(current)
            height = max(row for row, _ in current) + 1
            width = max(column for _, column in current) + 1
            for row in range(puzzle.rows - height + 1):
                for column in range(puzzle.columns - width + 1):
                    cells = tuple((row + local_row, column + local_column) for local_row, local_column in current)
                    if any(cell in blocked for cell in cells):
                        continue
                    placements.append(cells)
        options.append(placements)

    def complete(index: int) -> bool:
        if index == len(puzzle.pieces):
            return all(
                tuple(row_counts[key]) == targets[key][0] and tuple(column_counts[key]) == targets[key][1]
                for key in targets
            )
        channel = puzzle.pieces[index].channel
        for cells in options[index]:
            if any(cell in covered for cell in cells):
                continue
            added_rows = [0] * puzzle.rows
            added_columns = [0] * puzzle.columns
            for row, column in cells:
                added_rows[row] += 1
                added_columns[column] += 1
            if any(row_counts[channel][row] + added_rows[row] > targets[channel][0][row] for row in range(puzzle.rows)):
                continue
            if any(
                column_counts[channel][column] + added_columns[column] > targets[channel][1][column]
                for column in range(puzzle.columns)
            ):
                continue
            for row, column in cells:
                covered.add((row, column))
                row_counts[channel][row] += 1
                column_counts[channel][column] += 1
            if complete(index + 1):
                return True
            for row, column in cells:
                covered.discard((row, column))
                row_counts[channel][row] -= 1
                column_counts[channel][column] -= 1
        return False

    return complete(0)


def fits_board(shape, rows: int, columns: int) -> bool:
    height = max(row for row, _ in shape) + 1
    width = max(column for _, column in shape) + 1
    return (height <= rows and width <= columns) or (width <= rows and height <= columns)


def random_shape(size: int, rng) -> tuple[tuple[int, int], ...]:
    cells = {(0, 0)}
    while len(cells) < size:
        row, column = rng.choice(sorted(cells))
        step_row, step_column = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        cells.add((row + step_row, column + step_column))
    min_row = min(row for row, _ in cells)
    min_column = min(column for _, column in cells)
    return tuple(sorted((row - min_row, column - min_column) for row, column in cells))


def random_statement(rng):
    """Deterministic small statement, mostly satisfiable, sometimes reshaped to be unsolvable."""
    rows = rng.randint(2, 4)
    columns = rng.randint(2, 4)
    channel_count = rng.randint(1, 2)
    blocked = {(row, column) for row in range(rows) for column in range(columns) if rng.random() < 0.12}
    pieces = []
    layout = []
    occupied = set()
    for _ in range(rng.randint(1, 4)):
        channel = rng.randrange(channel_count)
        shape = random_shape(rng.randint(1, 4), rng)
        if not fits_board(shape, rows, columns):
            continue
        orientations = []
        seen = set()
        current = shape
        for rotation in ROTATIONS:
            if rotation:
                current = rotate(current, 90)
            if current in seen:
                continue
            seen.add(current)
            orientations.append((rotation, current))
        rng.shuffle(orientations)
        placed = False
        for rotation, cells in orientations:
            height = max(row for row, _ in cells) + 1
            width = max(column for _, column in cells) + 1
            anchors = [
                (row, column)
                for row in range(rows - height + 1)
                for column in range(columns - width + 1)
            ]
            rng.shuffle(anchors)
            for anchor_row, anchor_column in anchors:
                absolute = {(anchor_row + row, anchor_column + column) for row, column in cells}
                if absolute & occupied or absolute & blocked:
                    continue
                occupied |= absolute
                layout.append((len(pieces), channel, anchor_row, anchor_column, rotation))
                pieces.append((channel, shape))
                placed = True
                break
            if placed:
                break
    if not pieces:
        return None
    layout_shapes = list(pieces)
    if rng.random() < 0.5:
        index = rng.randrange(len(pieces))
        for _ in range(20):
            candidate = random_shape(len(pieces[index][1]), rng)
            if fits_board(candidate, rows, columns):
                pieces[index] = (pieces[index][0], candidate)
                break
    free = sorted(
        (row, column)
        for row in range(rows)
        for column in range(columns)
        if (row, column) not in occupied and (row, column) not in blocked
    )
    rng.shuffle(free)
    fixed = [(row, column, rng.randrange(channel_count)) for row, column in free[: rng.randint(0, 2)]]
    row_targets = [[0] * rows for _ in range(channel_count)]
    column_targets = [[0] * columns for _ in range(channel_count)]
    for index, channel, anchor_row, anchor_column, rotation in layout:
        for local_row, local_column in rotate(layout_shapes[index][1], rotation):
            row_targets[channel][anchor_row + local_row] += 1
            column_targets[channel][anchor_column + local_column] += 1
    for row, column, channel in fixed:
        row_targets[channel][row] += 1
        column_targets[channel][column] += 1
    return statement(
        rows,
        columns,
        [(index, row_targets[index], column_targets[index]) for index in range(channel_count)],
        pieces,
        blocked=sorted(blocked),
        fixed=fixed,
    )


def solve_and_check(data):
    puzzle = CircuitPuzzle.model_validate(data)
    result = solve_circuit(puzzle, SOLVE_SECONDS, SOLVE_NODES)
    if result.outcome == "solved":
        validate_solution(puzzle, result.solution)
    return puzzle, result


# Two channels interleaved on one 4x4 board.
MULTI_PIECES = [
    (0, [(0, 0), (0, 1), (1, 0)]),
    (1, [(0, 0), (0, 1)]),
    (0, [(0, 0), (0, 1)]),
    (1, [(0, 0)]),
]
MULTI_LAYOUT = [(0, 0, 0, 0), (1, 1, 1, 0), (2, 2, 0, 0), (3, 0, 3, 0)]
MULTI_DATA = build(4, 4, 2, MULTI_PIECES, MULTI_LAYOUT)

BASE_DATA = build(3, 3, 1, [(0, [(0, 0), (0, 1)])], [(0, 0, 0, 0)])


# ---------------------------------------------------------------------------
# solving


def test_single_channel_solvable_and_independently_validated() -> None:
    data = build(
        4,
        4,
        1,
        [(0, [(0, 0), (0, 1)]), (0, [(0, 0), (0, 1), (1, 0)])],
        [(0, 0, 0, 0), (1, 1, 1, 0)],
    )
    puzzle, result = solve_and_check(data)
    assert result.outcome == "solved"
    assert result.limit_reason is None
    assert result.rule_version == "line-count-v1"
    assert sorted(item.piece_index for item in result.solution.placements) == [0, 1]
    coverage = coverage_of(puzzle, result.solution)
    assert len(coverage) == 5
    assert all(channel == 0 for channel in coverage.values())


def test_multiple_channels_share_one_board_without_overlap() -> None:
    puzzle, result = solve_and_check(MULTI_DATA)
    assert result.outcome == "solved"
    coverage = coverage_of(puzzle, result.solution)
    assert len(coverage) == sum(len(cells) for _, cells in MULTI_PIECES)
    assert len(set(coverage)) == len(coverage)
    for channel in puzzle.channels:
        for row, target in enumerate(channel.row_targets):
            assert sum(1 for (r, _), ch in coverage.items() if ch == channel.index and r == row) == target
        for column, target in enumerate(channel.column_targets):
            assert sum(1 for (_, c), ch in coverage.items() if ch == channel.index and c == column) == target
    assert {channel for channel in coverage.values()} == {0, 1}


def test_blocked_and_fixed_cells_are_respected() -> None:
    # (0, 0) and (0, 2) are blocked, (1, 0) is fixed; the domino can only cover
    # the remaining two cells of the bottom row.
    data = build(
        2,
        3,
        1,
        [(0, [(0, 0), (0, 1)])],
        [(0, 1, 1, 0)],
        blocked=[(0, 0), (0, 2)],
        fixed=[(1, 0, 0)],
    )
    puzzle, result = solve_and_check(data)
    assert result.outcome == "solved"
    placement = result.solution.placements[0]
    assert (placement.row, placement.column, placement.rotation) == (1, 1, 0)
    assert coverage_of(puzzle, result.solution) == {(1, 1): 0, (1, 2): 0}


def test_rotation_is_required() -> None:
    # The only free strip is a horizontal 1x3, while the piece is declared
    # vertical, so the solver must return a 90 or 270 degree rotation.
    data = build(
        2,
        3,
        1,
        [(0, [(0, 0), (1, 0), (2, 0)])],
        [(0, 0, 0, 90)],
    )
    puzzle, result = solve_and_check(data)
    assert result.outcome == "solved"
    placement = result.solution.placements[0]
    assert placement.rotation in (90, 270)
    assert coverage_of(puzzle, result.solution) == {(0, 0): 0, (0, 1): 0, (0, 2): 0}


def test_symmetric_rotations_are_deduplicated() -> None:
    assert _piece_orientations([(0, 0)]) == [(0, ((0, 0),))]
    square = _piece_orientations([(0, 0), (0, 1), (1, 0), (1, 1)])
    assert len(square) == 1 and square[0][0] == 0
    domino = _piece_orientations([(0, 0), (0, 1)])
    assert [rotation for rotation, _ in domino] == [0, 90]
    s_piece = _piece_orientations([(0, 0), (0, 1), (1, 1), (1, 2)])
    assert len(s_piece) == 2
    l_piece = _piece_orientations([(0, 0), (1, 0), (2, 0), (2, 1)])
    assert len(l_piece) == 4
    assert all(
        min(row for row, _ in shape) == 0 and min(column for _, column in shape) == 0
        for _, shape in l_piece
    )

    data = build(3, 3, 1, [(0, [(0, 0), (0, 1), (1, 0), (1, 1)])], [(0, 0, 0, 0)])
    puzzle, result = solve_and_check(data)
    assert result.outcome == "solved"
    assert result.solution.placements[0].rotation == 0
    assert coverage_of(puzzle, result.solution) == {(0, 0): 0, (0, 1): 0, (1, 0): 0, (1, 1): 0}


def test_two_identical_pieces_are_both_placed() -> None:
    data = build(
        2,
        3,
        1,
        [(0, [(0, 0), (0, 1)]), (0, [(0, 0), (0, 1)])],
        [(0, 0, 0, 0), (1, 1, 1, 0)],
    )
    puzzle, result = solve_and_check(data)
    assert result.outcome == "solved"
    assert sorted(item.piece_index for item in result.solution.placements) == [0, 1]
    coverage = coverage_of(puzzle, result.solution)
    assert len(coverage) == 4
    assert coverage in (
        {(0, 0): 0, (0, 1): 0, (1, 1): 0, (1, 2): 0},
        {(0, 1): 0, (0, 2): 0, (1, 0): 0, (1, 1): 0},
    )


def test_solver_matches_independent_enumerator_on_small_cases() -> None:
    cases = [
        build(2, 2, 1, [(0, [(0, 0)])], [(0, 1, 1, 0)]),
        build(
            2,
            3,
            1,
            [(0, [(0, 0), (0, 1)]), (0, [(0, 0), (0, 1)])],
            [(0, 0, 0, 0), (1, 1, 1, 0)],
        ),
        build(2, 3, 1, [(0, [(0, 0), (1, 0), (2, 0)])], [(0, 0, 0, 90)]),
        build(
            3,
            3,
            1,
            [(0, [(0, 0), (0, 1), (1, 0), (1, 1)]), (0, [(0, 0)])],
            [(0, 0, 0, 0), (1, 2, 2, 0)],
        ),
        build(
            3,
            3,
            1,
            [(0, [(0, 0), (0, 1)])] * 4,
            [(0, 0, 0, 0), (1, 0, 2, 90), (2, 1, 0, 0), (3, 2, 0, 0)],
        ),
        MULTI_DATA,
        # Legal statements with no solution.
        statement(
            2,
            3,
            [(0, [2, 2], [1, 1, 2])],
            [(0, [(0, 0), (0, 1)]), (0, [(0, 0), (0, 1)])],
            blocked=[(0, 1), (1, 0)],
        ),
        statement(
            3,
            3,
            [(0, [3, 3, 2], [3, 3, 2])],
            [(0, [(0, 0), (0, 1), (1, 1), (1, 2)]), (0, [(0, 0), (0, 1), (1, 1), (1, 2)])],
        ),
        statement(
            2,
            2,
            [(0, [2, 2], [2, 2])],
            [(0, [(0, 0), (0, 1)])],
            fixed=[(0, 1, 0), (1, 0, 0)],
        ),
    ]
    for data in cases:
        puzzle = CircuitPuzzle.model_validate(data)
        expected = brute_force_solvable(puzzle)
        result = solve_circuit(puzzle, SOLVE_SECONDS, SOLVE_NODES)
        if expected:
            assert result.outcome == "solved", data
            validate_solution(puzzle, result.solution)
        else:
            assert result.outcome == "unsatisfiable", data
            assert result.solution is None


def test_unsatisfiable_result_carries_no_limit_reason() -> None:
    data = statement(
        2,
        3,
        [(0, [2, 2], [1, 1, 2])],
        [(0, [(0, 0), (0, 1)]), (0, [(0, 0), (0, 1)])],
        blocked=[(0, 1), (1, 0)],
    )
    puzzle = CircuitPuzzle.model_validate(data)
    result = solve_circuit(puzzle, SOLVE_SECONDS, SOLVE_NODES)
    assert result.outcome == "unsatisfiable"
    assert result.solution is None
    assert result.limit_reason is None


def test_solver_matches_independent_enumerator_on_seeded_random_cases() -> None:
    rng = random.Random(20260928)
    checked = solved = unsatisfiable = 0
    while checked < 40:
        data = random_statement(rng)
        if data is None:
            continue
        try:
            puzzle = CircuitPuzzle.model_validate(data)
        except ValidationError:
            continue
        checked += 1
        if brute_force_solvable(puzzle):
            solved += 1
            result = solve_circuit(puzzle, SOLVE_SECONDS, SOLVE_NODES)
            assert result.outcome == "solved", data
            validate_solution(puzzle, result.solution)
        else:
            unsatisfiable += 1
            result = solve_circuit(puzzle, SOLVE_SECONDS, SOLVE_NODES)
            assert result.outcome == "unsatisfiable", data
    assert checked == 40
    assert solved > 0 and unsatisfiable > 0


# ---------------------------------------------------------------------------
# resource limits and the job entry point


def test_node_limit_is_a_work_timeout() -> None:
    puzzle = CircuitPuzzle.model_validate(MULTI_DATA)
    result = solve_circuit(puzzle, SOLVE_SECONDS, 1)
    assert result.outcome == "timeout"
    assert result.limit_reason == "work"
    assert result.solution is None


def test_time_limit_uses_the_monotonic_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter((0.0, 5.0))
    monkeypatch.setattr("app.puzzles.circuit.solve.time", SimpleNamespace(monotonic=lambda: next(clock)))
    puzzle = CircuitPuzzle.model_validate(MULTI_DATA)
    result = solve_circuit(puzzle, 1.0, SOLVE_NODES)
    assert result.outcome == "timeout"
    assert result.limit_reason == "time"
    assert result.solution is None


@pytest.mark.parametrize(
    "seconds,nodes",
    [(0.0, 10), (-1.0, 10), (1.0, 0), (1.0, -5)],
)
def test_non_positive_limits_raise_value_error(seconds: float, nodes: int) -> None:
    puzzle = CircuitPuzzle.model_validate(MULTI_DATA)
    with pytest.raises(ValueError):
        solve_circuit(puzzle, seconds, nodes)
    with pytest.raises(ValueError):
        solve_circuit_job(MULTI_DATA, seconds, nodes)


def test_job_entry_point_round_trips_through_json_and_pickle() -> None:
    raw = solve_circuit_job(MULTI_DATA, SOLVE_SECONDS, SOLVE_NODES)
    assert isinstance(raw, dict)
    assert json.loads(json.dumps(raw)) == raw

    result = CircuitSolveResult.model_validate(json.loads(json.dumps(raw)))
    assert result.outcome == "solved"
    validate_solution(CircuitPuzzle.model_validate(MULTI_DATA), result.solution)
    assert set(raw) == {"outcome", "rule_version", "solution", "limit_reason"}
    assert set(raw["solution"]) == {"placements"}
    assert set(raw["solution"]["placements"][0]) == {"piece_index", "row", "column", "rotation"}

    restored = pickle.loads(pickle.dumps(solve_circuit_job))
    assert restored(MULTI_DATA, SOLVE_SECONDS, SOLVE_NODES) == raw


# ---------------------------------------------------------------------------
# statement model rejections


def mutate(**changes):
    data = copy.deepcopy(BASE_DATA)
    data.update(changes)
    return data


invalid_statements = {
    "unknown-field": mutate(unknown=1),
    "wrong-rule-version": mutate(rule_version="line-count-v2"),
    "rows-too-small": mutate(rows=1),
    "columns-too-large": mutate(columns=11),
    "rows-is-bool": mutate(rows=True),
    "no-channels": mutate(channels=[]),
    "too-many-channels": mutate(
        channels=[{"index": index, "row_targets": [0, 0, 0], "column_targets": [0, 0, 0]} for index in range(5)]
    ),
    "no-pieces": mutate(pieces=[]),
    "channel-index-not-contiguous": mutate(
        channels=[{"index": 1, "row_targets": [2, 0, 0], "column_targets": [1, 1, 0]}]
    ),
    "channel-index-is-bool": mutate(
        channels=[{"index": True, "row_targets": [2, 0, 0], "column_targets": [1, 1, 0]}]
    ),
    "row-targets-length": mutate(
        channels=[{"index": 0, "row_targets": [2, 0], "column_targets": [1, 1, 0]}]
    ),
    "column-targets-length": mutate(
        channels=[{"index": 0, "row_targets": [2, 0, 0], "column_targets": [1, 1, 0, 0]}]
    ),
    "negative-target": mutate(
        channels=[{"index": 0, "row_targets": [2, -1, 1], "column_targets": [1, 1, 0]}]
    ),
    "target-is-bool": mutate(
        channels=[{"index": 0, "row_targets": [True, 0, 1], "column_targets": [1, 1, 0]}]
    ),
    "row-target-longer-than-row": mutate(
        channels=[{"index": 0, "row_targets": [4, 0, 0], "column_targets": [1, 1, 0]}]
    ),
    "column-target-longer-than-column": mutate(
        channels=[{"index": 0, "row_targets": [2, 0, 0], "column_targets": [4, 0, 0]}]
    ),
    "row-column-totals-disagree": mutate(
        channels=[{"index": 0, "row_targets": [2, 0, 0], "column_targets": [2, 1, 0]}]
    ),
    "total-differs-from-fixed-plus-pieces": mutate(
        channels=[{"index": 0, "row_targets": [3, 0, 0], "column_targets": [2, 1, 0]}]
    ),
    "duplicate-blocked": mutate(blocked_cells=[{"row": 1, "column": 1}, {"row": 1, "column": 1}]),
    "blocked-out-of-bounds": mutate(blocked_cells=[{"row": 3, "column": 0}]),
    "blocked-row-is-bool": mutate(blocked_cells=[{"row": True, "column": 0}]),
    "duplicate-fixed": mutate(
        fixed_cells=[
            {"row": 1, "column": 1, "channel": 0},
            {"row": 1, "column": 1, "channel": 0},
        ]
    ),
    "fixed-out-of-bounds": mutate(fixed_cells=[{"row": 0, "column": 3, "channel": 0}]),
    "fixed-overlaps-blocked": mutate(
        blocked_cells=[{"row": 1, "column": 1}],
        fixed_cells=[{"row": 1, "column": 1, "channel": 0}],
    ),
    "fixed-unknown-channel": mutate(fixed_cells=[{"row": 1, "column": 1, "channel": 5}]),
    "fixed-channel-is-bool": mutate(fixed_cells=[{"row": 1, "column": 1, "channel": True}]),
    "fixed-row-coverage-exceeds-target": statement(
        2, 2, [(0, [0, 2], [1, 1])], [(0, [(0, 0)])], fixed=[(0, 0, 0)]
    ),
    "fixed-column-coverage-exceeds-target": statement(
        2, 2, [(0, [1, 1], [0, 2])], [(0, [(0, 0)])], fixed=[(0, 0, 0)]
    ),
    "piece-unknown-channel": mutate(pieces=[{"channel": 4, "cells": [{"row": 0, "column": 0}]}]),
    "piece-channel-is-bool": mutate(pieces=[{"channel": True, "cells": [{"row": 0, "column": 0}]}]),
    "piece-empty": mutate(pieces=[{"channel": 0, "cells": []}]),
    "piece-duplicate-cell": mutate(
        pieces=[{"channel": 0, "cells": [{"row": 0, "column": 0}, {"row": 0, "column": 0}]}]
    ),
    "piece-unconnected": mutate(
        pieces=[{"channel": 0, "cells": [{"row": 0, "column": 0}, {"row": 0, "column": 2}]}]
    ),
    "piece-not-normalized": mutate(pieces=[{"channel": 0, "cells": [{"row": 1, "column": 1}]}]),
    "piece-does-not-fit-any-rotation": mutate(
        pieces=[{"channel": 0, "cells": [{"row": row, "column": 0} for row in range(4)]}]
    ),
    "row-capacity-exceeded": mutate(blocked_cells=[{"row": 0, "column": 0}, {"row": 0, "column": 1}]),
    "column-capacity-exceeded": mutate(
        blocked_cells=[{"row": 0, "column": 0}, {"row": 1, "column": 0}, {"row": 2, "column": 0}]
    ),
}


@pytest.mark.parametrize("name", sorted(invalid_statements))
def test_model_rejects_invalid_statement(name: str) -> None:
    with pytest.raises(ValidationError):
        CircuitPuzzle.model_validate(invalid_statements[name])


def test_model_rejects_duplicate_channel_indices() -> None:
    data = mutate(
        channels=[
            {"index": 0, "row_targets": [2, 0, 0], "column_targets": [1, 1, 0]},
            {"index": 0, "row_targets": [0, 0, 0], "column_targets": [0, 0, 0]},
        ]
    )
    with pytest.raises(ValidationError):
        CircuitPuzzle.model_validate(data)


def test_model_rejects_fixed_coverage_over_a_row_and_column_target() -> None:
    # The channel totals stay consistent in both statements; only the fixed
    # cells of one line already exceed that line's target.
    row_over = statement(2, 2, [(0, [0, 2], [1, 1])], [(0, [(0, 0)])], fixed=[(0, 0, 0)])
    with pytest.raises(ValidationError, match="row fixed coverage exceeds the row target"):
        CircuitPuzzle.model_validate(row_over)

    column_over = statement(2, 2, [(0, [1, 1], [0, 2])], [(0, [(0, 0)])], fixed=[(0, 0, 0)])
    with pytest.raises(ValidationError, match="column fixed coverage exceeds the column target"):
        CircuitPuzzle.model_validate(column_over)


def test_solution_models_reject_inconsistent_results() -> None:
    with pytest.raises(ValidationError):
        CircuitPlacement(piece_index=0, row=0, column=0, rotation=45)
    with pytest.raises(ValidationError):
        CircuitPlacement(piece_index=0, row=0, column=0, rotation=False)
    with pytest.raises(ValidationError):
        CircuitPlacement(piece_index=0, row=0, column=0, rotation=0, unknown=1)
    placement = CircuitPlacement(piece_index=0, row=0, column=0, rotation=0)
    with pytest.raises(ValidationError):
        CircuitSolveResult(outcome="solved")
    with pytest.raises(ValidationError):
        CircuitSolveResult(outcome="solved", solution=CircuitSolution(placements=[placement]), limit_reason="work")
    with pytest.raises(ValidationError):
        CircuitSolveResult(outcome="timeout")
    with pytest.raises(ValidationError):
        CircuitSolveResult(outcome="unsatisfiable", limit_reason="time")
    with pytest.raises(ValidationError):
        CircuitSolveResult(outcome="unsatisfiable", solution=CircuitSolution(placements=[placement]))


# ---------------------------------------------------------------------------
# independent validator rejections


def test_validator_accepts_solver_answers_and_rejects_forged_ones() -> None:
    puzzle = CircuitPuzzle.model_validate(MULTI_DATA)
    result = solve_circuit(puzzle, SOLVE_SECONDS, SOLVE_NODES)
    assert result.outcome == "solved"
    good = result.solution.model_copy(deep=True)
    validate_solution(puzzle, good)

    with pytest.raises(ValueError):
        validate_solution(puzzle, CircuitSolution(placements=good.placements[:-1]))

    duplicated = good.model_copy(deep=True)
    duplicated.placements[-1].piece_index = duplicated.placements[0].piece_index
    with pytest.raises(ValueError):
        validate_solution(puzzle, duplicated)

    forged_rotation = good.model_copy(deep=True)
    original = forged_rotation.placements[0]
    forged_rotation.placements[0] = CircuitPlacement.model_construct(
        piece_index=original.piece_index, row=original.row, column=original.column, rotation=45
    )
    with pytest.raises(ValueError):
        validate_solution(puzzle, forged_rotation)

    out_of_bounds = good.model_copy(deep=True)
    out_of_bounds.placements[0].row = puzzle.rows - 1
    out_of_bounds.placements[0].column = puzzle.columns - 1
    with pytest.raises(ValueError):
        validate_solution(puzzle, out_of_bounds)

    overlapping = good.model_copy(deep=True)
    overlapping.placements[1].row = overlapping.placements[0].row
    overlapping.placements[1].column = overlapping.placements[0].column
    with pytest.raises(ValueError):
        validate_solution(puzzle, overlapping)

    wrong_indices = good.model_copy(deep=True)
    wrong_indices.placements[-1].piece_index = len(puzzle.pieces)
    with pytest.raises(ValueError):
        validate_solution(puzzle, wrong_indices)


def test_validator_rejects_blocked_and_fixed_coverage() -> None:
    domino = [(0, [(0, 0), (0, 1)])]

    blocked_puzzle = CircuitPuzzle.model_validate(
        build(3, 3, 1, domino, [(0, 0, 0, 0)], blocked=[(2, 2)])
    )
    on_blocked = CircuitSolution(placements=[CircuitPlacement(piece_index=0, row=2, column=1, rotation=0)])
    with pytest.raises(ValueError):
        validate_solution(blocked_puzzle, on_blocked)

    fixed_puzzle = CircuitPuzzle.model_validate(build(3, 3, 1, domino, [(0, 0, 0, 0)], fixed=[(2, 2, 0)]))
    on_fixed = CircuitSolution(placements=[CircuitPlacement(piece_index=0, row=2, column=1, rotation=0)])
    with pytest.raises(ValueError):
        validate_solution(fixed_puzzle, on_fixed)


def test_validator_rejects_wrong_row_and_column_counts() -> None:
    puzzle = CircuitPuzzle.model_validate(build(3, 3, 1, [(0, [(0, 0), (0, 1)])], [(0, 0, 0, 0)]))
    shifted_column = CircuitSolution(placements=[CircuitPlacement(piece_index=0, row=0, column=1, rotation=0)])
    with pytest.raises(ValueError):
        validate_solution(puzzle, shifted_column)
    shifted_row = CircuitSolution(placements=[CircuitPlacement(piece_index=0, row=1, column=0, rotation=0)])
    with pytest.raises(ValueError):
        validate_solution(puzzle, shifted_row)
