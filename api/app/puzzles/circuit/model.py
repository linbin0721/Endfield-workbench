"""Domain model for the versioned ``line-count-v1`` circuit puzzle.

Every value that later shapes the search is validated here, so the solver and
the independent checker can trust the puzzle: board size, channel numbering,
target lengths and totals, obstacles, fixed cells and piece geometry.
"""

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


RULE_VERSION = "line-count-v1"
ROTATIONS = (0, 90, 180, 270)
MAX_BOARD_CELLS = 100


class CircuitCell(BaseModel):
    """Zero-based board coordinate shared by blocked, fixed and piece cells."""

    model_config = ConfigDict(extra="forbid")

    row: StrictInt = Field(ge=0)
    column: StrictInt = Field(ge=0)


class CircuitFixedCell(CircuitCell):
    """Already covered cell that belongs to one color channel."""

    channel: StrictInt = Field(ge=0)


class CircuitChannel(BaseModel):
    """One color channel with its per-row and per-column coverage counts."""

    model_config = ConfigDict(extra="forbid")

    index: StrictInt = Field(ge=0, le=3)
    row_targets: list[StrictInt] = Field(min_length=2, max_length=10)
    column_targets: list[StrictInt] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def validate_targets(self) -> "CircuitChannel":
        if any(value < 0 for value in (*self.row_targets, *self.column_targets)):
            raise ValueError("channel targets must be nonnegative")
        return self


class CircuitPiece(BaseModel):
    """Inventory piece in normalized local coordinates; rotations are implicit."""

    model_config = ConfigDict(extra="forbid")

    channel: StrictInt = Field(ge=0)
    cells: list[CircuitCell] = Field(min_length=1, max_length=MAX_BOARD_CELLS)

    @model_validator(mode="after")
    def validate_shape(self) -> "CircuitPiece":
        coordinates = {(cell.row, cell.column) for cell in self.cells}
        if len(coordinates) != len(self.cells):
            raise ValueError("piece contains duplicate local coordinates")
        if min(row for row, _ in coordinates) != 0 or min(column for _, column in coordinates) != 0:
            raise ValueError("piece must be normalized so its minimum row and column are 0")
        pending = [next(iter(coordinates))]
        visited = {pending[0]}
        while pending:
            row, column = pending.pop()
            for neighbor in ((row + 1, column), (row - 1, column), (row, column + 1), (row, column - 1)):
                if neighbor in coordinates and neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        if len(visited) != len(coordinates):
            raise ValueError("piece cells must be four-connected")
        return self


