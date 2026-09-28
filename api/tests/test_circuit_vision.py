"""Synthetic coverage for the circuit recognition math primitives (EW-006 B1a).

Only the pure helpers ``saturated_components``, ``fit_axis_lattice``,
``square_lattices``, ``cluster_hues``, ``cell_evidence`` and ``classify_cell``
are exercised. Every image is built in memory from simple rectangles, no file
is read and no other recognition stage is imported.
"""

import dataclasses
import math

import cv2
import numpy as np
import pytest

from app.puzzles.circuit.vision import (
    AxisLattice,
    CellClass,
    CellEvidence,
    ChannelClusters,
    Component,
    cell_evidence,
    classify_cell,
    cluster_hues,
    fit_axis_lattice,
    saturated_components,
    square_lattices,
)


def axis_centers(lines: int, start: float, end: float) -> tuple[float, ...]:
    step = (end - start) / lines
    return tuple(start + (index + 0.5) * step for index in range(lines))


def fitted_lattice(end: float, lines: int = 4, start: float = 0.0) -> AxisLattice:
    """Clean fit used to build the two axis pitches of the square cases."""
    result = fit_axis_lattice(axis_centers(lines, start, end), start, end)
    assert result is not None
    return result


# ---------------------------------------------------------------------------
# axis lattice


def test_fit_axis_lattice_fits_a_complete_lattice() -> None:
    values = list(axis_centers(5, 0.0, 100.0))
    result = fit_axis_lattice(values, 0.0, 100.0)
    assert result is not None
    assert result.start == 0.0
    assert result.end == 100.0
    assert result.step == 20.0
    assert result.centers == pytest.approx(axis_centers(5, 0.0, 100.0))
    assert result.inlier_indices == (0, 1, 2, 3, 4)
    assert result.residual_ratio == pytest.approx(0.0)


def test_fit_axis_lattice_tolerates_a_missing_first_line() -> None:
    result = fit_axis_lattice([30.0, 50.0, 70.0, 90.0], 0.0, 100.0)
    assert result is not None
    assert len(result.centers) == 5
    assert result.step == 20.0
    assert result.inlier_indices == (0, 1, 2, 3)
    assert result.residual_ratio == pytest.approx(0.0)


def test_fit_axis_lattice_tolerates_a_missing_last_line() -> None:
    result = fit_axis_lattice([10.0, 30.0, 50.0, 70.0], 0.0, 100.0)
    assert result is not None
    assert len(result.centers) == 5
    assert result.step == 20.0
    assert result.inlier_indices == (0, 1, 2, 3)
    assert result.residual_ratio == pytest.approx(0.0)


def test_fit_axis_lattice_tolerates_a_missing_middle_line() -> None:
    result = fit_axis_lattice([10.0, 30.0, 70.0, 90.0], 0.0, 100.0)
    assert result is not None
    assert result.centers == pytest.approx(axis_centers(5, 0.0, 100.0))
    assert result.inlier_indices == (0, 1, 2, 3)
    assert result.residual_ratio == pytest.approx(0.0)


def test_fit_axis_lattice_keeps_a_two_line_gap() -> None:
    result = fit_axis_lattice([10.0, 30.0, 90.0, 110.0], 0.0, 120.0)
    assert result is not None
    assert len(result.centers) == 6
    assert result.centers == pytest.approx(axis_centers(6, 0.0, 120.0))
    assert result.inlier_indices == (0, 1, 2, 3)
    assert result.residual_ratio == pytest.approx(0.0)


def test_fit_axis_lattice_keeps_a_three_line_gap() -> None:
    result = fit_axis_lattice([10.0, 30.0, 110.0, 130.0], 0.0, 140.0)
    assert result is not None
    assert len(result.centers) == 7
    assert result.centers == pytest.approx(axis_centers(7, 0.0, 140.0))
    assert result.inlier_indices == (0, 1, 2, 3)
    assert result.residual_ratio == pytest.approx(0.0)


def test_fit_axis_lattice_drops_outliers_and_keeps_input_positions() -> None:
    values = [10.0, 145.0, 30.0, 22.0, 50.0, 0.5, 70.0, 90.0]
    result = fit_axis_lattice(values, 0.0, 100.0)
    assert result is not None
    assert result.inlier_indices == (0, 2, 4, 6, 7)
    assert [values[index] for index in result.inlier_indices] == [10.0, 30.0, 50.0, 70.0, 90.0]
    assert result.centers == pytest.approx(axis_centers(5, 0.0, 100.0))
    assert result.residual_ratio == pytest.approx(0.0)


def test_fit_axis_lattice_rejects_mismatched_boundaries() -> None:
    # The observations are exactly the centers of a five line lattice over
    # [0, 100]; the same extent shifted to [0, 90] fits no line count at all.
    values = list(axis_centers(5, 0.0, 100.0))
    assert fit_axis_lattice(values, 0.0, 90.0) is None


def test_fit_axis_lattice_returns_none_on_a_complete_tie() -> None:
    # 25 and 75 are centers of several line counts (two, six and ten) with the
    # same hit-center count, inlier count and zero residual.
    assert fit_axis_lattice([25.0, 75.0], 0.0, 100.0) is None


