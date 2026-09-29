"""Strict OCR adapter coverage for circuit screenshots (EW-006 B2b)."""

import dataclasses

import numpy as np
import pytest

from app.puzzles.circuit.ocr import (
    ConstraintToken,
    QuestionCodeReading,
    SymbolTargets,
    extract_symbol_targets,
    normalize_circuit_code,
    parse_constraint_token,
    read_circuit_question_code,
)
from app.puzzles.circuit.vision import (
    BoardGeometry,
    ConstraintGlyph,
    SymbolLayout,
)


def geometry(*, rows: int = 3, columns: int = 4, step: float = 20.0) -> BoardGeometry:
    return BoardGeometry(
        left=40.0,
        top=40.0,
        right=40.0 + columns * step,
        bottom=40.0 + rows * step,
        step=step,
        rows=rows,
        columns=columns,
        row_centers=tuple(40.0 + (index + 0.5) * step for index in range(rows)),
        column_centers=tuple(40.0 + (index + 0.5) * step for index in range(columns)),
        evidence_ratio=1.0,
        score_margin=1.0,
    )


def glyph(
    axis: str, line: int, channel: int = 0, *, left: float = 20.0, top: float = 20.0
) -> ConstraintGlyph:
    return ConstraintGlyph(
        axis=axis,  # type: ignore[arg-type]
        line_index=line,
        channel=channel,
        left=left,
        top=top,
        right=left + 4.0,
        bottom=top + 6.0,
        center_x=left + 2.0,
        center_y=top + 3.0,
        hue=20.0 + channel * 30.0,
    )


def layout(
    glyphs: tuple[ConstraintGlyph, ...],
    *,
    rows: int = 3,
    columns: int = 4,
    channels: int = 1,
) -> SymbolLayout:
    return SymbolLayout(
        geometry=geometry(rows=rows, columns=columns),
        channel_hues=tuple(20.0 + index * 30.0 for index in range(channels)),
        glyphs=glyphs,
        residual_ratio=0.0,
    )


class FakeOCR:
    def __init__(self, text_results=(), box_results=()):
        self.text_results = list(text_results)
        self.box_results = list(box_results)
        self.text_calls: list[list[np.ndarray]] = []
        self.box_calls: list[np.ndarray] = []

    def text_rec(self, crops):
        self.text_calls.append(crops)
        return self.text_results, 0.001

    def __call__(self, image):
        self.box_calls.append(image)
        result = self.box_results.pop(0) if self.box_results else []
        return result, 0.001


@pytest.mark.parametrize(
    ("text", "maximum", "value", "notation"),
    [
        ("0", 10, 0, "digits"),
        (" 10\u2003", 10, 10, "digits"),
        ("１", 10, 1, "digits"),
        ("⑩", 10, 10, "digits"),
        ("I", 10, 1, "roman"),
        ("IV", 10, 4, "roman"),
        ("Ⅸ", 10, 9, "roman"),
        ("X", 10, 10, "roman"),
        ("∅\ufe0f", 10, 0, "empty"),
        ("Ø", 10, 0, "empty"),
    ],
)
def test_parse_constraint_token_accepts_only_canonical_values(
    text: str, maximum: int, value: int, notation: str
) -> None:
    assert parse_constraint_token(text, 0.90, maximum) == ConstraintToken(
        value=value,
        notation=notation,  # type: ignore[arg-type]
        confidence=0.90,
    )


@pytest.mark.parametrize(
    ("text", "confidence", "maximum"),
    [
        ("O", 0.99, 10),
        ("1O", 0.99, 10),
        ("01", 0.99, 10),
        ("11", 0.99, 10),
        ("IIII", 0.99, 10),
        ("VX", 0.99, 10),
        ("iv", 0.99, 10),
        ("value=4", 0.99, 10),
        ("4!", 0.99, 10),
        ("4", 0.899, 10),
        ("4", float("nan"), 10),
        ("4", True, 10),
        ("4", 0.99, 3),
        ("4", 0.99, True),
    ],
)
def test_parse_constraint_token_rejects_guessing_and_invalid_values(
    text: str, confidence: object, maximum: object
) -> None:
    assert parse_constraint_token(  # type: ignore[arg-type]
        text, confidence, maximum
    ) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("V40020", "V40020"),
        ("△-V40020", "V40020"),
        ("Δ-V40020", "V40020"),
        ("∆-WL0020", "WL0020"),
        (" ▲ — WL 0020 ", "WL0020"),
        ("▵－V 40051", "V40051"),
        ("WL\u20030020", "WL0020"),
    ],
)
def test_normalize_circuit_code_accepts_only_documented_forms(
    raw: str, expected: str
) -> None:
    assert normalize_circuit_code(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "v40020",
        "WLA0020",
        "WL-A0020",
        "V4O020",
        "text V40020",
        "V40020 extra",
        "V4002",
        "WL00020",
        "△--V40020",
    ],
)
def test_normalize_circuit_code_does_not_guess(raw: str) -> None:
    assert normalize_circuit_code(raw) is None


