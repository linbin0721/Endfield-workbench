"""Bounded deterministic search for the versioned ``line-count-v1`` rule.

The search never guesses: fixed and blocked cells are removed up front, every
legal placement of every remaining piece is pre-generated as a board bitmask
plus its row and column contributions, and a depth-first search with MRV,
contribution bounds, exchange-symmetry elimination and a failed-state cache
either finds one solution or proves there is none within the service limits.
The result is re-checked by ``verify.validate_solution`` before it is returned.
"""

import time
from typing import NamedTuple

from app.puzzles.circuit.model import (
    ROTATIONS,
    CircuitPlacement,
    CircuitPuzzle,
    CircuitSolution,
    CircuitSolveResult,
)
from app.puzzles.circuit.verify import validate_solution


class _LimitReached(Exception):
    """Internal control flow: the bounded search hit a service limit."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _Candidate(NamedTuple):
    """One pre-generated legal placement of one piece."""

    mask: int
    rotation: int
    row: int
    column: int
    row_counts: tuple[tuple[int, int], ...]
    column_counts: tuple[tuple[int, int], ...]


def _normalize_shape(cells) -> tuple[tuple[int, int], ...]:
    min_row = min(row for row, _ in cells)
    min_column = min(column for _, column in cells)
    return tuple(sorted((row - min_row, column - min_column) for row, column in cells))


def _piece_orientations(cells) -> list[tuple[int, tuple[tuple[int, int], ...]]]:
    """Distinct normalized orientations in 0/90/180/270 order.

    Symmetric shapes collapse to a single entry, so rotations that reproduce an
    earlier orientation are never enumerated twice.
    """
    orientations: list[tuple[int, tuple[tuple[int, int], ...]]] = []
    current = _normalize_shape(cells)
    for rotation in ROTATIONS:
        if rotation:
            height = max(row for row, _ in current) + 1
            current = _normalize_shape([(column, height - 1 - row) for row, column in current])
        if all(shape != current for _, shape in orientations):
            orientations.append((rotation, current))
    return orientations


def solve_circuit_job(data: dict, time_limit_seconds: float, max_nodes: int) -> dict:
    """Top-level pickleable worker entry point. Never run in an HTTP handler."""
    puzzle = CircuitPuzzle.model_validate(data)
    return solve_circuit(puzzle, time_limit_seconds, max_nodes).model_dump()


def solve_circuit(puzzle: CircuitPuzzle, time_limit_seconds: float, max_nodes: int) -> CircuitSolveResult:
    """Search one circuit puzzle inside a monotonic deadline and a node budget."""
    if time_limit_seconds <= 0 or max_nodes < 1:
        raise ValueError("solver limits must be positive")
    deadline = time.monotonic() + time_limit_seconds

    rows = puzzle.rows
    columns = puzzle.columns
    channel_ids = sorted(channel.index for channel in puzzle.channels)
    channels = {channel.index: channel for channel in puzzle.channels}

    # Steps 1-3: fixed and blocked cells become unavailable bits; the remaining
    # targets are what the inventory pieces still have to cover.
    blocked_mask = 0
    blocked_rows = [0] * rows
    blocked_columns = [0] * columns
    for cell in puzzle.blocked_cells:
        blocked_mask |= 1 << (cell.row * columns + cell.column)
        blocked_rows[cell.row] += 1
        blocked_columns[cell.column] += 1

    fixed_mask = 0
    fixed_rows = {index: [0] * rows for index in channel_ids}
    fixed_columns = {index: [0] * columns for index in channel_ids}
    for cell in puzzle.fixed_cells:
        fixed_mask |= 1 << (cell.row * columns + cell.column)
        fixed_rows[cell.channel][cell.row] += 1
        fixed_columns[cell.channel][cell.column] += 1

    row_remaining = {
        index: [channels[index].row_targets[row] - fixed_rows[index][row] for row in range(rows)]
        for index in channel_ids
    }
    column_remaining = {
        index: [channels[index].column_targets[column] - fixed_columns[index][column] for column in range(columns)]
        for index in channel_ids
    }
    if any(value < 0 for values in row_remaining.values() for value in values) or any(
        value < 0 for values in column_remaining.values() for value in values
    ):
        return CircuitSolveResult(outcome="unsatisfiable")

    free_rows = [
        columns - blocked_rows[row] - sum(fixed_rows[index][row] for index in channel_ids) for row in range(rows)
    ]
    free_columns = [
        rows - blocked_columns[column] - sum(fixed_columns[index][column] for index in channel_ids)
        for column in range(columns)
    ]

    orientations = [
        _piece_orientations([(cell.row, cell.column) for cell in piece.cells]) for piece in puzzle.pieces
    ]
    piece_channel = [piece.channel for piece in puzzle.pieces]
    piece_area = [len(piece.cells) for piece in puzzle.pieces]

    candidates: list[tuple[_Candidate, ...]] = []
    for piece_orientations in orientations:
        generated: list[_Candidate] = []
        for rotation, shape in piece_orientations:
            height = max(row for row, _ in shape) + 1
            width = max(column for _, column in shape) + 1
            for anchor_row in range(rows - height + 1):
                for anchor_column in range(columns - width + 1):
                    mask = 0
                    touched_rows: dict[int, int] = {}
                    touched_columns: dict[int, int] = {}
                    for row, column in shape:
                        board_row = anchor_row + row
                        board_column = anchor_column + column
                        mask |= 1 << (board_row * columns + board_column)
                        touched_rows[board_row] = touched_rows.get(board_row, 0) + 1
                        touched_columns[board_column] = touched_columns.get(board_column, 0) + 1
                    if mask & (blocked_mask | fixed_mask):
                        continue
                    generated.append(_Candidate(
                        mask=mask,
                        rotation=rotation,
                        row=anchor_row,
                        column=anchor_column,
                        row_counts=tuple(sorted(touched_rows.items())),
                        column_counts=tuple(sorted(touched_columns.items())),
                    ))
        candidates.append(tuple(generated))
    if any(not options for options in candidates):
        return CircuitSolveResult(outcome="unsatisfiable")

    # Pieces with the same channel and the same canonical orientation set are
    # interchangeable, so the search only ever branches on the lowest-indexed
    # unplaced member of each such group.
    canonical = [min(shape for _, shape in item) for item in orientations]
    class_ids: dict[tuple[int, tuple[tuple[int, int], ...]], int] = {}
    class_members: list[list[int]] = []
    for index, channel in enumerate(piece_channel):
        key = (channel, canonical[index])
        if key not in class_ids:
            class_ids[key] = len(class_members)
            class_members.append([])
        class_members[class_ids[key]].append(index)

    nodes = 0
    failed: set[tuple] = set()

    def feasible(candidate: _Candidate, channel: int, occupied: int) -> bool:
        if candidate.mask & occupied:
            return False
        available_rows = row_remaining[channel]
        for row, count in candidate.row_counts:
            if available_rows[row] < count:
                return False
        available_columns = column_remaining[channel]
        for column, count in candidate.column_counts:
            if available_columns[column] < count:
                return False
        return True

    def search(occupied: int, remaining: int) -> list[tuple[int, _Candidate]] | None:
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes:
            raise _LimitReached("work")
        if time.monotonic() >= deadline:
            raise _LimitReached("time")
        if remaining == 0:
            return []

        row_load = [0] * rows
        for row in range(rows):
            load = sum(row_remaining[index][row] for index in channel_ids)
            if load > free_rows[row]:
                return None
            row_load[row] = load
        column_load = [0] * columns
        for column in range(columns):
            load = sum(column_remaining[index][column] for index in channel_ids)
            if load > free_columns[column]:
                return None
            column_load[column] = load

        key = (
            occupied,
            remaining,
            tuple(tuple(row_remaining[index]) for index in channel_ids),
            tuple(tuple(column_remaining[index]) for index in channel_ids),
        )
        if key in failed:
            return None

        # Step 4 and 6: MRV over interchangeable groups, plus a lower and upper
        # bound for every channel row and column built from the still-legal
        # candidates of each remaining piece.
        row_low = {index: [0] * rows for index in channel_ids}
        row_high = {index: [0] * rows for index in channel_ids}
        column_low = {index: [0] * columns for index in channel_ids}
        column_high = {index: [0] * columns for index in channel_ids}
        chosen_piece = -1
        chosen_channel = -1
        chosen_rank: tuple[int, int] | None = None
        chosen_options: list[_Candidate] = []
        for members in class_members:
            unplaced = [index for index in members if remaining >> index & 1]
            if not unplaced:
                continue
            piece = unplaced[0]
            channel = piece_channel[piece]
            options = [candidate for candidate in candidates[piece] if feasible(candidate, channel, occupied)]
            if not options:
                failed.add(key)
                return None
            rank = (len(options), -piece_area[piece])
            if chosen_rank is None or rank < chosen_rank:
                chosen_rank = rank
                chosen_piece = piece
                chosen_channel = channel
                chosen_options = options
            copies = len(unplaced)
            local_row_low = [0] * rows
            local_row_high = [0] * rows
            local_column_low = [0] * columns
            local_column_high = [0] * columns
            row_hits = [0] * rows
            column_hits = [0] * columns
            for candidate in options:
                for row, count in candidate.row_counts:
                    row_hits[row] += 1
                    if row_hits[row] == 1 or count < local_row_low[row]:
                        local_row_low[row] = count
                    if count > local_row_high[row]:
                        local_row_high[row] = count
                for column, count in candidate.column_counts:
                    column_hits[column] += 1
                    if column_hits[column] == 1 or count < local_column_low[column]:
                        local_column_low[column] = count
                    if count > local_column_high[column]:
                        local_column_high[column] = count
            for row in range(rows):
                if row_hits[row] != len(options):
                    local_row_low[row] = 0  # some placement of this piece misses the row
                row_low[channel][row] += copies * local_row_low[row]
                row_high[channel][row] += copies * local_row_high[row]
            for column in range(columns):
                if column_hits[column] != len(options):
                    local_column_low[column] = 0
                column_low[channel][column] += copies * local_column_low[column]
                column_high[channel][column] += copies * local_column_high[column]

        for index in channel_ids:
            for row in range(rows):
                value = row_remaining[index][row]
                if value < row_low[index][row] or value > row_high[index][row]:
                    failed.add(key)
                    return None
            for column in range(columns):
                value = column_remaining[index][column]
                if value < column_low[index][column] or value > column_high[index][column]:
                    failed.add(key)
                    return None

        # Step 5: tightest lines first; the first complete assignment wins.
        def tightness(candidate: _Candidate) -> tuple[int, int]:
            score = 0
            for row, count in candidate.row_counts:
                score += count * (free_rows[row] - row_load[row])
            for column, count in candidate.column_counts:
                score += count * (free_columns[column] - column_load[column])
            return (score, candidate.mask)

        for candidate in sorted(chosen_options, key=tightness):
            for row, count in candidate.row_counts:
                row_remaining[chosen_channel][row] -= count
                free_rows[row] -= count
            for column, count in candidate.column_counts:
                column_remaining[chosen_channel][column] -= count
                free_columns[column] -= count
            result = search(occupied | candidate.mask, remaining & ~(1 << chosen_piece))
            for row, count in candidate.row_counts:
                row_remaining[chosen_channel][row] += count
                free_rows[row] += count
            for column, count in candidate.column_counts:
                column_remaining[chosen_channel][column] += count
                free_columns[column] += count
            if result is not None:
                return [(chosen_piece, candidate), *result]
        failed.add(key)
        return None

    try:
        found = search(fixed_mask, (1 << len(puzzle.pieces)) - 1)
    except _LimitReached as limit:
        return CircuitSolveResult(outcome="timeout", limit_reason=limit.reason)
    if found is None:
        return CircuitSolveResult(outcome="unsatisfiable")

    placements = [
        CircuitPlacement(piece_index=piece, row=candidate.row, column=candidate.column, rotation=candidate.rotation)
        for piece, candidate in found
    ]
    placements.sort(key=lambda placement: placement.piece_index)
    solution = CircuitSolution(placements=placements)
    validate_solution(puzzle, solution)
    return CircuitSolveResult(outcome="solved", solution=solution)