def test_fit_axis_lattice_is_scale_invariant() -> None:
    base = fit_axis_lattice([10.5, 30.0, 49.5, 70.0, 90.5, 140.0], 0.0, 100.0)
    scaled = fit_axis_lattice([2.625, 7.5, 12.375, 17.5, 22.625, 35.0], 0.0, 25.0)
    assert base is not None
    assert scaled is not None
    assert len(base.centers) == 5
    assert len(scaled.centers) == 5
    assert base.inlier_indices == (0, 1, 2, 3, 4)
    assert scaled.inlier_indices == (0, 1, 2, 3, 4)
    assert scaled.centers == pytest.approx([center * 0.25 for center in base.centers])
    assert base.residual_ratio == pytest.approx(0.015)
    assert scaled.residual_ratio == pytest.approx(base.residual_ratio)


# ---------------------------------------------------------------------------
# square check


def test_square_lattices_requires_both_axes() -> None:
    lattice = fitted_lattice(400.0)
    assert square_lattices(lattice, lattice) is True
    assert square_lattices(None, lattice) is False
    assert square_lattices(lattice, None) is False
    assert square_lattices(None, None) is False


def test_square_lattices_uses_the_twelve_percent_boundary() -> None:
    square = fitted_lattice(400.0)  # step 100
    wider = fitted_lattice(448.0)  # step 112: 12 / 112 stays inside
    exactly = fitted_lattice(352.0)  # step 88: 12 / 100 is the boundary
    too_far = fitted_lattice(348.0)  # step 87: 13 / 100 must be rejected
    assert square_lattices(square, wider) is True
    assert square_lattices(square, exactly) is True
    assert square_lattices(square, too_far) is False


# ---------------------------------------------------------------------------
# hue clustering


def test_cluster_hues_single_channel() -> None:
    result = cluster_hues([10, 12, 14])
    assert result is not None
    assert result.centers == pytest.approx([12.0])
    assert result.assignments == (0, 0, 0)


def test_cluster_hues_two_channels() -> None:
    result = cluster_hues([10, 12, 100, 102])
    assert result is not None
    assert result.centers == pytest.approx([11.0, 101.0])
    assert result.assignments == (0, 0, 1, 1)


def test_cluster_hues_three_channels() -> None:
    result = cluster_hues([10, 12, 70, 72, 130, 132])
    assert result is not None
    assert result.centers == pytest.approx([11.0, 71.0, 131.0])
    assert result.assignments == (0, 0, 1, 1, 2, 2)


def test_cluster_hues_four_channels() -> None:
    result = cluster_hues([10, 12, 50, 52, 90, 92, 130, 132])
    assert result is not None
    assert result.centers == pytest.approx([11.0, 51.0, 91.0, 131.0])
    assert result.assignments == (0, 0, 1, 1, 2, 2, 3, 3)


def test_cluster_hues_merges_across_the_zero_wrap() -> None:
    result = cluster_hues([0, 179])
    assert result is not None
    assert len(result.centers) == 1
    assert result.centers[0] == pytest.approx(179.5)
    assert result.assignments == (0, 0)


def test_cluster_hues_is_order_independent() -> None:
    ordered = cluster_hues([0, 5, 100, 105, 179])
    shuffled = cluster_hues([105, 179, 0, 100, 5])
    assert ordered is not None
    assert shuffled is not None
    assert ordered.assignments == (0, 0, 1, 1, 0)
    assert shuffled.assignments == (1, 0, 0, 1, 0)
    assert shuffled.centers == pytest.approx(ordered.centers)
    assert ordered.centers[0] == pytest.approx(1.33, abs=0.01)
    assert ordered.centers[1] == pytest.approx(102.5)


def test_cluster_hues_rejects_more_than_four_channels() -> None:
    five = [10, 12, 50, 52, 90, 92, 130, 132, 160, 162]
    assert cluster_hues(five) is None


def test_cluster_hues_empty_input() -> None:
    result = cluster_hues([])
    assert result == ChannelClusters(centers=(), assignments=())


# ---------------------------------------------------------------------------
# saturated components


def hsv_block(rows: list[list[tuple[int, int, int]]]) -> np.ndarray:
    """Encode an explicit OpenCV HSV (hue 0..179) row matrix as BGR pixels."""
    return cv2.cvtColor(np.array(rows, dtype=np.uint8), cv2.COLOR_HSV2BGR)


def solid(
    hue: int,
    *,
    width: int = 1,
    height: int = 1,
    saturation: int = 255,
    value: int = 255,
) -> np.ndarray:
    return hsv_block([[(hue, saturation, value)] * width for _ in range(height)])


def blank(width: int = 80, height: int = 64) -> np.ndarray:
    """Black BGR canvas: zero saturation and value, so nothing is masked."""
    return np.zeros((height, width, 3), dtype=np.uint8)


def paste(image: np.ndarray, x: int, y: int, block: np.ndarray) -> None:
    image[y : y + block.shape[0], x : x + block.shape[1]] = block