def test_extract_symbol_targets_batches_tight_crops_and_fills_missing_keys() -> None:
    image = np.zeros((130, 150, 3), dtype=np.uint8)
    source_layout = layout(
        (
            glyph("row", 0, left=0.0, top=0.0),
            glyph("row", 1, left=18.0, top=18.0),
            glyph("column", 0, left=140.0, top=120.0),
            glyph("column", 1, left=30.0, top=30.0),
        )
    )
    ocr = FakeOCR(
        text_results=[("2", 0.99), ("I", 0.98), ("1", 0.97), ("2", 0.96)]
    )

    result = extract_symbol_targets(image, source_layout, ocr)

    assert result == SymbolTargets(
        channel_hues=(20.0,),
        row_targets=((2, 1, 0),),
        column_targets=((1, 2, 0, 0),),
        notation="mixed",
        minimum_confidence=0.96,
    )
    assert len(ocr.text_calls) == 1
    assert len(ocr.text_calls[0]) == 4
    assert ocr.text_calls[0][0].shape[:2] == (7, 5)
    assert ocr.text_calls[0][2].shape[:2] == (8, 6)
    assert all(not hasattr(value, "shape") for value in dataclasses.astuple(result))


@pytest.mark.parametrize("channels", [1, 2, 3, 4])
def test_extract_symbol_targets_supports_one_to_four_channels(channels: int) -> None:
    glyphs = tuple(
        item
        for channel in range(channels)
        for item in (glyph("row", 0, channel), glyph("column", 0, channel))
    )
    ocr = FakeOCR(text_results=[("1", 0.99)] * len(glyphs))

    result = extract_symbol_targets(
        np.zeros((140, 160, 3), dtype=np.uint8),
        layout(glyphs, rows=2, columns=2, channels=channels),
        ocr,
    )

    assert result is not None
    assert result.row_targets == ((1, 0),) * channels
    assert result.column_targets == ((1, 0),) * channels
    assert result.notation == "digits"


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        ([('I', 0.99), ('I', 0.99)], "roman"),
        ([('∅', 0.99), ('2', 0.99), ('2', 0.99)], "digits"),
    ],
)
def test_empty_tokens_do_not_change_notation(results, expected: str) -> None:
    items = (glyph("row", 0), glyph("column", 0))
    if len(results) == 3:
        items = (glyph("row", 1),) + items
    result = extract_symbol_targets(
        np.zeros((140, 160, 3), dtype=np.uint8), layout(items), FakeOCR(results)
    )
    assert result is not None and result.notation == expected


@pytest.mark.parametrize(
    "ocr_results",
    [
        [("1", 0.89), ("1", 0.99)],
        [("1", 0.99)],
        [("1", 0.99), ("bad", 0.99)],
        [("1", 0.99), None],
    ],
)
def test_extract_symbol_targets_rejects_low_missing_or_invalid_results(
    ocr_results,
) -> None:
    result = extract_symbol_targets(
        np.zeros((140, 160, 3), dtype=np.uint8),
        layout((glyph("row", 0), glyph("column", 0))),
        FakeOCR(ocr_results),
    )
    assert result is None


def test_extract_symbol_targets_rejects_duplicate_key_without_running_ocr() -> None:
    duplicate = glyph("row", 0)
    ocr = FakeOCR([("1", 0.99), ("1", 0.99)])
    assert extract_symbol_targets(
        np.zeros((140, 160, 3), dtype=np.uint8),
        layout((duplicate, duplicate)),
        ocr,
    ) is None
    assert ocr.text_calls == []


def test_extract_symbol_targets_rejects_unknown_axis_without_running_ocr() -> None:
    invalid = dataclasses.replace(glyph("row", 0), axis="diagonal")
    ocr = FakeOCR([("1", 0.99)])
    assert extract_symbol_targets(
        np.zeros((140, 160, 3), dtype=np.uint8),
        layout((invalid,)),
        ocr,
    ) is None
    assert ocr.text_calls == []


