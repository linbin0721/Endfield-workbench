"""Response models for the source-circuit question-number catalog."""

from __future__ import annotations

import math
import numbers
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.puzzles.circuit.model import CircuitPuzzle
from app.puzzles.circuit.presentation import (
    CircuitDisplayColor,
    palette_matches_channels,
)


CandidateStatus = Literal["provisional", "verified"]
CircuitCatalogCandidateStatus = CandidateStatus


class CircuitCatalogCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    puzzle: CircuitPuzzle
    display_palette: list[CircuitDisplayColor] = Field(default_factory=list)
    status: CircuitCatalogCandidateStatus
    observations: int = Field(ge=1)
    first_seen: datetime
    last_seen: datetime

    @model_validator(mode="after")
    def validate_status(self) -> "CircuitCatalogCandidate":
        expected = "verified" if self.observations >= 2 else "provisional"
        if self.status != expected:
            raise ValueError("candidate status must match its observation count")
        if self.last_seen < self.first_seen:
            raise ValueError("candidate last_seen cannot precede first_seen")
        if self.display_palette and not palette_matches_channels(
            self.display_palette,
            range(len(self.puzzle.channels)),
        ):
            raise ValueError("candidate palette must match puzzle channels")
        return self


class CircuitCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^(?:V[0-9]{5}|WL[0-9]{4})$")
    candidates: list[CircuitCatalogCandidate] = Field(default_factory=list)
    updated_at: datetime


class CircuitCatalogMatch(BaseModel):
    """How the current circuit recognition relates to stored variants."""

    model_config = ConfigDict(extra="forbid")

    available: bool = True
    code: str = Field(pattern=r"^(?:V[0-9]{5}|WL[0-9]{4})$")
    code_confidence: float | None = None
    complete: bool = False
    recorded: bool = False
    duplicate: bool = False
    image_digest_mismatch: bool = False
    matched_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    matched_status: CircuitCatalogCandidateStatus | None = None
    candidates: list[CircuitCatalogCandidate] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)

    @field_validator("code_confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: object) -> object:
        if value is None:
            return value
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise ValueError("code confidence must be numeric")
        numeric = float(value)
        if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
            raise ValueError("code confidence must be finite in 0..1")
        return numeric

    @model_validator(mode="after")
    def validate_match(self) -> "CircuitCatalogMatch":
        if self.recorded and self.duplicate:
            raise ValueError("a catalog match cannot be both recorded and duplicate")
        if self.image_digest_mismatch and (
            self.recorded
            or self.duplicate
            or self.matched_fingerprint is not None
            or self.matched_status is not None
        ):
            raise ValueError("a digest mismatch cannot claim an observation match")
        if (self.matched_fingerprint is None) != (self.matched_status is None):
            raise ValueError("matched fingerprint and status must be set together")
        return self