def test_saturated_components_reports_geometry_colour_and_order() -> None:
    image = blank()
    paste(image, 40, 8, solid(100, width=8, height=8, saturation=180, value=200))
    paste(image, 10, 8, solid(30, width=6, height=4))
    # A 5x1 strip whose saturation/value medians differ from their means.
    paste(
        image,
        20,
        40,
        hsv_block(
            [[(150, 100, 90), (150, 100, 90), (150, 100, 90), (150, 250, 240), (150, 250, 240)]]
        ),
    )

    result = saturated_components(image)

    assert isinstance(result, tuple)
    assert [(component.x, component.y) for component in result] == [(10, 8), (40, 8), (20, 40)]
    yellow, blue, magenta = result

    assert (yellow.x, yellow.y, yellow.width, yellow.height, yellow.area) == (10, 8, 6, 4, 24)
    assert (yellow.center_x, yellow.center_y) == pytest.approx((12.5, 9.5))
    assert yellow.hue == pytest.approx(30.0, abs=1.0)
    assert yellow.saturation == pytest.approx(255.0, abs=2.0)
    assert yellow.value == pytest.approx(255.0, abs=2.0)

    assert (blue.x, blue.y, blue.width, blue.height, blue.area) == (40, 8, 8, 8, 64)
    assert (blue.center_x, blue.center_y) == pytest.approx((43.5, 11.5))
    assert blue.hue == pytest.approx(100.0, abs=1.0)
    assert blue.saturation == pytest.approx(180.0, abs=2.0)
    assert blue.value == pytest.approx(200.0, abs=2.0)

    assert (magenta.x, magenta.y, magenta.width, magenta.height, magenta.area) == (20, 40, 5, 1, 5)
    assert (magenta.center_x, magenta.center_y) == pytest.approx((22.0, 40.0))
    assert magenta.hue == pytest.approx(150.0, abs=1.0)
    assert magenta.saturation == pytest.approx(100.0, abs=2.0)  # median, not mean 160
    assert magenta.value == pytest.approx(90.0, abs=2.0)  # median, not mean 150


def test_saturated_components_ignores_low_saturation_and_low_value() -> None:
    assert saturated_components(blank()) == ()

    image = blank()
    paste(image, 4, 4, solid(60, width=6, height=6, saturation=89))
    paste(image, 20, 4, solid(60, width=6, height=6, value=79))
    paste(image, 36, 4, solid(60, width=6, height=6, saturation=89, value=79))
    paste(image, 4, 24, solid(0, saturation=0, value=255))  # white misses the saturation gate
    paste(image, 20, 24, solid(60, width=6, height=6, saturation=200, value=160))
    paste(image, 36, 24, solid(60, width=6, height=6))

    result = saturated_components(image)

    assert [(component.x, component.y) for component in result] == [(20, 24), (36, 24)]


def test_saturated_components_averages_hue_across_the_zero_wrap() -> None:
    image = blank()
    paste(image, 8, 8, hsv_block([[(0, 255, 255)] * 3 + [(179, 255, 255)] * 3]))

    result = saturated_components(image)

    assert len(result) == 1
    hue = result[0].hue
    assert hue == pytest.approx(179.5, abs=1.0)
    # A plain arithmetic mean would land near 89.5, far from the wrap seam.
    assert min(hue, 180.0 - hue) < 1.5


def scaled_scene(offset_x: int = 0, offset_y: int = 0) -> np.ndarray:
    """Three even sized rectangles so 0.5x/2x nearest resampling stays exact."""
    image = blank()
    paste(image, 8 + offset_x, 8 + offset_y, solid(20, width=8, height=4))
    paste(image, 40 + offset_x, 8 + offset_y, solid(90, width=4, height=8))
    paste(image, 24 + offset_x, 32 + offset_y, solid(140, width=12, height=8))
    return image


def component_signature(components: tuple[Component, ...], scale: float) -> list[float]:
    """Hues, scale normalized areas and pairwise offsets of one variant."""
    first = components[0]
    signature = [component.hue for component in components]
    signature += [component.area / scale**2 for component in components]
    for component in components[1:]:
        signature.append((component.center_x - first.center_x) / scale)
        signature.append((component.center_y - first.center_y) / scale)
    return signature


def test_saturated_components_is_scale_and_translation_invariant() -> None:
    unit = scaled_scene()
    half = cv2.resize(unit, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_NEAREST)
    double = cv2.resize(unit, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_NEAREST)
    shifted = scaled_scene(offset_x=6, offset_y=10)

    base = saturated_components(unit)
    assert len(base) == 3
    expected = component_signature(base, 1.0)

    variants = (("half", half, 0.5), ("double", double, 2.0), ("shifted", shifted, 1.0))
    for name, image, scale in variants:
        components = saturated_components(image)
        assert len(components) == 3, name
        signature = component_signature(components, scale)
        assert signature == pytest.approx(expected, rel=0.1, abs=1.0), name


@pytest.mark.parametrize(
    "image",
    [
        pytest.param(np.zeros((0, 0, 3), dtype=np.uint8), id="empty"),
        pytest.param(np.zeros((8, 8), dtype=np.uint8), id="grayscale"),
        pytest.param(np.zeros((8, 8, 4), dtype=np.uint8), id="four-channel"),
        pytest.param(np.zeros((8, 8, 3), dtype=np.float32), id="float"),
    ],
)
def test_saturated_components_rejects_unsupported_images(image: np.ndarray) -> None:
    with pytest.raises(ValueError):
        saturated_components(image)