def test_row_and_column_values_use_opposite_board_dimension_limits() -> None:
    image = np.zeros((140, 180, 3), dtype=np.uint8)
    source = layout((glyph("row", 0), glyph("column", 0)), rows=2, columns=4)
    assert extract_symbol_targets(
        image, source, FakeOCR([("4", 0.99), ("2", 0.99)])
    ) is None  # sums differ after the values pass their respective bounds
    assert extract_symbol_targets(
        image, source, FakeOCR([("4", 0.99), ("3", 0.99)])
    ) is None  # column value 3 exceeds the two-row board


def boxes(*values: tuple[str, float]):
    return [([0, 0, 1, 1], text, confidence) for text, confidence in values]


def test_question_code_prefers_relative_board_region() -> None:
    ocr = FakeOCR(box_results=[boxes(("△-V40020", 0.98))])
    result = read_circuit_question_code(
        np.zeros((160, 200, 3), dtype=np.uint8), geometry(), ocr
    )
    assert result == QuestionCodeReading("V40020", 0.98, True, False)
    assert len(ocr.box_calls) == 1
    assert ocr.box_calls[0].shape[1] < 200


def test_question_code_falls_back_to_full_frame_and_downscales() -> None:
    ocr = FakeOCR(
        box_results=[boxes(("noise", 0.99)), boxes(("△-WL0020", 0.97))]
    )
    result = read_circuit_question_code(
        np.zeros((2000, 3000, 3), dtype=np.uint8), geometry(), ocr
    )
    assert result.code == "WL0020"
    assert len(ocr.box_calls) == 2
    assert max(ocr.box_calls[1].shape[:2]) == 1800


def test_question_code_without_geometry_reads_only_the_bounded_full_frame() -> None:
    ocr = FakeOCR(box_results=[boxes(("V40051", 0.96))])
    result = read_circuit_question_code(
        np.zeros((200, 300, 3), dtype=np.uint8), None, ocr
    )
    assert result.code == "V40051"
    assert len(ocr.box_calls) == 1


def test_question_code_conflict_is_ambiguous() -> None:
    ocr = FakeOCR(
        box_results=[boxes(("V40020", 0.99), ("V40051", 0.98))]
    )
    result = read_circuit_question_code(
        np.zeros((160, 200, 3), dtype=np.uint8), geometry(), ocr
    )
    assert result == QuestionCodeReading(None, None, True, True)
    assert len(ocr.box_calls) == 1


def test_question_code_low_confidence_survives_fallback_as_code_like() -> None:
    ocr = FakeOCR(
        box_results=[boxes(("V40020", 0.94)), boxes(("V40020", 0.93))]
    )
    result = read_circuit_question_code(
        np.zeros((160, 200, 3), dtype=np.uint8), geometry(), ocr
    )
    assert result == QuestionCodeReading(None, None, True, False)


def test_question_code_repeated_same_code_is_not_ambiguous() -> None:
    ocr = FakeOCR(
        box_results=[boxes(("V40020", 0.96), ("△-V40020", 0.99))]
    )
    result = read_circuit_question_code(
        np.zeros((160, 200, 3), dtype=np.uint8), geometry(), ocr
    )
    assert result == QuestionCodeReading("V40020", 0.99, True, False)


def test_ocr_results_are_frozen_plain_values() -> None:
    token = ConstraintToken(1, "digits", 0.99)
    targets = SymbolTargets((20.0,), ((1, 0),), ((1, 0),), "digits", 0.99)
    reading = QuestionCodeReading("V40020", 0.99, True, False)
    for value in (token, targets, reading):
        assert value.__dataclass_params__.frozen is True
        with pytest.raises(dataclasses.FrozenInstanceError):
            value.confidence = 0.5  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="cannot have confidence"):
        QuestionCodeReading(None, 0.99, True, False)
    with pytest.raises(ValueError, match="ambiguous"):
        QuestionCodeReading("V40020", 0.99, True, True)


@pytest.mark.parametrize(
    ("code", "confidence", "message"),
    [
        ("△-V40020", 0.99, "canonical"),
        ("V4002", 0.99, "canonical"),
        ("V40020", None, "finite"),
        ("V40020", True, "finite"),
        ("V40020", float("nan"), "finite"),
        ("V40020", -0.1, "finite"),
        ("V40020", 1.1, "finite"),
    ],
)
def test_question_code_reading_rejects_noncanonical_or_invalid_confidence(
    code: str, confidence: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        QuestionCodeReading(  # type: ignore[arg-type]
            code, confidence, True, False
        )