class CircuitPuzzle(BaseModel):
    """A complete ``line-count-v1`` statement."""

    model_config = ConfigDict(extra="forbid")

    rule_version: Literal["line-count-v1"]
    rows: StrictInt = Field(ge=2, le=10)
    columns: StrictInt = Field(ge=2, le=10)
    channels: list[CircuitChannel] = Field(min_length=1, max_length=4)
    blocked_cells: list[CircuitCell] = Field(default_factory=list, max_length=MAX_BOARD_CELLS)
    fixed_cells: list[CircuitFixedCell] = Field(default_factory=list, max_length=MAX_BOARD_CELLS)
    pieces: list[CircuitPiece] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_puzzle(self) -> "CircuitPuzzle":
        if self.rows * self.columns > MAX_BOARD_CELLS:
            raise ValueError("board exceeds the 100-cell limit")
        indices = [channel.index for channel in self.channels]
        if sorted(indices) != list(range(len(self.channels))):
            raise ValueError("channel indices must be contiguous starting at 0")
        for channel in self.channels:
            if len(channel.row_targets) != self.rows or len(channel.column_targets) != self.columns:
                raise ValueError("channel targets must match the board dimensions")
            if any(value > self.columns for value in channel.row_targets):
                raise ValueError("row target exceeds the row length")
            if any(value > self.rows for value in channel.column_targets):
                raise ValueError("column target exceeds the column length")

        blocked = {(cell.row, cell.column) for cell in self.blocked_cells}
        if len(blocked) != len(self.blocked_cells):
            raise ValueError("blocked_cells contains duplicate coordinates")
        if any(row >= self.rows or column >= self.columns for row, column in blocked):
            raise ValueError("blocked_cells contains an out-of-bounds coordinate")

        fixed: dict[tuple[int, int], int] = {}
        for cell in self.fixed_cells:
            point = (cell.row, cell.column)
            if point in fixed:
                raise ValueError("fixed_cells contains duplicate coordinates")
            if point in blocked:
                raise ValueError("fixed_cells overlaps blocked_cells")
            if cell.row >= self.rows or cell.column >= self.columns:
                raise ValueError("fixed_cells contains an out-of-bounds coordinate")
            if cell.channel not in indices:
                raise ValueError("fixed_cells references an unknown channel")
            fixed[point] = cell.channel

        # Fixed cells already count toward their channel's line targets, so a
        # line whose fixed count exceeds its target is contradictory before the
        # search starts and must be rejected instead of reported unsatisfiable.
        fixed_rows: Counter[tuple[int, int]] = Counter()
        fixed_columns: Counter[tuple[int, int]] = Counter()
        for (row, column), channel in fixed.items():
            fixed_rows[(channel, row)] += 1
            fixed_columns[(channel, column)] += 1
        for channel in self.channels:
            for row, target in enumerate(channel.row_targets):
                if fixed_rows[(channel.index, row)] > target:
                    raise ValueError("row fixed coverage exceeds the row target")
            for column, target in enumerate(channel.column_targets):
                if fixed_columns[(channel.index, column)] > target:
                    raise ValueError("column fixed coverage exceeds the column target")

        piece_area = {index: 0 for index in indices}
        for piece in self.pieces:
            if piece.channel not in indices:
                raise ValueError("piece references an unknown channel")
            piece_area[piece.channel] += len(piece.cells)
            height = max(cell.row for cell in piece.cells) + 1
            width = max(cell.column for cell in piece.cells) + 1
            if not (
                (height <= self.rows and width <= self.columns)
                or (width <= self.rows and height <= self.columns)
            ):
                raise ValueError("piece bounding box does not fit the board in any rotation")

        fixed_count: Counter[int] = Counter(fixed.values())
        for channel in self.channels:
            total = sum(channel.row_targets)
            if total != sum(channel.column_targets):
                raise ValueError("channel row and column targets disagree")
            if total != fixed_count[channel.index] + piece_area[channel.index]:
                raise ValueError("channel targets must equal fixed cells plus piece area")

        blocked_rows = Counter(row for row, _ in blocked)
        blocked_columns = Counter(column for _, column in blocked)
        for row in range(self.rows):
            capacity = self.columns - blocked_rows[row]
            if sum(channel.row_targets[row] for channel in self.channels) > capacity:
                raise ValueError("row targets exceed the non-blocked capacity")
        for column in range(self.columns):
            capacity = self.rows - blocked_columns[column]
            if sum(channel.column_targets[column] for channel in self.channels) > capacity:
                raise ValueError("column targets exceed the non-blocked capacity")
        return self


class CircuitPlacement(BaseModel):
    """One piece anchored by the top-left corner of its rotated bounding box."""

    model_config = ConfigDict(extra="forbid")

    piece_index: StrictInt = Field(ge=0, le=31)
    row: StrictInt = Field(ge=0, le=9)
    column: StrictInt = Field(ge=0, le=9)
    rotation: StrictInt

    @model_validator(mode="after")
    def validate_rotation(self) -> "CircuitPlacement":
        if self.rotation not in ROTATIONS:
            raise ValueError("rotation must be 0, 90, 180 or 270")
        return self


class CircuitSolution(BaseModel):
    """Only the placements; the covered board is derived from the puzzle."""

    model_config = ConfigDict(extra="forbid")

    placements: list[CircuitPlacement] = Field(default_factory=list, max_length=32)


class CircuitSolveResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["solved", "unsatisfiable", "timeout"]
    rule_version: Literal["line-count-v1"] = RULE_VERSION
    solution: CircuitSolution | None = None
    limit_reason: Literal["time", "work"] | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> "CircuitSolveResult":
        if self.outcome == "solved":
            if self.solution is None:
                raise ValueError("a solved result must carry a solution")
            if self.limit_reason is not None:
                raise ValueError("only a timeout result carries a limit_reason")
        else:
            if self.solution is not None:
                raise ValueError("only a solved result carries a solution")
            if self.outcome == "timeout":
                if self.limit_reason is None:
                    raise ValueError("a timeout result must carry a limit_reason")
            elif self.limit_reason is not None:
                raise ValueError("only a timeout result carries a limit_reason")
        return self