def test_saturated_components_returns_frozen_plain_values() -> None:
    image = blank()
    paste(image, 8, 8, solid(120, width=4, height=4))

    result = saturated_components(image)

    assert isinstance(result, tuple)
    assert len(result) == 1
    assert all(isinstance(component, Component) for component in result)
    assert [field.name for field in dataclasses.fields(Component)] == [
        "x",
        "y",
        "width",
        "height",
        "area",
        "center_x",
        "center_y",
        "hue",
        "saturation",
        "value",
    ]

    component = result[0]
    for field in dataclasses.fields(Component):
        value = getattr(component, field.name)
        assert not isinstance(value, np.ndarray)
        assert type(value) in (int, float)
    assert type(component.x) is int
    assert type(component.area) is int
    assert type(component.hue) is float
    assert type(component.saturation) is float

    assert Component.__dataclass_params__.frozen is True
    for field in dataclasses.fields(Component):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(component, field.name, getattr(component, field.name))


# ---------------------------------------------------------------------------
# cell evidence

CELL_SIZE = 64
CELL_HUE = 100


def dark_cell(size: int = CELL_SIZE) -> np.ndarray:
    """Dark, unsaturated background: neither bright neutral nor channel."""
    return solid(0, width=size, height=size, saturation=0, value=40)


def centered_block_cell(
    hue: int = CELL_HUE,
    *,
    size: int = CELL_SIZE,
    block: int = 24,
    saturation: int = 255,
    value: int = 255,
) -> np.ndarray:
    """One saturated square centered in the cell, well inside the edge ring."""
    image = dark_cell(size)
    offset = (size - block) // 2
    paste(
        image,
        offset,
        offset,
        solid(hue, width=block, height=block, saturation=saturation, value=value),
    )
    return image


