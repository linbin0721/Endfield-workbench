"""Strict OCR adapters for already located circuit screenshots.

The module owns no OCR engine.  Callers inject one initialized recognizer so
the eventual worker can keep model loading and process lifetime in one place.
"""

from __future__ import annotations

import math
import numbers
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.catalog.circuit_rules import normalize_circuit_code
from app.puzzles.circuit.vision import BoardGeometry, SymbolLayout


CONSTRAINT_MIN_CONFIDENCE = 0.90
QUESTION_CODE_MIN_CONFIDENCE = 0.95
QUESTION_CODE_CROP_WIDTH_PERCENT = 28
QUESTION_CODE_CROP_HEIGHT_PERCENT = 22
CONSTRAINT_CROP_PADDING = 0.05

_ROMAN_VALUES = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
}


@dataclass(frozen=True)
class ConstraintToken:
    """One unambiguous normalized constraint value."""

    value: int
    notation: Literal["digits", "roman", "empty"]
    confidence: float


@dataclass(frozen=True)
class SymbolTargets:
    """Complete channel-major targets decoded from one symbol layout."""

    channel_hues: tuple[float, ...]
    row_targets: tuple[tuple[int, ...], ...]
    column_targets: tuple[tuple[int, ...], ...]
    notation: Literal["digits", "roman", "mixed"]
    minimum_confidence: float


@dataclass(frozen=True)
class PartialSymbolTargets:
    """Reliable glyph locations with uncertain values left explicitly unknown."""

    channel_hues: tuple[float, ...]
    row_targets: tuple[tuple[int | None, ...], ...]
    column_targets: tuple[tuple[int | None, ...], ...]
    notation: Literal["digits", "roman", "mixed"] | None


@dataclass(frozen=True)
class QuestionCodeReading:
    """Optional normalized code plus evidence explaining an absent value."""

    code: str | None
    confidence: float | None
    saw_code_like: bool
    ambiguous: bool

    def __post_init__(self) -> None:
        if self.code is None:
            if self.confidence is not None:
                raise ValueError("a missing question code cannot have confidence")
        else:
            if normalize_circuit_code(self.code) != self.code:
                raise ValueError("a question code must already be canonical")
            if (
                isinstance(self.confidence, bool)
                or not isinstance(self.confidence, numbers.Real)
                or not math.isfinite(float(self.confidence))
                or not 0.0 <= float(self.confidence) <= 1.0
            ):
                raise ValueError("question code confidence must be finite in 0..1")
        if self.ambiguous and (self.code is not None or not self.saw_code_like):
            raise ValueError("an ambiguous reading must be code-like and have no code")


def _normalized_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(
        character
        for character in normalized
        if not character.isspace()
        and not (
            "\ufe00" <= character <= "\ufe0f"
            or "\U000e0100" <= character <= "\U000e01ef"
        )
    )


def parse_constraint_token(
    text: str, confidence: float, maximum: int
) -> ConstraintToken | None:
    """Parse one OCR token without guessing visually similar characters."""
    if not isinstance(text, str):
        return None
    if isinstance(confidence, bool) or not isinstance(confidence, numbers.Real):
        return None
    numeric_confidence = float(confidence)
    if (
        not math.isfinite(numeric_confidence)
        or numeric_confidence < CONSTRAINT_MIN_CONFIDENCE
    ):
        return None
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 0:
        return None

    token = _normalized_text(text)
    if token in {"∅", "Ø"}:
        return ConstraintToken(value=0, notation="empty", confidence=numeric_confidence)
    if re.fullmatch(r"(?:0|[1-9][0-9]*)", token):
        value = int(token)
        if value <= maximum:
            return ConstraintToken(
                value=value, notation="digits", confidence=numeric_confidence
            )
        return None
    value = _ROMAN_VALUES.get(token)
    if value is not None and value <= maximum:
        return ConstraintToken(
            value=value, notation="roman", confidence=numeric_confidence
        )
    return None


def _validated_image(image: np.ndarray, caller: str) -> None:
    if not isinstance(image, np.ndarray):
        raise ValueError(f"{caller} expects a numpy array")
    if (
        image.dtype != np.uint8
        or image.ndim != 3
        or image.shape[2] != 3
        or image.size == 0
    ):
        raise ValueError(f"{caller} expects a non-empty uint8 BGR image")


def _text_rec_results(ocr: object, crops: list[np.ndarray]) -> list[object] | None:
    result = getattr(ocr, "text_rec")(crops)
    if not isinstance(result, tuple) or len(result) != 2:
        return None
    values = result[0]
    if not isinstance(values, (list, tuple)) or len(values) != len(crops):
        return None
    return list(values)


