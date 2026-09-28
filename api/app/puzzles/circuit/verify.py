"""Independent result check for ``line-count-v1`` solutions.

This module deliberately shares no search helper with ``solve.py``: every
rotation is recomputed from the original piece definition and every row and
column count is recomputed from the fixed cells plus the reconstructed
coverage. It never looks at pre-generated candidates or search state, so a bug
in the solver cannot make a forged placement look valid.
"""

from app.puzzles.circuit.model import CircuitPuzzle, CircuitSolution


_ROTATIONS = (0, 90, 180, 270)


def _rotated_cells(cells: list[tuple[int, int]], rotation: int) -> list[tuple[int, int]]:
    """Rotate raw local cells clockwise, re-normalizing to the origin each step."""
    current = sorted(cells)
    for _ in range(rotation // 90):
        current = [(column, -row) for row, column in current]
        min_row = min(row for row, _ in current)
        min_column = min(column for _, column in current)
        current = sorted((row - min_row, column - min_column) for row, column in current)
    return current


def validate_solution(puzzle: CircuitPuzzle, solution: CircuitSolution) -> None:
    """Recompute the whole board from the puzzle and the placement list.

    Raises ``ValueError`` when any piece is missing, duplicated, out of bounds,
    overlapping, on a blocked or fixed cell, or when a channel's rebuilt row and
    column counts differ from its targets.
    """
    piece_count = len(puzzle.pieces)
    indices = [placement.piece_index for placement in solution.placements]
    if sorted(indices) != list(range(piece_count)):
        raise ValueError("every piece must be placed exactly once")

    blocked = {(cell.row, cell.column) for cell in puzzle.blocked_cells}
    fixed = {(cell.row, cell.column) for cell in puzzle.fixed_cells}
    row_counts = {channel.index: [0] * puzzle.rows for channel in puzzle.channels}
    column_counts = {channel.index: [0] * puzzle.columns for channel in puzzle.channels}
    # Fixed cells already belong to their channel, so they count toward the
    # targets before any placement is considered.
    for cell in puzzle.fixed_cells:
        if cell.channel not in row_counts:
            raise ValueError("fixed cell references an unknown channel")
        row_counts[cell.channel][cell.row] += 1
        column_counts[cell.channel][cell.column] += 1

    covered: set[tuple[int, int]] = set()
    for placement in solution.placements:
        if placement.rotation not in _ROTATIONS:
            raise ValueError("rotation must be 0, 90, 180 or 270")
        piece = puzzle.pieces[placement.piece_index]
        if piece.channel not in row_counts:
            raise ValueError("placement references an unknown channel")
        shape = _rotated_cells([(cell.row, cell.column) for cell in piece.cells], placement.rotation)
        for row, column in shape:
            board_row = row + placement.row
            board_column = column + placement.column
            if not (0 <= board_row < puzzle.rows and 0 <= board_column < puzzle.columns):
                raise ValueError("placement extends outside the board")
            if (board_row, board_column) in blocked:
                raise ValueError("placement covers a blocked cell")
            if (board_row, board_column) in fixed:
                raise ValueError("placement covers a fixed cell")
            if (board_row, board_column) in covered:
                raise ValueError("placements overlap")
            covered.add((board_row, board_column))
            row_counts[piece.channel][board_row] += 1
            column_counts[piece.channel][board_column] += 1

    for channel in puzzle.channels:
        if row_counts[channel.index] != list(channel.row_targets):
            raise ValueError("row coverage does not match the channel targets")
        if column_counts[channel.index] != list(channel.column_targets):
            raise ValueError("column coverage does not match the channel targets")
