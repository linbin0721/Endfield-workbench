from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


TaskStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class TaskView(BaseModel):
    id: str
    status: TaskStatus
    created_at: datetime
    completed_at: datetime | None = None
    cancellation_requested: bool = False
    computation_stopped: bool = False
    result: Any | None = None
    error: ErrorDetail | None = None


class PuzzleCapability(BaseModel):
    id: str
    name: str
    recognition_available: bool
    solving_available: bool
    supported_rule_versions: list[str]
    rules_note: str