def extract_symbol_targets(
    image: np.ndarray,
    layout: SymbolLayout,
    ocr: object,
    *,
    allow_incomplete: bool = False,
) -> SymbolTargets | PartialSymbolTargets | None:
    """Batch-read coloured glyphs; confirmed absent keys retain their zero.

    Strict callers get the existing complete, consistent targets or None.
    Opting into drafts keeps failed glyph readings as null and preserves known
    counts even when the totals disagree, without a second OCR batch.
    """
    _validated_image(image, "extract_symbol_targets")
    geometry = layout.geometry
    keys = [(glyph.axis, glyph.line_index, glyph.channel) for glyph in layout.glyphs]
    if len(set(keys)) != len(keys):
        return None
    channel_count = len(layout.channel_hues)
    if not 1 <= channel_count <= 4:
        return None

    height, width = image.shape[:2]
    padding = CONSTRAINT_CROP_PADDING * geometry.step
    crops: list[np.ndarray] = []
    for glyph in layout.glyphs:
        if glyph.axis not in {"row", "column"}:
            return None
        if glyph.channel < 0 or glyph.channel >= channel_count:
            return None
        line_count = geometry.rows if glyph.axis == "row" else geometry.columns
        if glyph.line_index < 0 or glyph.line_index >= line_count:
            return None
        left = max(0, int(math.floor(glyph.left - padding)))
        top = max(0, int(math.floor(glyph.top - padding)))
        right = min(width, int(math.ceil(glyph.right + padding)))
        bottom = min(height, int(math.ceil(glyph.bottom + padding)))
        if right <= left or bottom <= top:
            return None
        crops.append(image[top:bottom, left:right])

    if not crops:
        return None
    results = _text_rec_results(ocr, crops)
    if results is None:
        return None

    decoded: dict[tuple[str, int, int], ConstraintToken | None] = {}
    observed_notations: set[str] = set()
    confidences: list[float] = []
    for key, result in zip(keys, results, strict=True):
        if not isinstance(result, (list, tuple)) or len(result) != 2:
            token = None
        else:
            text, confidence = result
            maximum = geometry.columns if key[0] == "row" else geometry.rows
            token = parse_constraint_token(text, confidence, maximum)
        if token is None:
            if not allow_incomplete:
                return None
            decoded[key] = None
            continue
        decoded[key] = token
        confidences.append(token.confidence)
        if token.notation != "empty":
            observed_notations.add(token.notation)

    if not observed_notations and not allow_incomplete:
        return None
    notation: Literal["digits", "roman", "mixed"] | None
    if not observed_notations:
        notation = None
    elif observed_notations == {"digits"}:
        notation = "digits"
    elif observed_notations == {"roman"}:
        notation = "roman"
    else:
        notation = "mixed"

    def value(key: tuple[str, int, int]) -> int | None:
        # Only absent glyphs in a confirmed layout mean zero. A present glyph
        # that failed OCR is unknown, never a fabricated zero.
        token = decoded.get(key, ConstraintToken(0, "empty", 1.0))
        return token.value if token is not None else None

    row_targets = tuple(
        tuple(
            value(("row", line, channel))
            for line in range(geometry.rows)
        )
        for channel in range(channel_count)
    )
    column_targets = tuple(
        tuple(
            value(("column", line, channel))
            for line in range(geometry.columns)
        )
        for channel in range(channel_count)
    )
    complete = notation is not None and all(
        v is not None for targets in (*row_targets, *column_targets) for v in targets
    )
    if not complete or any(
        sum(rows) != sum(columns)
        for rows, columns in zip(row_targets, column_targets)
    ):
        if not allow_incomplete:
            return None
        return PartialSymbolTargets(
            channel_hues=tuple(float(hue) for hue in layout.channel_hues),
            row_targets=row_targets,
            column_targets=column_targets,
            notation=notation,
        )
    return SymbolTargets(
        channel_hues=tuple(float(hue) for hue in layout.channel_hues),
        row_targets=row_targets,
        column_targets=column_targets,
        notation=notation,
        minimum_confidence=float(min(confidences)),
    )


def _ocr_boxes(ocr: object, image: np.ndarray) -> object:
    result = ocr(image)  # type: ignore[operator]
    if not isinstance(result, tuple) or len(result) != 2:
        return None
    return result[0]


def _codes_from_boxes(results: object) -> tuple[dict[str, float], bool]:
    candidates: dict[str, float] = {}
    saw_code_like = False
    if not isinstance(results, (list, tuple)):
        return candidates, False
    for result in results:
        if not isinstance(result, (list, tuple)) or len(result) != 3:
            continue
        _, text, confidence = result
        code = normalize_circuit_code(text)
        if code is None:
            continue
        saw_code_like = True
        if isinstance(confidence, bool) or not isinstance(confidence, numbers.Real):
            continue
        numeric_confidence = float(confidence)
        if not math.isfinite(numeric_confidence) or numeric_confidence < QUESTION_CODE_MIN_CONFIDENCE:
            continue
        candidates[code] = max(candidates.get(code, 0.0), numeric_confidence)
    return candidates, saw_code_like


def _reading_from_candidates(
    candidates: dict[str, float], saw_code_like: bool
) -> QuestionCodeReading | None:
    if len(candidates) > 1:
        return QuestionCodeReading(None, None, True, True)
    if len(candidates) == 1:
        code, confidence = next(iter(candidates.items()))
        return QuestionCodeReading(code, confidence, True, False)
    if saw_code_like:
        return QuestionCodeReading(None, None, True, False)
    return None


def read_circuit_question_code(
    image: np.ndarray, geometry: BoardGeometry | None, ocr: object
) -> QuestionCodeReading:
    """Read an optional code once from its fixed top-left screen region."""
    _validated_image(image, "read_circuit_question_code")
    del geometry  # Kept in the public signature for existing callers.
    height, width = image.shape[:2]
    crop_width = max(1, (width * QUESTION_CODE_CROP_WIDTH_PERCENT + 99) // 100)
    crop_height = max(1, (height * QUESTION_CODE_CROP_HEIGHT_PERCENT + 99) // 100)
    candidates, saw_code_like = _codes_from_boxes(
        _ocr_boxes(ocr, image[:crop_height, :crop_width])
    )
    reading = _reading_from_candidates(candidates, saw_code_like)
    if reading is not None:
        return reading
    return QuestionCodeReading(None, None, False, False)
