"""Presentation-only color models shared by recognition and the catalog."""

from __future__ import annotations

import math
import numbers
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class CircuitDisplayColor(BaseModel):
    """One domain channel's display hue in standard 0..360 degree space."""

    model_config = ConfigDict(extra="forbid")

    channel: StrictInt = Field(ge=0, le=3)
    hue_degrees: float = Field(ge=0.0, lt=360.0)

    @field_validator("hue_degrees", mode="before")
    @classmethod
    def validate_finite_hue(cls, value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise ValueError("display hue must be numeric")
        hue = float(value)
        if not math.isfinite(hue) or not 0.0 <= hue < 360.0:
            raise ValueError("display hue must be finite in [0, 360)")
        return hue


def palette_matches_channels(
    palette: Sequence[CircuitDisplayColor], expected_channels: Sequence[int]
) -> bool:
    """Return whether a palette is complete and ordered for the given channels."""

    return [color.channel for color in palette] == list(expected_channels)
