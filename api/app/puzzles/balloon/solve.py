"""Bounded exact search for the explicitly versioned center-torque rule."""

import time

from app.puzzles.balloon.model import (
    BalloonPuzzle, BalloonSolution, BalloonSolveResult, Placement,
)
from app.puzzles.balloon.verify import validate_solution


class _LimitReached(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def solve_balloon_job(data: dict, time_limit_seconds: float, max_nodes: int) -> dict:
    """Top-level pickleable worker entry point. Never run in an HTTP handler."""
    puzzle = BalloonPuzzle.model_validate(data)
    return solve_balloon(puzzle, time_limit_seconds, max_nodes).model_dump()


def solve_balloon(puzzle: BalloonPuzzle, time_limit_seconds: float, max_nodes: int) -> BalloonSolveResult:
    if time_limit_seconds <= 0 or max_nodes < 1:
        raise ValueError("solver limits must be positive")
    deadline = time.monotonic() + time_limit_seconds
    # Search highly weighted positions first, making moments constrain branches early.
    cells = sorted(
        ((cell.row, cell.column) for cell in puzzle.usable_cells),
        key=lambda point: (-(abs(2 * point[0] - puzzle.rows + 1) + abs(2 * point[1] - puzzle.columns + 1)), point),
    )
    stocks = sorted(puzzle.inventory, key=lambda item: -item.lift)
    lifts = tuple(item.lift for item in stocks)
    starting_counts = tuple(item.count for item in stocks)
    coordinates = [(2 * column - (puzzle.columns - 1), 2 * row - (puzzle.rows - 1)) for row, column in cells]
    seen: set[tuple[int, tuple[int, ...], int, int]] = set()
    nodes = 0

    def reachable(index: int, counts: tuple[int, ...], x_moment: int, y_moment: int) -> bool:
        weights = [lift for lift, count in zip(lifts, counts) for _ in range(count)]
        needed = len(weights)
        if needed > len(cells) - index:
            return False
        if not weights:
            return x_moment == 0 and y_moment == 0
        weights.sort(reverse=True)
        for axis, current in ((0, x_moment), (1, y_moment)):
            available = sorted(point[axis] for point in coordinates[index:])
            smallest = sum(weight * value for weight, value in zip(weights, available[:needed]))
            largest = sum(weight * value for weight, value in zip(weights, available[-needed:][::-1]))
            if current + smallest > 0 or current + largest < 0:
                return False
        return True

    def search(index: int, counts: tuple[int, ...], x_moment: int, y_moment: int) -> list[tuple[int, int, int]] | None:
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes:
            raise _LimitReached("work")
        if nodes == 1 or nodes % 128 == 0:
            if time.monotonic() >= deadline:
                raise _LimitReached("time")
        if not reachable(index, counts, x_moment, y_moment):
            return None
        if not any(counts):
            return []
        if index >= len(cells):
            return None
        state = (index, counts, x_moment, y_moment)
        if state in seen:
            return None
        row, column = cells[index]
        x, y = coordinates[index]
        for stock_index, count in enumerate(counts):
            if count == 0:
                continue
            updated = counts[:stock_index] + (count - 1,) + counts[stock_index + 1:]
            continuation = search(index + 1, updated, x_moment + lifts[stock_index] * x, y_moment + lifts[stock_index] * y)
            if continuation is not None:
                return [(row, column, lifts[stock_index]), *continuation]
        if len(cells) - index > sum(counts):
            continuation = search(index + 1, counts, x_moment, y_moment)
            if continuation is not None:
                return continuation
        seen.add(state)
        return None

    try:
        found = search(0, starting_counts, 0, 0)
    except _LimitReached as exc:
        return BalloonSolveResult(outcome="timeout", limit_reason=exc.reason)
    if found is None:
        return BalloonSolveResult(outcome="unsatisfiable")
    placements = [Placement(row=row, column=column, lift=lift) for row, column, lift in found]
    solution = BalloonSolution(
        placements=placements,
        used_count=len(placements),
        total_lift=sum(item.lift for item in placements),
        column_moment=sum(item.lift * (2 * item.column - (puzzle.columns - 1)) for item in placements),
        row_moment=sum(item.lift * (2 * item.row - (puzzle.rows - 1)) for item in placements),
    )
    validate_solution(puzzle, solution)
    return BalloonSolveResult(outcome="solved", solution=solution)
