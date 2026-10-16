"""Editable recognition evidence, deliberately separate from a valid puzzle.

Only line targets may be unknown in v1. Geometry, channels, cells and the whole
inventory must already be reliable. Totals, capacity and solvability remain
the responsibility of CircuitPuzzle and the existing solve endpoint.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.puzzles.circuit.model import CircuitPiece
from app.puzzles.circuit.presentation import CircuitDisplayColor, palette_matches_channels

DraftTarget = Annotated[StrictInt, Field(ge=0, le=10)] | None
DraftReason = Literal[
    "row_targets", "column_targets", "rejected", "unsatisfiable",
    "solver_limit", "validation_failed",
]


class CircuitDraftChannel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: StrictInt = Field(ge=0, le=3)
    row_targets: list[DraftTarget] = Field(min_length=2, max_length=10)
    column_targets: list[DraftTarget] = Field(min_length=2, max_length=10)


class CircuitDraftCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["empty", "blocked", "fixed"]
    channel: StrictInt | None = Field(default=None, ge=0, le=3)

    @model_validator(mode="after")
    def validate_channel(self) -> "CircuitDraftCell":
        if (self.kind == "fixed") != (self.channel is not None):
            raise ValueError("only a fixed draft cell has a required channel")
        return self


class CircuitDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_version: Literal["line-count-v1"] = "line-count-v1"
    rows: StrictInt = Field(ge=2, le=10)
    columns: StrictInt = Field(ge=2, le=10)
    channels: list[CircuitDraftChannel] = Field(min_length=1, max_length=4)
    cells: list[CircuitDraftCell] = Field(min_length=4, max_length=100)
    pieces: list[CircuitPiece] = Field(min_length=1, max_length=32)
    palette: list[CircuitDisplayColor] = Field(min_length=1, max_length=4)
    missing: list[DraftReason] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def validate_structure(self) -> "CircuitDraft":
        indices = list(range(len(self.channels)))
        if [channel.index for channel in self.channels] != indices:
            raise ValueError("draft channels must be ordered and contiguous")
        if len(self.cells) != self.rows * self.columns:
            raise ValueError("draft cells must be row-major and match the board")
        if not palette_matches_channels(self.palette, indices):
            raise ValueError("draft palette must match its channels")
        for channel in self.channels:
            if len(channel.row_targets) != self.rows or len(channel.column_targets) != self.columns:
                raise ValueError("draft target lengths must match the board")
            if any(v is not None and v > self.columns for v in channel.row_targets):
                raise ValueError("draft row target exceeds the line length")
            if any(v is not None and v > self.rows for v in channel.column_targets):
                raise ValueError("draft column target exceeds the line length")
        if any(cell.channel is not None and cell.channel not in indices for cell in self.cells):
            raise ValueError("draft fixed cell references an unknown channel")
        if any(piece.channel not in indices for piece in self.pieces):
            raise ValueError("draft piece references an unknown channel")
        if len(set(self.missing)) != len(self.missing):
            raise ValueError("draft reasons must be unique")
        for field in ("row_targets", "column_targets"):
            unknown = any(v is None for channel in self.channels for v in getattr(channel, field))
            if unknown != (field in self.missing):
                raise ValueError("draft missing reasons must describe unknown targets")
        return self
