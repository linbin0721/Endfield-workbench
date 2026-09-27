"""Response models for the question-number catalog."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.puzzles.balloon.model import BalloonPuzzle


CatalogStatus = Literal["provisional", "verified", "disputed"]


class CatalogCandidate(BaseModel):
    fingerprint: str
    puzzle: BalloonPuzzle
    target_total_lift: int | None = None
    observations: int = 1
    first_seen: datetime
    last_seen: datetime


class CatalogEntry(BaseModel):
    code: str
    status: CatalogStatus
    candidates: list[CatalogCandidate] = Field(default_factory=list)
    updated_at: datetime


class CatalogMatch(BaseModel):
    """How the current recognition relates to the stored catalog."""

    available: bool = True
    code: str
    code_confidence: float | None = None
    complete: bool = False
    recorded: bool = False
    duplicate: bool = False
    matched_fingerprint: str | None = None
    status: CatalogStatus | None = None
    candidates: list[CatalogCandidate] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