def striped_cell(
    size: int = CELL_SIZE,
    *,
    period: int = 8,
    high: int = 220,
    low: int = 150,
) -> np.ndarray:
    """Diagonal bright neutral stripes with a large value step between them."""
    rows, columns = np.mgrid[0:size, 0:size]
    hsv = np.zeros((size, size, 3), dtype=np.uint8)
    hsv[:, :, 2] = np.where(((rows + columns) % period) < period // 2, high, low)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def evidence_for(**overrides: object) -> CellEvidence:
    """Valid placed-like evidence whose fields each test overrides as needed."""
    fields: dict[str, object] = {
        "bright_neutral_ratio": 0.0,
        "channel_ratio": 0.80,
        "centered_channel_ratio": 0.90,
        "edge_channel_ratio": 0.60,
        "stripe_ratio": 0.0,
        "channel_distances": (1.0,),
    }
    fields.update(overrides)
    return CellEvidence(**fields)  # type: ignore[arg-type]


def test_dark_cell_is_empty_with_full_confidence() -> None:
    evidence = cell_evidence(dark_cell(), [40.0])

    assert evidence.bright_neutral_ratio == 0.0
    assert evidence.channel_ratio == 0.0
    assert evidence.centered_channel_ratio == 0.0
    assert evidence.edge_channel_ratio == 0.0
    assert evidence.stripe_ratio == 0.0
    assert evidence.channel_distances == (math.inf,)
    assert classify_cell(evidence) == CellClass(kind="empty", channel=None, confidence=1.0)


def test_flat_bright_gray_is_empty_and_not_blocked() -> None:
    flat = solid(0, width=CELL_SIZE, height=CELL_SIZE, saturation=0, value=200)
    evidence = cell_evidence(flat, [40.0])

    assert evidence.bright_neutral_ratio == pytest.approx(1.0)
    assert evidence.stripe_ratio == 0.0
    result = classify_cell(evidence)
    assert result == CellClass(kind="empty", channel=None, confidence=1.0)


def test_diagonal_gray_stripes_are_blocked() -> None:
    evidence = cell_evidence(striped_cell(), [40.0])

    assert evidence.bright_neutral_ratio == pytest.approx(1.0)
    assert evidence.stripe_ratio >= 0.06
    assert evidence.channel_ratio == 0.0
    assert classify_cell(evidence) == CellClass(kind="blocked", channel=None, confidence=1.0)


def test_flat_stripes_below_the_value_step_are_not_blocked() -> None:
    # Bright neutral and striped in space, but the value step of 8 is below
    # the transition threshold of 12, so the cell must not read as blocked.
    evidence = cell_evidence(striped_cell(high=200, low=192), [40.0])

    assert evidence.bright_neutral_ratio == pytest.approx(1.0)
    assert evidence.stripe_ratio == 0.0
    assert classify_cell(evidence).kind == "empty"


def test_small_centered_block_is_fixed() -> None:
    evidence = cell_evidence(centered_block_cell(), [CELL_HUE])

    assert evidence.channel_ratio == pytest.approx(0.140625)
    assert evidence.centered_channel_ratio == pytest.approx(0.5625)
    assert evidence.edge_channel_ratio == 0.0
    assert evidence.channel_distances == pytest.approx((0.0,), abs=2.0)
    assert classify_cell(evidence) == CellClass(kind="fixed", channel=0, confidence=1.0)


def test_wide_block_that_stops_short_of_the_edge_is_fixed() -> None:
    image = dark_cell()
    paste(image, 12, 12, solid(CELL_HUE, width=40, height=40))
    evidence = cell_evidence(image, [CELL_HUE])

    assert evidence.channel_ratio == pytest.approx(0.390625)
    assert evidence.centered_channel_ratio == pytest.approx(1.0)
    assert evidence.edge_channel_ratio == 0.0
    assert classify_cell(evidence) == CellClass(kind="fixed", channel=0, confidence=1.0)


def test_block_reaching_the_edge_is_placed() -> None:
    image = dark_cell()
    paste(image, 4, 4, solid(CELL_HUE, width=56, height=56))
    evidence = cell_evidence(image, [CELL_HUE])

    assert evidence.channel_ratio == pytest.approx(0.765625)
    assert evidence.edge_channel_ratio == pytest.approx(1372 / 2332)
    assert classify_cell(evidence) == CellClass(kind="placed", channel=0, confidence=1.0)


def test_fully_covered_cell_is_placed() -> None:
    evidence = cell_evidence(
        solid(CELL_HUE, width=CELL_SIZE, height=CELL_SIZE), [CELL_HUE]
    )

    assert evidence.channel_ratio == 1.0
    assert evidence.edge_channel_ratio == 1.0
    assert classify_cell(evidence) == CellClass(kind="placed", channel=0, confidence=1.0)


def test_single_channel_block_selects_index_zero() -> None:
    evidence = cell_evidence(centered_block_cell(30), [30.0])
    result = classify_cell(evidence)

    assert evidence.channel_distances == pytest.approx((0.0,), abs=2.0)
    assert result == CellClass(kind="fixed", channel=0, confidence=1.0)


def test_two_channels_select_the_matching_index() -> None:
    first = cell_evidence(centered_block_cell(30), [30.0, 120.0])
    second = cell_evidence(centered_block_cell(120), [30.0, 120.0])

    assert first.channel_distances == pytest.approx((0.0, 90.0), abs=2.0)
    assert second.channel_distances == pytest.approx((90.0, 0.0), abs=2.0)
    assert classify_cell(first).channel == 0
    assert classify_cell(second).channel == 1


def test_four_channels_select_the_matching_index() -> None:
    hues = [10.0, 55.0, 100.0, 145.0]
    evidence = cell_evidence(centered_block_cell(100), hues)

    assert evidence.channel_distances == pytest.approx((90.0, 45.0, 0.0, 45.0), abs=2.0)
    result = classify_cell(evidence)
    assert result == CellClass(kind="fixed", channel=2, confidence=1.0)


def test_zero_and_one_seventy_nine_are_neighbours() -> None:
    evidence = cell_evidence(centered_block_cell(0), [179.0, 90.0])

    assert evidence.channel_distances[0] == pytest.approx(1.0, abs=2.0)
    assert evidence.channel_distances[1] == pytest.approx(90.0, abs=2.0)
    assert classify_cell(evidence) == CellClass(kind="fixed", channel=0, confidence=1.0)


def test_hues_are_folded_by_the_opencv_period() -> None:
    evidence = cell_evidence(centered_block_cell(10), [190.0, 100.0])

    assert evidence.channel_distances[0] == pytest.approx(0.0, abs=2.0)
    assert classify_cell(evidence).channel == 0


def test_hue_separation_of_exactly_two_is_accepted() -> None:
    evidence = cell_evidence(dark_cell(8), [10.0, 12.0])

    assert evidence.channel_distances == (math.inf, math.inf)


def test_numpy_sequence_inputs_are_accepted() -> None:
    evidence = cell_evidence(centered_block_cell(), np.array([CELL_HUE, 10.0]))

    assert len(evidence.channel_distances) == 2
    assert classify_cell(evidence).channel == 0
    assert classify_cell(evidence_for(channel_distances=np.array([1.0, 40.0]))) == CellClass(
        kind="placed", channel=0, confidence=1.0
    )


@pytest.mark.parametrize("scale", [0.5, 1.0, 2.0])
def test_cell_evidence_is_scale_invariant(scale: float) -> None:
    unit = centered_block_cell()
    scaled = (
        unit
        if scale == 1.0
        else cv2.resize(unit, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    )
    base = cell_evidence(unit, [CELL_HUE])
    evidence = cell_evidence(scaled, [CELL_HUE])

    assert evidence.bright_neutral_ratio == pytest.approx(base.bright_neutral_ratio, abs=0.01)
    assert evidence.channel_ratio == pytest.approx(base.channel_ratio, rel=0.05, abs=0.01)
    assert evidence.centered_channel_ratio == pytest.approx(
        base.centered_channel_ratio, rel=0.05, abs=0.01
    )
    assert evidence.edge_channel_ratio == pytest.approx(base.edge_channel_ratio, abs=0.01)
    assert evidence.stripe_ratio == pytest.approx(base.stripe_ratio, abs=0.01)


@pytest.mark.parametrize("scale", [0.5, 1.0, 2.0])
def test_scaled_cells_keep_the_same_kind_and_channel(scale: float) -> None:
    unit = centered_block_cell()
    scaled = (
        unit
        if scale == 1.0
        else cv2.resize(unit, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    )

    base = classify_cell(cell_evidence(unit, [CELL_HUE]))
    result = classify_cell(cell_evidence(scaled, [CELL_HUE]))

    assert base == CellClass(kind="fixed", channel=0, confidence=1.0)
    assert result == base


def test_bright_neutral_gates_are_inclusive() -> None:
    included = cell_evidence(solid(0, width=16, height=16, saturation=60, value=150), [40.0])
    too_saturated = cell_evidence(solid(0, width=16, height=16, saturation=61, value=150), [40.0])
    too_dark = cell_evidence(solid(0, width=16, height=16, saturation=60, value=149), [40.0])

    assert included.bright_neutral_ratio == 1.0
    assert too_saturated.bright_neutral_ratio == 0.0
    assert too_dark.bright_neutral_ratio == 0.0


def test_channel_gates_are_inclusive() -> None:
    at_saturation = cell_evidence(centered_block_cell(CELL_HUE, saturation=90, value=255), [100.0])
    below_saturation = cell_evidence(
        centered_block_cell(CELL_HUE, saturation=89, value=255), [100.0]
    )
    at_value = cell_evidence(centered_block_cell(CELL_HUE, saturation=255, value=80), [100.0])
    below_value = cell_evidence(centered_block_cell(CELL_HUE, saturation=255, value=79), [100.0])

    assert at_saturation.channel_ratio == pytest.approx(0.140625)
    assert at_value.channel_ratio == pytest.approx(0.140625)
    assert below_saturation.channel_ratio == 0.0
    assert below_value.channel_ratio == 0.0


def test_tied_nearest_hues_leave_the_pixel_unassigned() -> None:
    # The block hue 100 sits exactly between the two channel hues, so the
    # nearest distances are equal and no pixel may be attributed to a channel.
    evidence = cell_evidence(centered_block_cell(CELL_HUE), [95.0, 105.0])

    assert evidence.channel_ratio == 0.0
    assert evidence.channel_distances == (math.inf, math.inf)
    assert classify_cell(evidence) == CellClass(kind="empty", channel=None, confidence=1.0)


def test_cell_evidence_accepts_a_crop_view_of_a_larger_screenshot() -> None:
    screenshot = np.zeros((200, 200, 3), dtype=np.uint8)
    screenshot[50:114, 60:124] = dark_cell()
    screenshot[70:94, 80:104] = solid(CELL_HUE, width=24, height=24)
    crop = screenshot[50:114, 60:124]

    assert crop.flags["C_CONTIGUOUS"] is False
    evidence = cell_evidence(crop, [CELL_HUE])
    assert classify_cell(evidence) == CellClass(kind="fixed", channel=0, confidence=1.0)


# ---------------------------------------------------------------------------
# classification


def test_blocked_wins_over_a_placed_looking_channel_ratio() -> None:
    result = classify_cell(
        evidence_for(bright_neutral_ratio=0.5, stripe_ratio=0.5, channel_ratio=0.9)
    )
    assert result == CellClass(kind="blocked", channel=None, confidence=1.0)


def test_equal_nearest_distances_are_an_ambiguous_channel() -> None:
    result = classify_cell(evidence_for(channel_distances=(3.0, 3.0, 40.0)))
    assert result == CellClass(kind="placed", channel=None, confidence=0.0)


def test_nearly_equal_distances_are_an_ambiguous_channel() -> None:
    result = classify_cell(evidence_for(channel_distances=(3.0, 4.5, 40.0)))
    assert result == CellClass(kind="placed", channel=None, confidence=0.0)


def test_runner_up_gap_of_exactly_two_is_an_ambiguous_channel() -> None:
    result = classify_cell(evidence_for(channel_distances=(1.0, 3.0)))
    assert result == CellClass(kind="placed", channel=None, confidence=0.0)


def test_close_runner_up_keeps_the_channel_with_zero_confidence() -> None:
    result = classify_cell(evidence_for(channel_distances=(1.0, 4.0, 40.0)))
    assert result == CellClass(kind="placed", channel=0, confidence=0.0)


def test_far_runner_up_keeps_full_confidence() -> None:
    result = classify_cell(evidence_for(channel_distances=(10.0, 40.0)))
    assert result == CellClass(kind="placed", channel=0, confidence=1.0)


def test_missing_channel_keeps_the_kind_but_is_incomplete() -> None:
    assert classify_cell(evidence_for(channel_distances=())) == CellClass(
        kind="placed", channel=None, confidence=0.0
    )
    assert classify_cell(evidence_for(channel_distances=(10.5, 40.0))) == CellClass(
        kind="placed", channel=None, confidence=0.0
    )


def test_fixed_cell_with_an_ambiguous_channel_is_incomplete() -> None:
    fields = {
        "channel_ratio": 0.15,
        "centered_channel_ratio": 0.50,
        "edge_channel_ratio": 0.05,
    }
    assert classify_cell(evidence_for(channel_distances=(5.0, 6.0), **fields)) == CellClass(
        kind="fixed", channel=None, confidence=0.0
    )
    assert classify_cell(evidence_for(channel_distances=(), **fields)) == CellClass(
        kind="fixed", channel=None, confidence=0.0
    )


def test_fixed_with_a_unique_far_channel_is_confident() -> None:
    result = classify_cell(
        evidence_for(
            channel_ratio=0.15,
            centered_channel_ratio=0.50,
            edge_channel_ratio=0.05,
            channel_distances=(1.0, 40.0),
        )
    )
    assert result == CellClass(kind="fixed", channel=0, confidence=1.0)


def test_fixed_ignores_thresholds_of_the_other_kinds() -> None:
    # 0.40 is within 0.03 of the placed channel ratio 0.42, but the cell is
    # decided by the fixed rule, whose own thresholds are all far away.
    result = classify_cell(
        evidence_for(
            channel_ratio=0.40,
            centered_channel_ratio=0.50,
            edge_channel_ratio=0.05,
            channel_distances=(1.0, 40.0),
        )
    )
    assert result == CellClass(kind="fixed", channel=0, confidence=1.0)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"bright_neutral_ratio": 0.31, "stripe_ratio": 0.50}, id="bright-near"),
        pytest.param({"bright_neutral_ratio": 0.30, "stripe_ratio": 0.50}, id="bright-exact"),
        pytest.param({"bright_neutral_ratio": 0.50, "stripe_ratio": 0.061}, id="stripe-near"),
        pytest.param({"bright_neutral_ratio": 0.50, "stripe_ratio": 0.06}, id="stripe-exact"),
    ],
)
def test_blocked_near_a_threshold_has_zero_confidence(overrides: dict[str, float]) -> None:
    result = classify_cell(evidence_for(**overrides))
    assert result == CellClass(kind="blocked", channel=None, confidence=0.0)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"channel_ratio": 0.421}, id="channel-near"),
        pytest.param({"channel_ratio": 0.42}, id="channel-exact"),
        pytest.param({"edge_channel_ratio": 0.21}, id="edge-near"),
        pytest.param({"edge_channel_ratio": 0.20}, id="edge-exact"),
    ],
)
def test_placed_near_a_threshold_has_zero_confidence(overrides: dict[str, float]) -> None:
    result = classify_cell(evidence_for(channel_distances=(1.0, 40.0), **overrides))
    assert result == CellClass(kind="placed", channel=0, confidence=0.0)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"channel_ratio": 0.09}, id="channel-near"),
        pytest.param({"centered_channel_ratio": 0.21}, id="centered-near"),
        pytest.param({"edge_channel_ratio": 0.11}, id="edge-near"),
    ],
)
def test_fixed_near_a_threshold_has_zero_confidence(overrides: dict[str, float]) -> None:
    fields = {
        "channel_ratio": 0.15,
        "centered_channel_ratio": 0.50,
        "edge_channel_ratio": 0.05,
        "channel_distances": (1.0, 40.0),
    }
    fields.update(overrides)
    result = classify_cell(evidence_for(**fields))
    assert result == CellClass(kind="fixed", channel=0, confidence=0.0)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"stripe_ratio": 0.05}, id="stripe-near"),
        pytest.param({"bright_neutral_ratio": 0.29}, id="bright-near"),
        pytest.param({"channel_ratio": 0.05}, id="channel-near"),
        pytest.param({"centered_channel_ratio": 0.18}, id="centered-near"),
        pytest.param({"edge_channel_ratio": 0.10}, id="edge-near"),
    ],
)
def test_empty_near_a_classification_threshold_has_zero_confidence(
    overrides: dict[str, float],
) -> None:
    fields: dict[str, object] = {
        "bright_neutral_ratio": 0.0,
        "channel_ratio": 0.0,
        "centered_channel_ratio": 0.0,
        "edge_channel_ratio": 0.0,
        "stripe_ratio": 0.0,
        "channel_distances": (),
    }
    fields.update(overrides)
    result = classify_cell(evidence_for(**fields))
    assert result == CellClass(kind="empty", channel=None, confidence=0.0)


