"""Independent result check, separate from search pruning and state."""

from collections import Counter

from app.puzzles.balloon.model import BalloonPuzzle, BalloonSolution


def validate_solution(puzzle: BalloonPuzzle, solution: BalloonSolution) -> None:
    allowed = {(cell.row, cell.column) for cell in puzzle.usable_cells}
    expected = Counter({item.lift: item.count for item in puzzle.inventory})
    placements = solution.placements
    coordinates = [(item.row, item.column) for item in placements]
    if len(coordinates) != len(set(coordinates)):
        raise ValueError("duplicate placement")
    if any(point not in allowed for point in coordinates):
        raise ValueError("placement on unavailable cell")
    if Counter(item.lift for item in placements) != expected:
        raise ValueError("inventory mismatch")
    total_lift = sum(item.lift for item in placements)
    column_moment = sum(item.lift * (2 * item.column - (puzzle.columns - 1)) for item in placements)
    row_moment = sum(item.lift * (2 * item.row - (puzzle.rows - 1)) for item in placements)
    if column_moment != 0 or row_moment != 0:
        raise ValueError("unbalanced placement")
    if (solution.used_count, solution.total_lift, solution.column_moment, solution.row_moment) != (
        len(placements), total_lift, column_moment, row_moment
    ):
        raise ValueError("incorrect solution summary")
