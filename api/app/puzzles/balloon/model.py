from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


RULE_VERSION = "center-torque-v1"


class Cell(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row: StrictInt = Field(ge=0)
    column: StrictInt = Field(ge=0)


class Stock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lift: StrictInt = Field(ge=1, le=100)
    count: StrictInt = Field(ge=1, le=18)


class BalloonPuzzle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_version: Literal["center-torque-v1"]
    rows: StrictInt = Field(ge=2, le=6)
    columns: StrictInt = Field(ge=2, le=6)
    usable_cells: list[Cell] = Field(min_length=1, max_length=36)
    inventory: list[Stock] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_board(self) -> "BalloonPuzzle":
        cells = [(cell.row, cell.column) for cell in self.usable_cells]
        if len(set(cells)) != len(cells):
            raise ValueError("usable_cells contains duplicate coordinates")
        if any(row >= self.rows or column >= self.columns for row, column in cells):
            raise ValueError("usable_cells contains an out-of-bounds coordinate")
        lifts = [item.lift for item in self.inventory]
        if len(set(lifts)) != len(lifts):
            raise ValueError("inventory contains duplicate lift values")
        count = sum(item.count for item in self.inventory)
        if count > 18 or count > len(cells):
            raise ValueError("inventory exceeds balloon or usable-cell limit")
        return self


class Placement(Cell):
    lift: StrictInt = Field(ge=1)


class BalloonSolution(BaseModel):
    placements: list[Placement]
    used_count: int
    total_lift: int
    column_moment: int
    row_moment: int


class BalloonSolveResult(BaseModel):
    outcome: Literal["solved", "unsatisfiable", "timeout"]
    rule_version: Literal["center-torque-v1"] = RULE_VERSION
    solution: BalloonSolution | None = None
    limit_reason: Literal["time", "work"] | None = None