def test_clear_empty_is_confident() -> None:
    result = classify_cell(
        evidence_for(
            bright_neutral_ratio=0.0,
            channel_ratio=0.0,
            centered_channel_ratio=0.0,
            edge_channel_ratio=0.0,
            stripe_ratio=0.0,
            channel_distances=(),
        )
    )
    assert result == CellClass(kind="empty", channel=None, confidence=1.0)


# ---------------------------------------------------------------------------
# cell input validation


@pytest.mark.parametrize(
    "image",
    [
        pytest.param(np.zeros((0, 0, 3), dtype=np.uint8), id="empty"),
        pytest.param(np.zeros((8, 8), dtype=np.uint8), id="grayscale"),
        pytest.param(np.zeros((8, 8, 4), dtype=np.uint8), id="four-channel"),
        pytest.param(np.zeros((8, 8, 3), dtype=np.float32), id="float"),
        pytest.param(np.zeros((8, 8, 3, 1), dtype=np.uint8), id="four-dim"),
        pytest.param(None, id="not-an-array"),
        pytest.param([[0, 0, 0]], id="nested-list"),
    ],
)
def test_cell_evidence_rejects_unsupported_images(image: object) -> None:
    with pytest.raises(ValueError):
        cell_evidence(image, [10.0])  # type: ignore[arg-type]


@pytest.mark.parametrize("shape", [(7, 8, 3), (8, 7, 3), (7, 7, 3)])
def test_cell_evidence_rejects_small_cells(shape: tuple[int, int, int]) -> None:
    with pytest.raises(ValueError):
        cell_evidence(np.zeros(shape, dtype=np.uint8), [10.0])


def test_cell_evidence_accepts_the_minimum_cell_side() -> None:
    evidence = cell_evidence(np.zeros((8, 8, 3), dtype=np.uint8), [10.0])
    assert evidence.channel_distances == (math.inf,)


@pytest.mark.parametrize(
    "hues",
    [
        pytest.param([], id="empty"),
        pytest.param([0.0, 40.0, 80.0, 120.0, 160.0], id="five"),
        pytest.param([float("nan")], id="nan"),
        pytest.param([float("inf")], id="inf"),
        pytest.param([-float("inf")], id="negative-inf"),
        pytest.param([10.0, 11.5], id="too-close"),
        pytest.param([179.0, 0.5], id="too-close-across-the-wrap"),
        pytest.param([10.0, 10.0], id="duplicate"),
        pytest.param([10.0, 20.0, 30.0, 40.0, 50.0], id="more-than-four"),
        pytest.param(10.0, id="not-a-sequence"),
        pytest.param("10", id="string"),
        pytest.param(["10"], id="numeric-string"),
        pytest.param(["a", "b"], id="non-numeric"),
        pytest.param(None, id="none"),
        pytest.param(np.array(10.0), id="zero-dim-array"),
    ],
)
def test_cell_evidence_rejects_invalid_channel_hues(hues: object) -> None:
    with pytest.raises(ValueError):
        cell_evidence(dark_cell(8), hues)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"bright_neutral_ratio": 1.2}, id="bright-above-one"),
        pytest.param({"channel_ratio": -0.01}, id="channel-negative"),
        pytest.param({"centered_channel_ratio": float("nan")}, id="centered-nan"),
        pytest.param({"edge_channel_ratio": float("inf")}, id="edge-inf"),
        pytest.param({"stripe_ratio": -0.5}, id="stripe-negative"),
        pytest.param({"stripe_ratio": float("nan")}, id="stripe-nan"),
    ],
)
def test_classify_cell_rejects_invalid_ratios(overrides: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        classify_cell(evidence_for(**overrides))


@pytest.mark.parametrize(
    "distances",
    [
        pytest.param((-1.0,), id="negative"),
        pytest.param((-float("inf"),), id="negative-inf"),
        pytest.param((float("nan"),), id="nan"),
        pytest.param((1.0, float("nan")), id="nan-runner-up"),
        pytest.param(("1.0",), id="string"),
        pytest.param((1.0, "2.0"), id="string-runner-up"),
        pytest.param(None, id="none"),
        pytest.param(3.0, id="not-a-sequence"),
        pytest.param(np.array(1.0), id="zero-dim-array"),
    ],
)
def test_classify_cell_rejects_invalid_channel_distances(distances: object) -> None:
    with pytest.raises(ValueError):
        classify_cell(evidence_for(channel_distances=distances))


def test_classify_cell_rejects_other_objects() -> None:
    with pytest.raises(ValueError):
        classify_cell("not evidence")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# frozen, plain return values


def test_cell_evidence_is_frozen_and_detached_from_the_image() -> None:
    image = centered_block_cell()
    snapshot = image.copy()
    hues = [CELL_HUE, 10.0]
    evidence = cell_evidence(image, hues)

    assert np.array_equal(image, snapshot)
    assert hues == [CELL_HUE, 10.0]
    assert [field.name for field in dataclasses.fields(CellEvidence)] == [
        "bright_neutral_ratio",
        "channel_ratio",
        "centered_channel_ratio",
        "edge_channel_ratio",
        "stripe_ratio",
        "channel_distances",
    ]
    for field in dataclasses.fields(CellEvidence):
        value = getattr(evidence, field.name)
        assert not isinstance(value, np.ndarray)
        if field.name == "channel_distances":
            assert type(value) is tuple
            assert all(type(distance) is float for distance in value)
        else:
            assert type(value) is float

    assert CellEvidence.__dataclass_params__.frozen is True
    for field in dataclasses.fields(CellEvidence):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(evidence, field.name, getattr(evidence, field.name))


def test_cell_class_is_frozen_and_holds_plain_values() -> None:
    placed = classify_cell(evidence_for(channel_distances=(1.0, 40.0)))
    empty = classify_cell(
        evidence_for(
            bright_neutral_ratio=0.0,
            channel_ratio=0.0,
            centered_channel_ratio=0.0,
            edge_channel_ratio=0.0,
            stripe_ratio=0.0,
            channel_distances=(),
        )
    )

    assert [field.name for field in dataclasses.fields(CellClass)] == [
        "kind",
        "channel",
        "confidence",
    ]
    assert type(placed.kind) is str
    assert type(placed.channel) is int
    assert type(placed.confidence) is float
    assert empty.channel is None
    assert type(empty.confidence) is float

    assert CellClass.__dataclass_params__.frozen is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        placed.kind = "empty"
