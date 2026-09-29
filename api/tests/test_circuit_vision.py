"""Synthetic coverage for the circuit recognition math primitives (EW-006 B1).

Only the pure helpers ``saturated_components``, ``fit_axis_lattice``,
``square_lattices``, ``cluster_hues``, ``cell_evidence``, ``classify_cell``,
``reconstruct_piece``, bar extraction, board location, target decoding and
board cell extraction and inventory extraction are exercised. Every image is
built in memory from simple shapes, no file is read and no other recognition
stage is imported.
"""

import dataclasses
import math

import cv2
import numpy as np
import pytest

from app.puzzles.circuit.vision import (
    AxisLattice,
    BarEnsemble,
    BarStack,
    BarTargets,
    BoardCellMap,
    BoardGeometry,
    CellClass,
    CellEvidence,
    ChannelClusters,
    Component,
    InventoryPiece,
    InventoryState,
    PieceShape,
    cell_evidence,
    classify_cell,
    cluster_hues,
    extract_bar_stacks,
    extract_bar_targets,
    extract_board_cells,
    extract_inventory,
    fit_axis_lattice,
    group_bar_ensembles,
    locate_bar_board,
    reconstruct_piece,
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


# ---------------------------------------------------------------------------
# inventory piece reconstruction


PIECE_CELL = 20
# I, L, S and T tromino/tetromino shapes as normalized (row, column) cells.
PIECE_SHAPES = (
    pytest.param(((0, 0), (0, 1), (0, 2), (0, 3)), 1, 4, id="i"),
    pytest.param(((0, 0), (1, 0), (1, 1)), 2, 2, id="l"),
    pytest.param(((0, 1), (0, 2), (1, 0), (1, 1)), 2, 3, id="s"),
    pytest.param(((0, 0), (0, 1), (0, 2), (1, 1)), 2, 3, id="t"),
)

# Fixed 11x9 uncertainty fixture: a 3 px wide vertical bar with a 3 px tall
# horizontal bar attached to its middle left. It was found once by a
# deterministic seeded search over small rectangle unions and is hard coded
# here; the test never searches. Two different near-best grids explain it with
# eight occupied cells each: 5x4 at IoU 0.8431372549019608 and 4x3 at IoU
# 0.8095238095238095, only 0.0336 apart and therefore inside the default 0.04
# ambiguity margin.
AMBIGUOUS_PIECE_ROWS = (
    "......###",
    "......###",
    "......###",
    "......###",
    "#########",
    "#########",
    "#########",
    "......###",
    "......###",
    "......###",
    "......###",
)


def piece_mask(
    cells: tuple[tuple[int, int], ...],
    *,
    cell: int = PIECE_CELL,
    canvas: tuple[int, int] | None = None,
) -> np.ndarray:
    """Render one piece as a uint8 0/255 mask, optionally inside a canvas.

    The shape bounding box comes from the cells themselves, so a canvas only
    translates the piece and adds background around it.
    """
    rows = max(row for row, _ in cells) + 1
    columns = max(column for _, column in cells) + 1
    mask = np.zeros((rows * cell, columns * cell), dtype=np.uint8)
    for row, column in cells:
        mask[row * cell : (row + 1) * cell, column * cell : (column + 1) * cell] = 255
    if canvas is not None:
        framed = np.zeros(canvas, dtype=np.uint8)
        framed[3 : 3 + mask.shape[0], 5 : 5 + mask.shape[1]] = mask
        mask = framed
    return mask


def mask_from_rows(rows: tuple[str, ...]) -> np.ndarray:
    """Build a bool mask from ``#``/``.`` rows so fixed fixtures stay readable."""
    return np.array([[value == "#" for value in row] for row in rows], dtype=bool)


def rotate_cells(
    cells: tuple[tuple[int, int], ...],
    rows: int,
    columns: int,
    quarter_turns: int,
) -> tuple[tuple[int, int], ...]:
    """Cell coordinates after ``np.rot90(mask, quarter_turns)``.

    Cell ``(row, column)`` of a ``rows`` x ``columns`` grid moves to
    ``(columns - 1 - column, row)`` per counter clockwise quarter turn about
    the image, which is the orientation a rotated screenshot would show.
    """
    if quarter_turns == 0:
        rotated = tuple(cells)
    elif quarter_turns == 1:
        rotated = tuple((columns - 1 - column, row) for row, column in cells)
    elif quarter_turns == 2:
        rotated = tuple((rows - 1 - row, columns - 1 - column) for row, column in cells)
    else:
        rotated = tuple((column, rows - 1 - row) for row, column in cells)
    return tuple(sorted(rotated))


@pytest.mark.parametrize(("cells", "rows", "columns"), PIECE_SHAPES)
def test_reconstruct_piece_reads_the_square_grid(
    cells: tuple[tuple[int, int], ...], rows: int, columns: int
) -> None:
    result = reconstruct_piece(piece_mask(cells))
    assert result is not None
    assert result.cells == cells
    assert result.rows == rows
    assert result.columns == columns
    assert result.iou == pytest.approx(1.0)


@pytest.mark.parametrize("quarter_turns", [0, 1, 2, 3])
@pytest.mark.parametrize(("cells", "rows", "columns"), PIECE_SHAPES)
def test_reconstruct_piece_follows_the_image_orientation(
    cells: tuple[tuple[int, int], ...], rows: int, columns: int, quarter_turns: int
) -> None:
    rotated_mask = np.rot90(piece_mask(cells), quarter_turns)
    result = reconstruct_piece(rotated_mask)
    expected = rotate_cells(cells, rows, columns, quarter_turns)
    assert result is not None
    assert result.cells == expected
    assert result.rows == max(row for row, _ in expected) + 1
    assert result.columns == max(column for _, column in expected) + 1
    assert result.iou == pytest.approx(1.0)


@pytest.mark.parametrize(("cells", "rows", "columns"), PIECE_SHAPES)
def test_reconstruct_piece_is_scale_and_translation_invariant(
    cells: tuple[tuple[int, int], ...], rows: int, columns: int
) -> None:
    half = reconstruct_piece(piece_mask(cells, cell=PIECE_CELL // 2))
    plain = reconstruct_piece(piece_mask(cells))
    double = reconstruct_piece(piece_mask(cells, cell=PIECE_CELL * 2))
    translated = reconstruct_piece(piece_mask(cells, canvas=(200, 220)))
    assert half is not None
    assert plain is not None
    assert double is not None
    assert translated is not None
    for result in (half, plain, double, translated):
        assert result.cells == cells
        assert result.rows == rows
        assert result.columns == columns
        assert result.iou == pytest.approx(1.0, abs=0.02)


def test_reconstruct_piece_never_reads_an_l_as_a_single_cell() -> None:
    result = reconstruct_piece(piece_mask(((0, 0), (1, 0), (1, 1))))
    assert result is not None
    assert result.cells == ((0, 0), (1, 0), (1, 1))
    assert result.rows == 2
    assert result.columns == 2
    assert len(result.cells) == 3


def test_reconstruct_piece_never_reads_a_long_bar_as_a_single_cell() -> None:
    # A 1x4 bar has a 4:1 bounding box, so the 1x1 hypothesis fails the square
    # pitch check and only the four cell row survives.
    result = reconstruct_piece(piece_mask(((0, 0), (0, 1), (0, 2), (0, 3))))
    assert result is not None
    assert result.cells == ((0, 0), (0, 1), (0, 2), (0, 3))
    assert result.rows == 1
    assert result.columns == 4


def test_reconstruct_piece_eliminates_integer_multiple_subdivisions() -> None:
    # At 10 px per cell the 2x2 L is also exactly representable on a 4x4 grid
    # with 12 cells and IoU 1.0. The fewest-cell rule must keep the 3 cell
    # shape instead of the subdivision.
    result = reconstruct_piece(piece_mask(((0, 0), (1, 0), (1, 1)), cell=10), max_grid=4)
    assert result is not None
    assert result.cells == ((0, 0), (1, 0), (1, 1))
    assert result.rows == 2
    assert result.columns == 2
    assert len(result.cells) == 3
    assert result.iou == pytest.approx(1.0)


def test_reconstruct_piece_accepts_bool_and_uint8() -> None:
    boolean = reconstruct_piece(piece_mask(((0, 0), (1, 0), (1, 1))).astype(bool))
    unsigned = reconstruct_piece(piece_mask(((0, 0), (1, 0), (1, 1))))
    assert boolean is not None
    assert boolean == unsigned


def test_reconstruct_piece_treats_any_nonzero_uint8_as_foreground() -> None:
    mask = piece_mask(((0, 0), (1, 0), (1, 1)))
    mask[mask == 255] = 7
    result = reconstruct_piece(mask)
    assert result is not None
    assert result.cells == ((0, 0), (1, 0), (1, 1))


def test_reconstruct_piece_handles_a_single_pixel() -> None:
    result = reconstruct_piece(np.ones((1, 1), dtype=bool))
    assert result is not None
    assert result.cells == ((0, 0),)
    assert result.rows == 1
    assert result.columns == 1
    assert result.iou == pytest.approx(1.0)


@pytest.mark.parametrize("dtype", [np.bool_, np.uint8])
def test_reconstruct_piece_returns_none_without_foreground(dtype: type) -> None:
    assert reconstruct_piece(np.zeros((6, 7), dtype=dtype)) is None


def test_reconstruct_piece_returns_none_for_isolated_noise() -> None:
    canvas = np.zeros((50, 50), dtype=np.uint8)
    canvas[0:40, 0:40] = piece_mask(((0, 0), (1, 0), (1, 1)))
    canvas[45, 45] = 1
    assert reconstruct_piece(canvas) is None


def test_reconstruct_piece_returns_none_for_a_diagonal_touch() -> None:
    # Two blocks meeting at one corner pixel are not 4-connected.
    canvas = np.zeros((20, 20), dtype=bool)
    canvas[0:10, 0:10] = True
    canvas[10:20, 10:20] = True
    assert reconstruct_piece(canvas) is None


def test_reconstruct_piece_returns_none_for_disconnected_blocks() -> None:
    canvas = np.zeros((30, 50), dtype=bool)
    canvas[0:20, 0:20] = True
    canvas[0:20, 30:50] = True
    assert reconstruct_piece(canvas) is None


def test_reconstruct_piece_returns_none_below_the_iou_threshold() -> None:
    # A 10 px thick square ring: the only usable hypothesis is the 5x5 ring at
    # IoU 0.5625, below the 0.72 gate. Lowering the gate proves the rejection
    # came from the IoU threshold and not from a missing hypothesis.
    ring = np.ones((100, 100), dtype=bool)
    ring[10:90, 10:90] = False
    assert reconstruct_piece(ring) is None
    lowered = reconstruct_piece(ring, minimum_iou=0.5)
    assert lowered is not None
    assert lowered.rows == 5
    assert lowered.columns == 5
    assert len(lowered.cells) == 16
    assert lowered.iou == pytest.approx(0.5625)
    assert lowered.iou < 0.72
    assert reconstruct_piece(ring, minimum_iou=0.57) is None


def test_reconstruct_piece_returns_none_on_an_ambiguous_tie() -> None:
    mask = mask_from_rows(AMBIGUOUS_PIECE_ROWS)
    assert reconstruct_piece(mask) is None
    assert reconstruct_piece(mask.astype(np.uint8) * 255) is None

    # With no ambiguity margin only the single best IoU survives.
    strict = reconstruct_piece(mask, ambiguity_margin=0.0)
    assert strict is not None
    assert strict.cells == (
        (0, 3),
        (1, 3),
        (2, 0),
        (2, 1),
        (2, 2),
        (2, 3),
        (3, 3),
        (4, 3),
    )
    assert strict.rows == 5
    assert strict.columns == 4
    assert strict.iou == pytest.approx(0.8431372549019608)

    # The competing eight cell candidate is the 4x3 reading; max_grid=4 removes
    # the 5x4 winner and shows the other finalist of the tie.
    competing = reconstruct_piece(mask, max_grid=4)
    assert competing is not None
    assert competing.cells == (
        (0, 2),
        (1, 0),
        (1, 1),
        (1, 2),
        (2, 0),
        (2, 1),
        (2, 2),
        (3, 2),
    )
    assert competing.rows == 4
    assert competing.columns == 3
    assert competing.iou == pytest.approx(0.8095238095238095)
    assert len(competing.cells) == len(strict.cells) == 8


@pytest.mark.parametrize("dtype", [np.bool_, np.uint8])
def test_reconstruct_piece_does_not_modify_the_input(dtype: type) -> None:
    mask = piece_mask(((0, 0), (1, 0), (1, 1))).astype(dtype)
    snapshot = mask.copy()
    result = reconstruct_piece(mask)
    assert result is not None
    assert mask.dtype == dtype
    assert np.array_equal(mask, snapshot)


@pytest.mark.parametrize(
    "mask",
    [
        [[True, False], [False, True]],
        None,
        7,
        np.zeros((3, 3), dtype=np.float32),
        np.zeros((3, 3), dtype=np.int32),
        np.zeros((3, 3), dtype=np.uint16),
        np.zeros((3, 3, 1), dtype=bool),
        np.zeros(3, dtype=bool),
        np.zeros((0, 4), dtype=bool),
        np.zeros((4, 0), dtype=np.uint8),
        np.zeros((0, 0), dtype=bool),
    ],
)
def test_reconstruct_piece_rejects_invalid_masks(mask: object) -> None:
    with pytest.raises(ValueError):
        reconstruct_piece(mask)  # type: ignore[arg-type]


@pytest.mark.parametrize("max_grid", [0, 6, -1, True, False, 2.5, "3", None, np.int64(3)])
def test_reconstruct_piece_rejects_invalid_max_grid(max_grid: object) -> None:
    with pytest.raises(ValueError):
        reconstruct_piece(np.ones((4, 4), dtype=bool), max_grid=max_grid)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [-0.01, 1.01, float("nan"), float("inf"), float("-inf"), "0.5", None],
)
def test_reconstruct_piece_rejects_invalid_minimum_iou(value: object) -> None:
    with pytest.raises(ValueError):
        reconstruct_piece(np.ones((4, 4), dtype=bool), minimum_iou=value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [-0.01, 1.01, float("nan"), float("inf"), float("-inf"), "0.04", None],
)
def test_reconstruct_piece_rejects_invalid_ambiguity_margin(value: object) -> None:
    with pytest.raises(ValueError):
        reconstruct_piece(
            np.ones((4, 4), dtype=bool), ambiguity_margin=value  # type: ignore[arg-type]
        )


def test_reconstruct_piece_ratio_booleans_count_as_zero_and_one() -> None:
    # The two ratios only have to be finite numbers, so a Python bool passes as
    # 0/1; max_grid is the one parameter that must be a plain int.
    mask = piece_mask(((0, 0), (1, 0), (1, 1)))
    assert reconstruct_piece(mask, minimum_iou=False, ambiguity_margin=False) == (
        reconstruct_piece(mask, minimum_iou=0.0, ambiguity_margin=0.0)
    )
    assert reconstruct_piece(mask, minimum_iou=True, ambiguity_margin=True) == (
        reconstruct_piece(mask, minimum_iou=1.0, ambiguity_margin=1.0)
    )


def test_reconstruct_piece_accepts_the_unit_parameter_boundaries() -> None:
    mask = piece_mask(((0, 0), (1, 0), (1, 1)))
    # A zero gate with the widest margin pulls in the 1x1 reading at IoU 0.75,
    # which then wins on cell count; both boundary values stay legal.
    loose = reconstruct_piece(mask, minimum_iou=0.0, ambiguity_margin=1.0)
    assert loose is not None
    assert loose.cells == ((0, 0),)
    assert loose.rows == 1
    assert loose.columns == 1
    assert loose.iou == pytest.approx(0.75)

    # minimum_iou=1.0 keeps only exact fits, and max_grid=5 is the upper bound.
    exact = reconstruct_piece(mask, minimum_iou=1.0)
    assert exact is not None
    assert exact.cells == ((0, 0), (1, 0), (1, 1))
    assert exact.iou == pytest.approx(1.0)
    widest = reconstruct_piece(mask, max_grid=5)
    assert widest == exact


def test_piece_shape_is_frozen_and_holds_plain_values() -> None:
    result = reconstruct_piece(piece_mask(((0, 1), (0, 2), (1, 0), (1, 1))))
    assert result is not None
    assert [field.name for field in dataclasses.fields(PieceShape)] == [
        "cells",
        "rows",
        "columns",
        "iou",
    ]
    assert type(result.cells) is tuple
    assert all(type(cell) is tuple and len(cell) == 2 for cell in result.cells)
    assert all(type(value) is int for cell in result.cells for value in cell)
    assert list(result.cells) == sorted(result.cells)
    assert min(row for row, _ in result.cells) == 0
    assert min(column for _, column in result.cells) == 0
    assert type(result.rows) is int
    assert type(result.columns) is int
    assert type(result.iou) is float

    assert PieceShape.__dataclass_params__.frozen is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.rows = 3


# ---------------------------------------------------------------------------
# short bar stacks and ensembles
#
# Every scene is drawn from the documented ratios: a bar long side of
# 0.31 * step, a short side of 0.10 * step and a centre distance of 0.15 * step
# inside one stack. The stacks sit on the outer edge of their board side, so a
# horizontal stack grows upward from its bottom edge and a vertical stack
# grows leftward from its right edge.

BAR_LONG_RATIO = 0.31
BAR_SHORT_RATIO = 0.10
BAR_SLOT_RATIO = 0.15
SCENE_ORIGIN = (400.0, 300.0)
SCENE_MARGIN = 0.10


def draw_horizontal_bars(
    image: np.ndarray,
    centre_x: float,
    baseline_y: float,
    step: float,
    count: int,
    hue: int,
) -> None:
    """Stack ``count`` horizontal bars upward from one common bottom edge."""
    long_side = max(1, int(round(step * BAR_LONG_RATIO)))
    short_side = max(1, int(round(step * BAR_SHORT_RATIO)))
    for index in range(count):
        bottom = int(round(baseline_y - index * step * BAR_SLOT_RATIO))
        paste(
            image,
            int(round(centre_x - long_side / 2)),
            bottom - short_side,
            solid(hue, width=long_side, height=short_side),
        )


def draw_vertical_bars(
    image: np.ndarray,
    centre_y: float,
    baseline_x: float,
    step: float,
    count: int,
    hue: int,
) -> None:
    """Stack ``count`` vertical bars leftward from one common right edge."""
    long_side = max(1, int(round(step * BAR_LONG_RATIO)))
    short_side = max(1, int(round(step * BAR_SHORT_RATIO)))
    for index in range(count):
        right = int(round(baseline_x - index * step * BAR_SLOT_RATIO))
        paste(
            image,
            right - short_side,
            int(round(centre_y - long_side / 2)),
            solid(hue, width=short_side, height=long_side),
        )


def drawn_anchor(centre: float, step: float, orientation: str) -> float:
    """The centroid the renderer actually produces for one stack centre."""
    long_side = max(1, int(round(step * BAR_LONG_RATIO)))
    offset = int(round(centre - long_side / 2))
    return offset + (long_side - 1) / 2.0


def bar_scene(
    columns: tuple[int, ...] = (3, 1, 4, 0, 2),
    rows: tuple[int, ...] = (2, 5, 0, 3),
    *,
    step: float = 100.0,
    origin: tuple[float, float] = SCENE_ORIGIN,
    hue: int = 40,
    width: int = 1000,
    height: int = 800,
) -> np.ndarray:
    """A dark canvas with the top and left stacks of a virtual board."""
    image = blank(width, height)
    for index, count in enumerate(columns):
        if count <= 0:  # a zero target draws no bar at all
            continue
        draw_horizontal_bars(
            image,
            origin[0] + (index + 0.5) * step,
            origin[1] - SCENE_MARGIN * step,
            step,
            count,
            hue,
        )
    for index, count in enumerate(rows):
        if count <= 0:
            continue
        draw_vertical_bars(
            image,
            origin[1] + (index + 0.5) * step,
            origin[0] - SCENE_MARGIN * step,
            step,
            count,
            hue,
        )
    return image


def normalized_stack(
    stack: BarStack, origin: tuple[float, float], step: float
) -> tuple[float, ...]:
    """One stack in board step units relative to the scene origin."""
    if stack.orientation == "horizontal":
        anchor = (stack.anchor - origin[0]) / step
        baseline = (stack.baseline - origin[1]) / step
    else:
        anchor = (stack.anchor - origin[1]) / step
        baseline = (stack.baseline - origin[0]) / step
    return (
        anchor,
        baseline,
        stack.hue,
        stack.count,
        stack.step / step,
        stack.residual_ratio,
    )


def test_extract_bar_stacks_reads_every_stack() -> None:
    image = bar_scene()

    stacks = extract_bar_stacks(image)

    assert [stack.orientation for stack in stacks] == ["horizontal"] * 4 + ["vertical"] * 3
    assert [stack.count for stack in stacks] == [3, 1, 4, 2, 2, 5, 3]
    # The top stacks read left to right, the left stacks top to bottom.
    assert [stack.anchor for stack in stacks] == pytest.approx(
        [
            drawn_anchor(450.0, 100.0, "horizontal"),
            drawn_anchor(550.0, 100.0, "horizontal"),
            drawn_anchor(650.0, 100.0, "horizontal"),
            drawn_anchor(850.0, 100.0, "horizontal"),
            drawn_anchor(350.0, 100.0, "vertical"),
            drawn_anchor(450.0, 100.0, "vertical"),
            drawn_anchor(650.0, 100.0, "vertical"),
        ]
    )
    assert [stack.baseline for stack in stacks] == pytest.approx([290.0] * 4 + [390.0] * 3)
    assert [stack.step for stack in stacks] == pytest.approx([100.0] * 7)
    assert [stack.hue for stack in stacks] == pytest.approx([40.0] * 7, abs=1.0)
    assert [stack.residual_ratio for stack in stacks] == pytest.approx([0.0] * 7)
    assert isinstance(stacks, tuple)
    assert all(isinstance(stack, BarStack) for stack in stacks)


def test_extract_bar_stacks_returns_nothing_without_bars() -> None:
    assert extract_bar_stacks(blank()) == ()

    image = blank(300, 120)
    # A wide flat blob and a square block are no bars, however saturated.
    paste(image, 10, 10, solid(60, width=200, height=9))
    paste(image, 10, 40, solid(60, width=40, height=40))
    assert extract_bar_stacks(image) == ()


@pytest.mark.parametrize(
    ("scale", "step", "origin", "size"),
    [
        pytest.param(0.5, 100.0, (300.0, 250.0), (900, 700), id="half"),
        pytest.param(1.0, 200.0, (600.0, 500.0), (1800, 1400), id="unit"),
        pytest.param(1.0, 200.0, (637.0, 531.0), (1800, 1400), id="shifted"),
        pytest.param(2.0, 400.0, (1200.0, 1000.0), (3600, 2800), id="double"),
    ],
)
def test_extract_bar_stacks_is_scale_and_translation_invariant(
    scale: float, step: float, origin: tuple[float, float], size: tuple[int, int]
) -> None:
    image = bar_scene(
        columns=(3, 1, 4, 0, 2),
        rows=(2, 5, 0, 3),
        step=step,
        origin=origin,
        width=size[0],
        height=size[1],
    )

    stacks = extract_bar_stacks(image)

    assert [stack.count for stack in stacks] == [3, 1, 4, 2, 2, 5, 3]
    # The raw pixels follow the rendering, the normalized result does not.
    assert [stack.step for stack in stacks] == pytest.approx([200.0 * scale] * 7, rel=0.02)
    expected = [
        (0.5, -0.1, 40.0, 3, 1.0, 0.0),
        (1.5, -0.1, 40.0, 1, 1.0, 0.0),
        (2.5, -0.1, 40.0, 4, 1.0, 0.0),
        (4.5, -0.1, 40.0, 2, 1.0, 0.0),
        (0.5, -0.1, 40.0, 2, 1.0, 0.0),
        (1.5, -0.1, 40.0, 5, 1.0, 0.0),
        (3.5, -0.1, 40.0, 3, 1.0, 0.0),
    ]
    for stack, wanted in zip(stacks, expected):
        assert normalized_stack(stack, origin, step) == pytest.approx(
            wanted, rel=0.02, abs=0.02
        )


@pytest.mark.parametrize("scale", [0.5, 2.0])
def test_extract_bar_stacks_survives_resampling(scale: float) -> None:
    unit = bar_scene(columns=(3, 1, 4, 0, 2), rows=(2, 5, 0, 3), step=200.0,
                     origin=(600.0, 500.0), width=1800, height=1400)
    resampled = cv2.resize(unit, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) \
        if scale < 1.0 else cv2.resize(unit, None, fx=scale, fy=scale,
                                       interpolation=cv2.INTER_NEAREST)

    stacks = extract_bar_stacks(resampled)

    assert [stack.count for stack in stacks] == [3, 1, 4, 2, 2, 5, 3]
    origin = (600.0 * scale, 500.0 * scale)
    for stack in stacks:
        normalized = normalized_stack(stack, origin, 200.0 * scale)
        assert normalized[3] == stack.count
        assert normalized[4] == pytest.approx(1.0, rel=0.08)
        assert normalized[1] == pytest.approx(-0.1, abs=0.05)
        assert normalized[5] == pytest.approx(0.0, abs=0.05)


def test_extract_bar_stacks_is_rotation_equivalent() -> None:
    image = bar_scene(columns=(3, 1, 4, 0, 2), rows=(), step=100.0, width=1000, height=800)
    turned = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)

    upright = extract_bar_stacks(image)
    rotated = extract_bar_stacks(turned)

    assert [stack.orientation for stack in upright] == ["horizontal"] * 4
    assert [stack.orientation for stack in rotated] == ["vertical"] * 4
    # Rotating counter clockwise sends the stacks above the board to the left
    # of it, so the anchor becomes the old x mirrored in the image width and
    # the reading order turns around, while the baseline stays the bottom edge.
    assert [stack.count for stack in rotated] == list(
        reversed([stack.count for stack in upright])
    )
    for before, after in zip(reversed(upright), rotated):
        assert after.anchor == pytest.approx(1000 - 1 - before.anchor, abs=2.0)
        assert after.baseline == pytest.approx(before.baseline, abs=2.0)
        assert after.step == pytest.approx(before.step, rel=0.05)
        assert after.hue == pytest.approx(before.hue, abs=1.0)
    assert [ensemble.orientation for ensemble in group_bar_ensembles(upright)] == [
        "horizontal"
    ]
    assert [ensemble.orientation for ensemble in group_bar_ensembles(rotated)] == ["vertical"]
    assert [len(ensemble.stacks) for ensemble in group_bar_ensembles(upright)] == [4]
    assert [len(ensemble.stacks) for ensemble in group_bar_ensembles(rotated)] == [4]


def test_stacks_never_absorb_bars_of_the_other_orientation() -> None:
    # With ``origin_x == origin_y`` the anchor of top column ``i`` is numerically
    # equal to the anchor of left row ``i`` and the two bar slots of one index
    # share their coordinate too, so a candidate of the other orientation would
    # pass every anchor, hue, size and spacing test. A stack may only grow along
    # its own orientation: neither side may take a bar of the other, no stack
    # may disappear and no anchor may carry two stacks of the same orientation.
    image = bar_scene(
        columns=(3, 1, 2), rows=(2, 3, 1), step=100.0, origin=(400.0, 400.0)
    )

    stacks = extract_bar_stacks(image)
    ensembles = group_bar_ensembles(stacks)

    assert [stack.orientation for stack in stacks] == ["horizontal"] * 3 + ["vertical"] * 3
    assert [stack.count for stack in stacks] == [3, 1, 2, 2, 3, 1]
    assert [stack.baseline for stack in stacks] == pytest.approx([390.0] * 6)
    assert [ensemble.orientation for ensemble in ensembles] == ["horizontal", "vertical"]
    assert [len(ensemble.stacks) for ensemble in ensembles] == [3, 3]
    assert [stack.count for stack in ensembles[0].stacks] == [3, 1, 2]
    assert [stack.count for stack in ensembles[1].stacks] == [2, 3, 1]


def test_extract_bar_stacks_keeps_a_single_bar_and_a_full_ten() -> None:
    one = extract_bar_stacks(bar_scene(columns=(1,), rows=(), step=100.0))
    ten = extract_bar_stacks(bar_scene(columns=(10,), rows=(), step=100.0,
                                       height=900))

    assert len(one) == 1
    assert (one[0].count, one[0].step, one[0].residual_ratio) == (1, 100.0, 0.0)
    assert one[0].baseline == pytest.approx(290.0)

    assert len(ten) == 1
    assert ten[0].count == 10
    assert ten[0].step == pytest.approx(100.0)
    assert ten[0].residual_ratio == pytest.approx(0.0)
    assert ten[0].baseline == pytest.approx(290.0)
    # Ten bars reach nine slots away from the board side.
    assert ten[0].anchor == pytest.approx(drawn_anchor(450.0, 100.0, "horizontal"), abs=0.5)


def test_a_zero_target_only_leaves_a_gap() -> None:
    image = bar_scene(columns=(3, 0, 2), rows=(1, 4), step=100.0)

    stacks = extract_bar_stacks(image)
    ensembles = group_bar_ensembles(stacks)

    horizontal = [stack for stack in stacks if stack.orientation == "horizontal"]
    assert [stack.count for stack in horizontal] == [3, 2]
    assert [stack.anchor for stack in horizontal] == pytest.approx(
        [drawn_anchor(450.0, 100.0, "horizontal"), drawn_anchor(650.0, 100.0, "horizontal")]
    )
    assert [stack.baseline for stack in horizontal] == pytest.approx([290.0, 290.0])
    # The missing middle line does not stop the two stacks from sharing a side.
    assert len(ensembles) == 2
    assert [len(ensemble.stacks) for ensemble in ensembles] == [2, 2]


def test_two_colours_of_one_line_stay_two_physical_stacks() -> None:
    image = blank(1000, 800)
    step = 100.0
    baseline = 290.0
    # The second logical column carries two colours, each offset to its own
    # side of the line centre; the first column stays single colour.
    draw_horizontal_bars(image, 550.0 - 22.0, baseline, step, 2, 40)
    draw_horizontal_bars(image, 550.0 + 22.0, baseline, step, 3, 100)
    draw_horizontal_bars(image, 450.0, baseline, step, 4, 40)

    stacks = extract_bar_stacks(image)
    ensembles = group_bar_ensembles(stacks)

    assert [(stack.anchor, stack.count) for stack in stacks] == pytest.approx(
        [
            (drawn_anchor(450.0, step, "horizontal"), 4),
            (drawn_anchor(528.0, step, "horizontal"), 2),
            (drawn_anchor(572.0, step, "horizontal"), 3),
        ]
    )
    assert [stack.hue for stack in stacks] == pytest.approx([40.0, 40.0, 100.0], abs=1.0)
    assert len(ensembles) == 1
    assert [stack.count for stack in ensembles[0].stacks] == [4, 2, 3]
    assert [stack.anchor for stack in ensembles[0].stacks] == pytest.approx(
        [
            drawn_anchor(450.0, step, "horizontal"),
            drawn_anchor(528.0, step, "horizontal"),
            drawn_anchor(572.0, step, "horizontal"),
        ]
    )


def test_ensembles_keep_two_baselines_and_sort_deterministically() -> None:
    image = blank(1100, 900)
    step = 100.0
    draw_horizontal_bars(image, 450.0, 290.0, step, 3, 40)
    draw_horizontal_bars(image, 550.0, 290.0, step, 1, 40)
    draw_horizontal_bars(image, 450.0, 790.0, step, 2, 40)
    draw_horizontal_bars(image, 550.0, 790.0, step, 4, 40)

    stacks = extract_bar_stacks(image)
    ensembles = group_bar_ensembles(stacks)

    assert [(ensemble.baseline, [stack.count for stack in ensemble.stacks])
            for ensemble in ensembles] == [(290.0, [3, 1]), (790.0, [2, 4])]
    assert [ensemble.orientation for ensemble in ensembles] == ["horizontal", "horizontal"]
    # The result does not depend on the caller's order.
    assert group_bar_ensembles(tuple(reversed(stacks))) == ensembles
    assert group_bar_ensembles(list(reversed(list(stacks)))) == ensembles


def test_a_large_gap_splits_one_stack() -> None:
    image = blank(1000, 800)
    step = 100.0
    draw_horizontal_bars(image, 450.0, 290.0, step, 3, 40)
    # The fourth bar belongs to the same line but sits five slots out: three
    # empty slots are far more than one bar slot and end the stack.
    draw_horizontal_bars(image, 450.0, 290.0 - 5 * 15.0, step, 1, 40)

    stacks = extract_bar_stacks(image)

    assert len(stacks) == 2
    # Sorted by baseline: the detached bar sits one slot further from the board.
    assert [stack.count for stack in stacks] == [1, 3]
    assert [stack.anchor for stack in stacks] == pytest.approx(
        [drawn_anchor(450.0, step, "horizontal")] * 2
    )
    assert [stack.baseline for stack in stacks] == pytest.approx([215.0, 290.0])
    assert [stack.step for stack in stacks] == pytest.approx([100.0, 100.0])


def test_lone_ui_components_do_not_form_an_ensemble() -> None:
    image = blank(1000, 800)
    # Title stroke, an inventory I piece, an inventory square and the bottom
    # colour strip: all alone on their own baseline.
    paste(image, 20, 40, solid(24, width=9, height=42))
    paste(image, 880, 300, solid(50, width=12, height=48))
    paste(image, 820, 420, solid(50, width=60, height=60))
    paste(image, 400, 780, solid(100, width=40, height=10))

    stacks = extract_bar_stacks(image)

    assert group_bar_ensembles(stacks) == ()
    # The bar shaped outliers may survive as candidates, the square may not.
    assert all(stack.count == 1 for stack in stacks)
    assert len(stacks) == 3


def test_ui_outliers_do_not_disturb_the_two_board_sides() -> None:
    image = bar_scene(columns=(3, 1, 4, 2), rows=(2, 5, 3), step=100.0)
    paste(image, 20, 40, solid(24, width=9, height=42))
    paste(image, 900, 500, solid(50, width=12, height=48))
    paste(image, 850, 650, solid(50, width=60, height=60))
    paste(image, 400, 780, solid(100, width=40, height=10))

    stacks = extract_bar_stacks(image)
    ensembles = group_bar_ensembles(stacks)

    assert len(ensembles) == 2
    top, left = ensembles
    assert (top.orientation, top.baseline) == ("horizontal", 290.0)
    assert [stack.count for stack in top.stacks] == [3, 1, 4, 2]
    assert (left.orientation, left.baseline) == ("vertical", 390.0)
    assert [stack.count for stack in left.stacks] == [2, 5, 3]


@pytest.mark.parametrize(
    "image",
    [
        pytest.param(np.zeros((0, 0, 3), dtype=np.uint8), id="empty"),
        pytest.param(np.zeros((8, 8), dtype=np.uint8), id="grayscale"),
        pytest.param(np.zeros((8, 8, 4), dtype=np.uint8), id="four-channel"),
        pytest.param(np.zeros((8, 8, 3), dtype=np.float32), id="float"),
        pytest.param("not an image", id="string"),
    ],
)
def test_extract_bar_stacks_rejects_unsupported_images(image: object) -> None:
    with pytest.raises(ValueError):
        extract_bar_stacks(image)  # type: ignore[arg-type]


def test_group_bar_ensembles_validates_its_input() -> None:
    stack = BarStack(
        orientation="horizontal",
        anchor=100.0,
        baseline=200.0,
        hue=40.0,
        count=2,
        step=100.0,
        residual_ratio=0.0,
    )
    assert group_bar_ensembles([]) == ()
    assert group_bar_ensembles(()) == ()
    for broken in (
        "not a sequence",
        [stack, "not a stack"],
        [dataclasses.replace(stack, orientation="diagonal")],
        [dataclasses.replace(stack, count=0)],
        [dataclasses.replace(stack, count=11)],
        [dataclasses.replace(stack, step=0.0)],
        [dataclasses.replace(stack, step=float("nan"))],
        [dataclasses.replace(stack, anchor=math.inf)],
        [dataclasses.replace(stack, residual_ratio=-0.1)],
    ):
        with pytest.raises(ValueError):
            group_bar_ensembles(broken)  # type: ignore[arg-type]


def test_group_bar_ensembles_needs_two_anchors() -> None:
    def stack(anchor: float) -> BarStack:
        return BarStack(
            orientation="vertical",
            anchor=anchor,
            baseline=500.0,
            hue=40.0,
            count=1,
            step=100.0,
            residual_ratio=0.0,
        )

    # Two colour offsets of one logical line are still one anchor cluster.
    assert group_bar_ensembles([stack(300.0), stack(305.0)]) == ()
    # A lone stack never forms an ensemble either.
    assert group_bar_ensembles([stack(300.0)]) == ()
    ensembles = group_bar_ensembles([stack(300.0), stack(500.0)])
    assert len(ensembles) == 1
    assert [item.anchor for item in ensembles[0].stacks] == [300.0, 500.0]
    assert ensembles[0].baseline == 500.0
    assert ensembles[0].step == 100.0
    assert ensembles[0].residual_ratio == 0.0


def test_bar_structures_are_frozen_and_hold_plain_values() -> None:
    image = bar_scene()
    stacks = extract_bar_stacks(image)
    ensembles = group_bar_ensembles(stacks)

    assert [field.name for field in dataclasses.fields(BarStack)] == [
        "orientation",
        "anchor",
        "baseline",
        "hue",
        "count",
        "step",
        "residual_ratio",
    ]
    assert [field.name for field in dataclasses.fields(BarEnsemble)] == [
        "orientation",
        "baseline",
        "step",
        "stacks",
        "residual_ratio",
    ]

    for stack in stacks:
        assert type(stack.orientation) is str
        assert type(stack.anchor) is float
        assert type(stack.baseline) is float
        assert type(stack.hue) is float
        assert type(stack.count) is int
        assert type(stack.step) is float
        assert type(stack.residual_ratio) is float
        assert BarStack.__dataclass_params__.frozen is True
        with pytest.raises(dataclasses.FrozenInstanceError):
            stack.count = 2
    for ensemble in ensembles:
        assert type(ensemble.orientation) is str
        assert type(ensemble.baseline) is float
        assert type(ensemble.step) is float
        assert type(ensemble.stacks) is tuple
        assert type(ensemble.residual_ratio) is float
        assert all(isinstance(stack, BarStack) for stack in ensemble.stacks)
        assert BarEnsemble.__dataclass_params__.frozen is True
        with pytest.raises(dataclasses.FrozenInstanceError):
            ensemble.step = 1.0

    # No returned value aliases the source pixels: overwriting the image in
    # place cannot change a stack that was already extracted.
    before = stacks
    image[:] = 0
    assert extract_bar_stacks(image) == ()
    assert before == stacks


# ---------------------------------------------------------------------------
# board geometry and bar targets


def draw_board_cells(
    image: np.ndarray,
    rows: int,
    columns: int,
    *,
    step: float,
    origin: tuple[float, float],
    evidence: str = "texture",
) -> None:
    """Draw scale-relative in-cell evidence without adding bar-like shapes."""
    thickness = max(1, int(round(0.04 * step)))
    for row in range(rows):
        for column in range(columns):
            left = origin[0] + column * step
            top = origin[1] + row * step
            center_x = int(round(left + 0.5 * step))
            center_y = int(round(top + 0.5 * step))
            if evidence == "texture":
                half = int(round(0.32 * step))
                cv2.line(
                    image,
                    (center_x - half, center_y),
                    (center_x + half, center_y),
                    (180, 180, 180),
                    thickness,
                )
                cv2.line(
                    image,
                    (center_x, center_y - half),
                    (center_x, center_y + half),
                    (180, 180, 180),
                    thickness,
                )
            elif evidence == "content":
                side = max(1, int(round(0.54 * step)))
                paste(
                    image,
                    center_x - side // 2,
                    center_y - side // 2,
                    solid(75, width=side, height=side, value=160),
                )
            else:  # pragma: no cover - helper misuse, not product behavior
                raise AssertionError(f"unknown evidence mode {evidence!r}")


def draw_bar_board(
    image: np.ndarray,
    column_targets: tuple[int, ...],
    row_targets: tuple[int, ...],
    *,
    step: float,
    origin: tuple[float, float],
    hue: int = 40,
    evidence: str = "texture",
) -> None:
    draw_board_cells(
        image,
        len(row_targets),
        len(column_targets),
        step=step,
        origin=origin,
        evidence=evidence,
    )
    for column, count in enumerate(column_targets):
        if count:
            draw_horizontal_bars(
                image,
                origin[0] + (column + 0.5) * step,
                origin[1] - SCENE_MARGIN * step,
                step,
                count,
                hue,
            )
    for row, count in enumerate(row_targets):
        if count:
            draw_vertical_bars(
                image,
                origin[1] + (row + 0.5) * step,
                origin[0] - SCENE_MARGIN * step,
                step,
                count,
                hue,
            )


def located_scene(
    column_targets: tuple[int, ...],
    row_targets: tuple[int, ...],
    *,
    step: float = 60.0,
    origin: tuple[float, float] = (240.0, 210.0),
    evidence: str = "texture",
) -> tuple[np.ndarray, tuple[BarEnsemble, ...], BoardGeometry]:
    width = int(math.ceil(origin[0] + (len(column_targets) + 1.5) * step))
    height = int(math.ceil(origin[1] + (len(row_targets) + 1.5) * step))
    image = blank(width, height)
    draw_bar_board(
        image,
        column_targets,
        row_targets,
        step=step,
        origin=origin,
        evidence=evidence,
    )
    ensembles = group_bar_ensembles(extract_bar_stacks(image))
    geometry = locate_bar_board(image, ensembles)
    assert geometry is not None
    return image, ensembles, geometry


def fixed_geometry(rows: int = 4, columns: int = 4, step: float = 100.0) -> BoardGeometry:
    left, top = 400.0, 300.0
    return BoardGeometry(
        left=left,
        top=top,
        right=left + columns * step,
        bottom=top + rows * step,
        step=step,
        rows=rows,
        columns=columns,
        row_centers=tuple(top + (index + 0.5) * step for index in range(rows)),
        column_centers=tuple(left + (index + 0.5) * step for index in range(columns)),
        evidence_ratio=1.0,
        score_margin=1.0,
    )


def manual_ensemble(
    geometry: BoardGeometry,
    orientation: str,
    entries: tuple[tuple[int, float, int, float], ...],
    *,
    step: float | None = None,
    baseline: float | None = None,
) -> BarEnsemble:
    """Build stacks as ``(line, hue, count, offset_in_steps)``."""
    pitch = geometry.step if step is None else step
    centers = geometry.column_centers if orientation == "horizontal" else geometry.row_centers
    edge = geometry.top if orientation == "horizontal" else geometry.left
    side = edge - SCENE_MARGIN * geometry.step if baseline is None else baseline
    stacks = tuple(
        BarStack(
            orientation=orientation,
            anchor=float(centers[line] + offset * geometry.step),
            baseline=float(side),
            hue=float(hue),
            count=count,
            step=float(pitch),
            residual_ratio=0.0,
        )
        for line, hue, count, offset in entries
    )
    return BarEnsemble(
        orientation=orientation,
        baseline=float(side),
        step=float(pitch),
        stacks=stacks,
        residual_ratio=0.0,
    )


@pytest.mark.parametrize(
    ("step", "origin"),
    [
        pytest.param(30.0, (150.0, 135.0), id="half"),
        pytest.param(60.0, (240.0, 210.0), id="unit"),
        pytest.param(60.0, (277.0, 239.0), id="translated"),
        pytest.param(120.0, (480.0, 420.0), id="double"),
    ],
)
def test_locate_bar_board_is_scale_and_translation_invariant(
    step: float, origin: tuple[float, float]
) -> None:
    columns = (1, 1, 0, 0, 0)
    rows = (1, 1, 0, 0)
    _, ensembles, geometry = located_scene(columns, rows, step=step, origin=origin)

    assert (geometry.rows, geometry.columns) == (4, 5)
    assert geometry.step == pytest.approx(step, rel=0.04)
    assert geometry.left == pytest.approx(origin[0], abs=0.10 * step)
    assert geometry.top == pytest.approx(origin[1], abs=0.10 * step)
    assert geometry.right == pytest.approx(origin[0] + 5 * step, abs=0.20 * step)
    assert geometry.bottom == pytest.approx(origin[1] + 4 * step, abs=0.20 * step)
    targets = extract_bar_targets(geometry, ensembles)
    assert targets is not None
    assert targets.column_targets == (columns,)
    assert targets.row_targets == (rows,)


@pytest.mark.parametrize(
    ("rows", "columns"),
    [
        pytest.param(2, 2, id="minimum"),
        pytest.param(3, 7, id="wide"),
        pytest.param(7, 3, id="tall"),
        pytest.param(10, 10, id="maximum"),
    ],
)
def test_locate_bar_board_supports_two_to_ten_rectangular_lines(
    rows: int, columns: int
) -> None:
    column_targets = tuple(1 if index in (0, columns - 1) else 0 for index in range(columns))
    row_targets = tuple(1 if index in (0, rows - 1) else 0 for index in range(rows))
    _, ensembles, geometry = located_scene(column_targets, row_targets, step=42.0)

    assert (geometry.rows, geometry.columns) == (rows, columns)
    targets = extract_bar_targets(geometry, ensembles)
    assert targets is not None
    assert targets.column_targets == (column_targets,)
    assert targets.row_targets == (row_targets,)


@pytest.mark.parametrize("evidence", ["texture", "content"])
def test_locate_bar_board_accepts_texture_and_saturated_content(evidence: str) -> None:
    _, _, geometry = located_scene((1, 0, 1), (1, 0, 1), evidence=evidence)
    assert (geometry.rows, geometry.columns) == (3, 3)
    assert geometry.evidence_ratio >= 0.50


@pytest.mark.parametrize(
    ("columns", "rows"),
    [
        pytest.param((0, 1, 1, 0), (0, 1, 1), id="leading-zero"),
        pytest.param((1, 0, 1, 0), (1, 0, 1), id="middle-zero"),
        pytest.param((1, 1, 0, 0), (1, 1, 0), id="trailing-zero"),
    ],
)
def test_bar_targets_keep_legal_leading_middle_and_trailing_zeroes(
    columns: tuple[int, ...], rows: tuple[int, ...]
) -> None:
    _, ensembles, geometry = located_scene(columns, rows)
    targets = extract_bar_targets(geometry, ensembles)

    assert targets is not None
    assert targets.column_targets == (columns,)
    assert targets.row_targets == (rows,)


def test_locate_bar_board_extends_through_same_step_cells() -> None:
    # The last two lines have no physical stacks. Their complete in-cell
    # evidence makes them part of the maximal board instead of an outside ring.
    _, _, geometry = located_scene((1, 1, 0, 0), (1, 1, 0, 0, 0))
    assert (geometry.rows, geometry.columns) == (5, 4)


def test_locate_bar_board_rejects_two_equal_geometries() -> None:
    step = 50.0
    image = blank(1100, 850)
    targets = (1, 0, 1)
    draw_bar_board(image, targets, targets, step=step, origin=(150.0, 140.0))
    draw_bar_board(image, targets, targets, step=step, origin=(700.0, 560.0))
    ensembles = group_bar_ensembles(extract_bar_stacks(image))

    assert locate_bar_board(image, ensembles) is None


def test_locate_bar_board_requires_both_axis_ensembles() -> None:
    image, ensembles, _ = located_scene((1, 0, 1), (1, 0, 1))
    horizontal = tuple(item for item in ensembles if item.orientation == "horizontal")
    vertical = tuple(item for item in ensembles if item.orientation == "vertical")
    assert locate_bar_board(image, horizontal) is None
    assert locate_bar_board(image, vertical) is None


def test_locate_bar_board_rejects_thirteen_percent_step_difference() -> None:
    geometry = fixed_geometry()
    horizontal = manual_ensemble(
        geometry,
        "horizontal",
        ((0, 40.0, 1, 0.0), (3, 40.0, 1, 0.0)),
        step=100.0,
    )
    vertical = manual_ensemble(
        geometry,
        "vertical",
        ((0, 40.0, 1, 0.0), (3, 40.0, 1, 0.0)),
        step=87.0,
    )
    assert locate_bar_board(blank(1000, 800), (horizontal, vertical)) is None


def test_right_and_bottom_ui_ensembles_do_not_replace_the_board() -> None:
    columns = (1, 0, 1, 0)
    rows = (1, 0, 1, 0)
    step = 60.0
    origin = (240.0, 210.0)
    image, _, expected = located_scene(columns, rows, step=step, origin=origin)
    right = origin[0] + len(columns) * step + step
    bottom = origin[1] + len(rows) * step + step
    for index, count in ((0, 1), (2, 2)):
        draw_vertical_bars(image, origin[1] + (index + 0.5) * step, right, step, count, 95)
        draw_horizontal_bars(image, origin[0] + (index + 0.5) * step, bottom, step, count, 95)
    ensembles = group_bar_ensembles(extract_bar_stacks(image))

    actual = locate_bar_board(image, ensembles)
    assert actual is not None
    assert (actual.rows, actual.columns) == (expected.rows, expected.columns)
    assert actual.left == pytest.approx(expected.left, abs=0.02 * step)
    assert actual.top == pytest.approx(expected.top, abs=0.02 * step)
    assert extract_bar_targets(actual, ensembles) is not None


def test_extract_bar_targets_decodes_two_offset_channels() -> None:
    geometry = fixed_geometry()
    horizontal = manual_ensemble(
        geometry,
        "horizontal",
        (
            (0, 40.0, 1, -0.20),
            (1, 100.0, 2, 0.20),
            (2, 40.0, 2, -0.19),
            (2, 100.0, 1, 0.21),
            (3, 40.0, 1, -0.21),
            (3, 100.0, 1, 0.19),
        ),
    )
    vertical = manual_ensemble(
        geometry,
        "vertical",
        (
            (0, 40.0, 1, -0.20),
            (0, 100.0, 2, 0.20),
            (1, 40.0, 1, -0.19),
            (2, 40.0, 1, -0.21),
            (2, 100.0, 1, 0.21),
            (3, 40.0, 1, -0.20),
            (3, 100.0, 1, 0.19),
        ),
    )

    targets = extract_bar_targets(geometry, (horizontal, vertical))
    assert targets is not None
    assert targets.channel_hues == pytest.approx((40.0, 100.0))
    assert targets.column_targets == ((1, 0, 2, 1), (0, 2, 1, 1))
    assert targets.row_targets == ((1, 1, 1, 1), (2, 0, 1, 1))
    assert targets.residual_ratio < 0.02


def test_extract_bar_targets_rejects_cross_channel_line_over_capacity() -> None:
    geometry = fixed_geometry()
    horizontal = manual_ensemble(
        geometry,
        "horizontal",
        (
            (0, 40.0, 1, -0.20),
            (1, 40.0, 1, -0.20),
            (2, 40.0, 1, -0.20),
            (0, 100.0, 1, 0.20),
            (1, 100.0, 1, 0.20),
        ),
    )
    vertical = manual_ensemble(
        geometry,
        "vertical",
        ((0, 40.0, 3, -0.20), (0, 100.0, 2, 0.20)),
    )
    assert extract_bar_targets(geometry, (horizontal, vertical)) is None


def single_channel_ensembles(
    geometry: BoardGeometry,
    columns: tuple[tuple[int, int, float], ...],
    rows: tuple[tuple[int, int, float], ...],
) -> tuple[BarEnsemble, BarEnsemble]:
    horizontal = manual_ensemble(
        geometry,
        "horizontal",
        tuple((line, 40.0, count, offset) for line, count, offset in columns),
    )
    vertical = manual_ensemble(
        geometry,
        "vertical",
        tuple((line, 40.0, count, offset) for line, count, offset in rows),
    )
    return horizontal, vertical


@pytest.mark.parametrize(
    ("columns", "rows"),
    [
        pytest.param(
            ((0, 1, 0.0), (0, 1, 0.0), (3, 1, 0.0)),
            ((0, 1, 0.0), (3, 2, 0.0)),
            id="duplicate-line",
        ),
        pytest.param(
            ((0, 5, 0.0), (3, 1, 0.0)),
            ((0, 3, 0.0), (3, 3, 0.0)),
            id="over-capacity",
        ),
        pytest.param(
            ((0, 1, -0.29), (3, 1, 0.29)),
            ((0, 1, 0.0), (3, 1, 0.0)),
            id="unstable-offset",
        ),
        pytest.param(
            ((0, 2, 0.0), (3, 1, 0.0)),
            ((0, 1, 0.0), (3, 1, 0.0)),
            id="unequal-totals",
        ),
    ],
)
def test_extract_bar_targets_rejects_inconsistent_observations(
    columns: tuple[tuple[int, int, float], ...],
    rows: tuple[tuple[int, int, float], ...],
) -> None:
    geometry = fixed_geometry()
    assert extract_bar_targets(geometry, single_channel_ensembles(geometry, columns, rows)) is None


def test_completed_undercount_is_not_guessed() -> None:
    image, ensembles, geometry = located_scene((2, 1, 0), (1, 2, 0))
    complete = extract_bar_targets(geometry, ensembles)
    assert complete is not None
    assert complete.column_targets == ((2, 1, 0),)

    # Losing one physical bar on only one side leaves inconsistent totals. The
    # decoder returns no targets instead of manufacturing the missing count.
    horizontal, vertical = single_channel_ensembles(
        fixed_geometry(rows=3, columns=3),
        ((0, 1, 0.0), (1, 1, 0.0)),
        ((0, 1, 0.0), (1, 2, 0.0)),
    )
    assert extract_bar_targets(fixed_geometry(rows=3, columns=3), (horizontal, vertical)) is None


@pytest.mark.parametrize(
    "image",
    [
        pytest.param(np.zeros((0, 0, 3), dtype=np.uint8), id="empty"),
        pytest.param(np.zeros((8, 8), dtype=np.uint8), id="grayscale"),
        pytest.param(np.zeros((8, 8, 3), dtype=np.float32), id="float"),
        pytest.param("not an image", id="string"),
    ],
)
def test_locate_bar_board_rejects_invalid_images(image: object) -> None:
    with pytest.raises(ValueError):
        locate_bar_board(image, ())  # type: ignore[arg-type]


def test_board_public_functions_validate_objects_and_name_the_caller() -> None:
    geometry = fixed_geometry()
    good = manual_ensemble(
        geometry,
        "horizontal",
        ((0, 40.0, 1, 0.0), (3, 40.0, 1, 0.0)),
    )
    broken = dataclasses.replace(good, stacks=("not a stack", good.stacks[1]))
    with pytest.raises(ValueError, match="locate_bar_board"):
        locate_bar_board(blank(1000, 800), (broken,))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="extract_bar_targets"):
        extract_bar_targets(geometry, (broken,))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="BoardGeometry"):
        extract_bar_targets("not geometry", ())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="equally spaced"):
        extract_bar_targets(
            dataclasses.replace(geometry, column_centers=(450.0, 550.0, 675.0, 750.0)),
            (),
        )
    with pytest.raises(ValueError, match="near boundary"):
        extract_bar_targets(dataclasses.replace(geometry, left=0.0), ())
    wrong_orientation = dataclasses.replace(
        good,
        stacks=(dataclasses.replace(good.stacks[0], orientation="vertical"), good.stacks[1]),
    )
    with pytest.raises(ValueError, match="orientations must agree"):
        locate_bar_board(blank(1000, 800), (wrong_orientation,))


def test_board_results_are_frozen_plain_values_and_do_not_alias_pixels() -> None:
    image, ensembles, geometry = located_scene((1, 0, 1), (1, 0, 1))
    targets = extract_bar_targets(geometry, ensembles)
    assert targets is not None
    before = (geometry, targets)
    image[:] = 0

    assert before == (geometry, targets)
    assert BoardGeometry.__dataclass_params__.frozen is True
    assert BarTargets.__dataclass_params__.frozen is True
    assert all(type(value) is float for value in (geometry.left, geometry.top, geometry.step))
    assert type(geometry.rows) is int
    assert type(geometry.row_centers) is tuple
    assert type(targets.channel_hues) is tuple
    assert type(targets.row_targets) is tuple
    assert all(type(value) is int for channel in targets.row_targets for value in channel)
    with pytest.raises(dataclasses.FrozenInstanceError):
        geometry.rows = 3
    with pytest.raises(dataclasses.FrozenInstanceError):
        targets.residual_ratio = 1.0


# ---------------------------------------------------------------------------
# board cell map

CELL_MAP_HUES = (40, 105)


def cell_map_geometry(
    rows: int,
    columns: int,
    *,
    step: int = 100,
    origin: tuple[int, int] = (40, 30),
) -> BoardGeometry:
    left, top = origin
    return BoardGeometry(
        left=float(left),
        top=float(top),
        right=float(left + columns * step),
        bottom=float(top + rows * step),
        step=float(step),
        rows=rows,
        columns=columns,
        row_centers=tuple(float(top + (row + 0.5) * step) for row in range(rows)),
        column_centers=tuple(
            float(left + (column + 0.5) * step) for column in range(columns)
        ),
        evidence_ratio=1.0,
        score_margin=1.0,
    )


def cell_map_image(geometry: BoardGeometry) -> np.ndarray:
    return blank(int(math.ceil(geometry.right)) + 30, int(math.ceil(geometry.bottom)) + 30)


def cell_map_box(
    geometry: BoardGeometry, row: int, column: int
) -> tuple[int, int, int]:
    return (
        int(round(geometry.left + column * geometry.step)),
        int(round(geometry.top + row * geometry.step)),
        int(round(geometry.step)),
    )


def paint_colored_cell(
    image: np.ndarray,
    geometry: BoardGeometry,
    row: int,
    column: int,
    hue: int,
) -> None:
    left, top, side = cell_map_box(geometry, row, column)
    paste(image, left, top, solid(hue, width=side, height=side))


def paint_blocked_cell(
    image: np.ndarray, geometry: BoardGeometry, row: int, column: int
) -> None:
    left, top, side = cell_map_box(geometry, row, column)
    period = max(4, 2 * round(side / 10))
    paste(image, left, top, striped_cell(side, period=period, high=220, low=150))


def paint_locked_cell(
    image: np.ndarray,
    geometry: BoardGeometry,
    row: int,
    column: int,
    hue: int,
    *,
    patch_ratio: float = 0.84,
) -> None:
    """Draw one colored square with a centered, mirror-symmetric padlock."""
    left, top, side = cell_map_box(geometry, row, column)
    patch_side = max(1, int(round(patch_ratio * side)))
    patch_left = left + (side - patch_side) // 2
    patch_top = top + (side - patch_side) // 2
    base = solid(hue, width=patch_side, height=patch_side, value=255)
    paste(image, patch_left, patch_top, base)

    center_x = left + side // 2
    center_y = top + side // 2
    body_width = max(1, int(round(0.30 * side)))
    body_height = max(1, int(round(0.16 * side)))
    arch_width = max(1, int(round(0.20 * side)))
    arch_height = max(1, int(round(0.14 * side)))
    hole_width = max(1, int(round(0.10 * side)))
    hole_height = max(1, int(round(0.06 * side)))
    body_top = center_y - int(round(0.02 * side))
    arch_top = body_top - arch_height

    paste(
        image,
        center_x - body_width // 2,
        body_top,
        solid(hue, width=body_width, height=body_height, value=150),
    )
    paste(
        image,
        center_x - arch_width // 2,
        arch_top,
        solid(hue, width=arch_width, height=arch_height, value=150),
    )
    paste(
        image,
        center_x - hole_width // 2,
        body_top - hole_height,
        solid(hue, width=hole_width, height=hole_height, value=255),
    )


def render_cell_map_scene(
    *, step: int = 100, origin: tuple[int, int] = (40, 30)
) -> tuple[np.ndarray, BoardGeometry]:
    """Two-channel rectangular board containing every stable cell kind."""
    geometry = cell_map_geometry(2, 4, step=step, origin=origin)
    image = cell_map_image(geometry)
    paint_blocked_cell(image, geometry, 0, 2)
    paint_locked_cell(image, geometry, 0, 3, CELL_MAP_HUES[0])
    paint_colored_cell(image, geometry, 1, 1, CELL_MAP_HUES[1])
    paint_colored_cell(image, geometry, 1, 2, CELL_MAP_HUES[1])
    paint_locked_cell(image, geometry, 1, 3, CELL_MAP_HUES[1])
    return image, geometry


def cell_kinds_and_channels(result: BoardCellMap) -> tuple[tuple[tuple[str, int | None], ...], ...]:
    return tuple(tuple((cell.kind, cell.channel) for cell in row) for row in result.cells)


EXPECTED_CELL_MAP = (
    (("empty", None), ("empty", None), ("blocked", None), ("fixed", 0)),
    (("empty", None), ("placed", 1), ("placed", 1), ("fixed", 1)),
)


def test_extract_board_cells_recovers_every_cell_kind_and_channel() -> None:
    image, geometry = render_cell_map_scene()

    result = extract_board_cells(image, geometry, CELL_MAP_HUES)

    assert result is not None
    assert cell_kinds_and_channels(result) == EXPECTED_CELL_MAP
    assert result.minimum_confidence == min(
        cell.confidence for row in result.cells for cell in row
    )
    assert BoardCellMap.__dataclass_params__.frozen is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.minimum_confidence = 0.0


def test_adjacent_locked_cells_remain_two_fixed_cells() -> None:
    geometry = cell_map_geometry(2, 2)
    image = cell_map_image(geometry)
    paint_locked_cell(image, geometry, 0, 0, CELL_MAP_HUES[0])
    paint_locked_cell(image, geometry, 0, 1, CELL_MAP_HUES[0])

    result = extract_board_cells(image, geometry, CELL_MAP_HUES)

    assert result is not None
    assert [result.cells[0][column].kind for column in range(2)] == ["fixed", "fixed"]
    assert [result.cells[0][column].channel for column in range(2)] == [0, 0]


def test_lock_like_highlight_without_a_cell_border_remains_placed() -> None:
    geometry = cell_map_geometry(2, 2)
    image = cell_map_image(geometry)
    paint_locked_cell(
        image,
        geometry,
        0,
        0,
        CELL_MAP_HUES[0],
        patch_ratio=1.0,
    )
    paint_colored_cell(image, geometry, 0, 1, CELL_MAP_HUES[0])

    result = extract_board_cells(image, geometry, CELL_MAP_HUES)

    assert result is not None
    assert [result.cells[0][column].kind for column in range(2)] == ["placed", "placed"]


def test_single_colored_cell_without_a_lock_is_incomplete() -> None:
    geometry = cell_map_geometry(2, 2)
    image = cell_map_image(geometry)
    paint_colored_cell(image, geometry, 0, 0, CELL_MAP_HUES[0])

    assert extract_board_cells(image, geometry, CELL_MAP_HUES) is None


def test_channel_coverage_near_the_decision_boundary_is_incomplete() -> None:
    geometry = cell_map_geometry(2, 2)
    ambiguous = cell_map_image(geometry)
    paint_locked_cell(
        ambiguous,
        geometry,
        0,
        0,
        CELL_MAP_HUES[0],
        patch_ratio=0.45,
    )
    stable = cell_map_image(geometry)
    paint_locked_cell(stable, geometry, 0, 0, CELL_MAP_HUES[0], patch_ratio=0.60)

    assert extract_board_cells(ambiguous, geometry, CELL_MAP_HUES) is None
    stable_result = extract_board_cells(stable, geometry, CELL_MAP_HUES)
    assert stable_result is not None
    assert stable_result.cells[0][0] == CellClass(kind="fixed", channel=0, confidence=1.0)


def test_two_channels_in_one_cell_are_incomplete() -> None:
    geometry = cell_map_geometry(2, 2)
    image = cell_map_image(geometry)
    left, top, side = cell_map_box(geometry, 0, 0)
    paste(image, left, top, solid(CELL_MAP_HUES[0], width=side // 2, height=side))
    paste(
        image,
        left + side // 2,
        top,
        solid(CELL_MAP_HUES[1], width=side - side // 2, height=side),
    )

    assert extract_board_cells(image, geometry, CELL_MAP_HUES) is None


@pytest.mark.parametrize(
    ("step", "origin"),
    [
        pytest.param(50, (31, 47), id="half-scale-translated"),
        pytest.param(100, (73, 41), id="base-scale-translated"),
        pytest.param(200, (29, 83), id="double-scale-translated"),
    ],
)
def test_board_cell_map_is_scale_and_translation_invariant(
    step: int, origin: tuple[int, int]
) -> None:
    image, geometry = render_cell_map_scene(step=step, origin=origin)

    result = extract_board_cells(image, geometry, CELL_MAP_HUES)

    assert result is not None
    assert cell_kinds_and_channels(result) == EXPECTED_CELL_MAP


@pytest.mark.parametrize(
    "image",
    [
        pytest.param(np.zeros((0, 0, 3), dtype=np.uint8), id="empty"),
        pytest.param(np.zeros((20, 20), dtype=np.uint8), id="grayscale"),
        pytest.param(np.zeros((20, 20, 3), dtype=np.float32), id="float"),
        pytest.param("not an image", id="string"),
    ],
)
def test_extract_board_cells_rejects_invalid_images(image: object) -> None:
    with pytest.raises(ValueError):
        extract_board_cells(image, cell_map_geometry(2, 2), CELL_MAP_HUES)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "hues",
    [
        pytest.param((), id="empty"),
        pytest.param((10, 30, 50, 70, 90), id="too-many"),
        pytest.param((float("nan"),), id="not-finite"),
        pytest.param((10, 11), id="too-close"),
        pytest.param(("blue",), id="not-a-number"),
    ],
)
def test_extract_board_cells_rejects_invalid_channel_hues(hues: object) -> None:
    with pytest.raises(ValueError):
        extract_board_cells(
            cell_map_image(cell_map_geometry(2, 2)),
            cell_map_geometry(2, 2),
            hues,  # type: ignore[arg-type]
        )


def test_extract_board_cells_rejects_invalid_geometry() -> None:
    image = blank(300, 300)
    with pytest.raises(ValueError, match="BoardGeometry"):
        extract_board_cells(image, "not geometry", CELL_MAP_HUES)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="step must be positive"):
        extract_board_cells(
            image,
            dataclasses.replace(cell_map_geometry(2, 2), step=-1.0),
            CELL_MAP_HUES,
        )


def test_extract_board_cells_returns_none_for_out_of_bounds_or_tiny_board() -> None:
    image = blank(300, 300)
    outside = cell_map_geometry(2, 2, step=60, origin=(200, 200))
    tiny = cell_map_geometry(2, 2, step=5, origin=(10, 10))

    assert extract_board_cells(image, outside, CELL_MAP_HUES) is None
    assert extract_board_cells(image, tiny, CELL_MAP_HUES) is None


def test_board_cell_map_is_detached_from_source_pixels() -> None:
    image, geometry = render_cell_map_scene()
    result = extract_board_cells(image, geometry, CELL_MAP_HUES)
    assert result is not None
    before = result

    image[:] = 255

    assert result == before
    assert all(
        not isinstance(value, np.ndarray)
        for row in result.cells
        for cell in row
        for value in (cell.kind, cell.channel, cell.confidence)
    )


# ---------------------------------------------------------------------------
# inventory slots and pieces

INVENTORY_HUES = (38, 104, 145, 170)


def inventory_geometry(step: int = 100) -> BoardGeometry:
    return cell_map_geometry(2, 2, step=step, origin=(40, 180))


def inventory_slot_box(
    index: int,
    *,
    step: int,
    columns: int,
    origin: tuple[int, int],
) -> tuple[int, int, int]:
    side = round(1.57 * step)
    pitch = round(1.72 * step)
    row, column = divmod(index, columns)
    return origin[0] + column * pitch, origin[1] + row * pitch, side


def draw_inventory_slot(
    image: np.ndarray,
    index: int,
    *,
    step: int,
    columns: int,
    origin: tuple[int, int],
    value: int = 180,
) -> None:
    left, top, side = inventory_slot_box(
        index, step=step, columns=columns, origin=origin
    )
    thickness = max(2, round(0.035 * step))
    cv2.rectangle(
        image,
        (left, top),
        (left + side - 1, top + side - 1),
        (value, value, value),
        thickness,
    )


def draw_inventory_piece(
    image: np.ndarray,
    index: int,
    cells: tuple[tuple[int, int], ...],
    hue: int,
    *,
    step: int,
    columns: int,
    origin: tuple[int, int],
) -> None:
    left, top, side = inventory_slot_box(
        index, step=step, columns=columns, origin=origin
    )
    unit = max(8, round(0.24 * step))
    gap = max(1, round(0.02 * step))
    rows = max(row for row, _ in cells) + 1
    columns_count = max(column for _, column in cells) + 1
    width = columns_count * unit
    height = rows * unit
    piece_left = left + (side - width) // 2
    piece_top = top + (side - height) // 2
    for row, column in cells:
        paste(
            image,
            piece_left + column * unit + gap // 2,
            piece_top + row * unit + gap // 2,
            solid(
                hue,
                width=unit - gap,
                height=unit - gap,
                value=210,
            ),
        )


def inventory_scene(
    slot_count: int,
    pieces: dict[int, tuple[int, tuple[tuple[int, int], ...]]],
    *,
    step: int = 100,
    columns: int = 2,
    origin: tuple[int, int] | None = None,
    frame_value: int = 180,
) -> tuple[np.ndarray, BoardGeometry]:
    geometry = inventory_geometry(step)
    slot_origin = origin or (geometry.right + round(1.20 * step), round(0.40 * step))
    pitch = round(1.72 * step)
    rows = math.ceil(slot_count / columns)
    width = int(slot_origin[0] + (columns - 1) * pitch + 1.57 * step + 2.0 * step)
    height = int(max(geometry.bottom + step, slot_origin[1] + (rows + 2) * pitch))
    image = blank(width, height)
    for index in range(slot_count):
        draw_inventory_slot(
            image,
            index,
            step=step,
            columns=columns,
            origin=(int(slot_origin[0]), int(slot_origin[1])),
            value=frame_value,
        )
    for index, (channel, cells) in pieces.items():
        draw_inventory_piece(
            image,
            index,
            cells,
            INVENTORY_HUES[channel],
            step=step,
            columns=columns,
            origin=(int(slot_origin[0]), int(slot_origin[1])),
        )
    return image, geometry


@pytest.mark.parametrize(
    ("step", "origin"),
    [
        pytest.param(50, (163, 27), id="half-translated"),
        pytest.param(100, (367, 43), id="unit-translated"),
        pytest.param(200, (713, 81), id="double-translated"),
    ],
)
def test_extract_inventory_is_scale_and_translation_invariant(
    step: int, origin: tuple[int, int]
) -> None:
    shapes = {
        0: (0, ((0, 0), (0, 1), (0, 2))),
        1: (1, ((0, 0), (1, 0), (1, 1))),
        2: (2, ((0, 0), (0, 1), (1, 1), (1, 2))),
        3: (3, ((0, 0), (0, 1), (0, 2), (1, 1))),
        4: (0, ((0, 0), (1, 0), (1, 1), (2, 0))),
    }
    image, geometry = inventory_scene(5, shapes, step=step, origin=origin)

    result = extract_inventory(image, geometry, INVENTORY_HUES)

    assert result is not None
    assert (result.slot_count, result.empty_count) == (5, 0)
    assert [piece.slot_index for piece in result.pieces] == [0, 1, 2, 3, 4]
    assert [piece.channel for piece in result.pieces] == [0, 1, 2, 3, 0]
    assert [piece.cells for piece in result.pieces] == [
        shapes[index][1] for index in range(5)
    ]
    assert all(piece.iou >= 0.72 for piece in result.pieces)


def test_extract_inventory_keeps_mixed_and_all_empty_slots() -> None:
    image, geometry = inventory_scene(
        3,
        {1: (0, ((0, 0), (0, 1), (1, 0)))},
    )
    mixed = extract_inventory(image, geometry, (INVENTORY_HUES[0],))
    empty_image, empty_geometry = inventory_scene(3, {})
    empty = extract_inventory(empty_image, empty_geometry, (INVENTORY_HUES[0],))

    assert mixed is not None
    assert (mixed.slot_count, mixed.empty_count) == (3, 2)
    assert len(mixed.pieces) == 1
    assert mixed.pieces[0].slot_index == 1
    assert empty is not None
    assert (empty.slot_count, empty.empty_count, empty.pieces) == (3, 3, ())


def test_extract_inventory_uses_visible_dividers_in_solid_rectangles() -> None:
    square_image, square_geometry = inventory_scene(
        1,
        {
            0: (
                0,
                ((0, 0), (0, 1), (1, 0), (1, 1)),
            )
        },
    )
    line_image, line_geometry = inventory_scene(1, {})
    left, top, side = inventory_slot_box(
        0,
        step=100,
        columns=2,
        origin=(int(line_geometry.right + 120), 40),
    )
    cell_width, piece_height = 22, 26
    piece_left = left + (side - 4 * cell_width) // 2
    piece_top = top + (side - piece_height) // 2
    for column, cell_value in enumerate((194, 181, 152, 195)):
        paste(
            line_image,
            piece_left + column * cell_width,
            piece_top,
            solid(
                INVENTORY_HUES[0],
                width=cell_width,
                height=piece_height,
                value=cell_value,
            ),
        )

    square = extract_inventory(
        square_image, square_geometry, (INVENTORY_HUES[0],)
    )
    line = extract_inventory(line_image, line_geometry, (INVENTORY_HUES[0],))

    assert square is not None
    assert square.pieces[0].cells == ((0, 0), (0, 1), (1, 0), (1, 1))
    assert (square.pieces[0].rows, square.pieces[0].columns) == (2, 2)
    assert line is not None
    assert line.pieces[0].cells == ((0, 0), (0, 1), (0, 2), (0, 3))
    assert (line.pieces[0].rows, line.pieces[0].columns) == (1, 4)


def test_extract_inventory_accepts_a_one_column_prefix_and_low_contrast_frames() -> None:
    image, geometry = inventory_scene(
        2,
        {0: (0, ((0, 0),)), 1: (0, ((0, 0), (1, 0)))},
        columns=1,
        frame_value=35,
    )

    result = extract_inventory(image, geometry, (INVENTORY_HUES[0],))

    assert result is not None
    assert result.slot_count == 2
    assert [piece.slot_index for piece in result.pieces] == [0, 1]
    assert result.pieces[0].cells == ((0, 0),)


def test_extract_inventory_rejects_a_hole_followed_by_another_frame() -> None:
    image, geometry = inventory_scene(4, {})
    left, top, side = inventory_slot_box(
        2, step=100, columns=2, origin=(int(geometry.right + 120), 40)
    )
    image[top - 4 : top + side + 4, left - 4 : left + side + 4] = 0

    assert extract_inventory(image, geometry, (INVENTORY_HUES[0],)) is None


def test_extract_inventory_rejects_two_distinct_grids() -> None:
    image, geometry = inventory_scene(2, {})
    image = np.concatenate((image, blank(image.shape[1], 220)), axis=0)
    second_origin = (int(geometry.right + 120), 430)
    for index in range(2):
        draw_inventory_slot(
            image,
            index,
            step=100,
            columns=2,
            origin=second_origin,
        )

    assert extract_inventory(image, geometry, (INVENTORY_HUES[0],)) is None


def test_extract_inventory_rejects_unknown_or_multiple_content() -> None:
    unknown, geometry = inventory_scene(1, {})
    draw_inventory_piece(
        unknown,
        0,
        ((0, 0), (0, 1)),
        75,
        step=100,
        columns=2,
        origin=(int(geometry.right + 120), 40),
    )
    multiple, multiple_geometry = inventory_scene(1, {})
    left, top, side = inventory_slot_box(
        0,
        step=100,
        columns=2,
        origin=(int(multiple_geometry.right + 120), 40),
    )
    paste(multiple, left + side // 3, top + side // 2, solid(INVENTORY_HUES[0], width=14, height=14))
    paste(multiple, left + 2 * side // 3, top + side // 2, solid(INVENTORY_HUES[0], width=14, height=14))

    assert extract_inventory(unknown, geometry, (INVENTORY_HUES[0],)) is None
    assert extract_inventory(multiple, multiple_geometry, (INVENTORY_HUES[0],)) is None


def test_extract_inventory_rejects_content_between_two_channel_hues() -> None:
    image, geometry = inventory_scene(1, {})
    draw_inventory_piece(
        image,
        0,
        ((0, 0), (0, 1)),
        39,
        step=100,
        columns=2,
        origin=(int(geometry.right + 120), 40),
    )

    assert extract_inventory(image, geometry, (35.0, 43.0)) is None


def test_extract_inventory_rejects_a_clipped_last_slot() -> None:
    image, geometry = inventory_scene(3, {})
    _, top, side = inventory_slot_box(
        2, step=100, columns=2, origin=(int(geometry.right + 120), 40)
    )
    clipped = image[: top + side // 2]

    assert extract_inventory(clipped, geometry, (INVENTORY_HUES[0],)) is None


@pytest.mark.parametrize(
    "image",
    [
        pytest.param(np.zeros((0, 0, 3), dtype=np.uint8), id="empty"),
        pytest.param(np.zeros((20, 20), dtype=np.uint8), id="grayscale"),
        pytest.param(np.zeros((20, 20, 3), dtype=np.float32), id="float"),
        pytest.param("not an image", id="string"),
    ],
)
def test_extract_inventory_rejects_invalid_images(image: object) -> None:
    with pytest.raises(ValueError):
        extract_inventory(image, inventory_geometry(), (INVENTORY_HUES[0],))  # type: ignore[arg-type]


def test_extract_inventory_validates_geometry_and_channel_hues() -> None:
    image, geometry = inventory_scene(1, {})
    with pytest.raises(ValueError, match="BoardGeometry"):
        extract_inventory(image, "not geometry", (INVENTORY_HUES[0],))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="step must be positive"):
        extract_inventory(
            image,
            dataclasses.replace(geometry, step=-1.0),
            (INVENTORY_HUES[0],),
        )
    for hues in ((), (10, 30, 50, 70, 90), (10, 11), (float("nan"),)):
        with pytest.raises(ValueError):
            extract_inventory(image, geometry, hues)


def test_inventory_results_are_frozen_plain_values_and_detached() -> None:
    image, geometry = inventory_scene(
        2, {0: (0, ((0, 0), (0, 1), (1, 0)))}
    )
    result = extract_inventory(image, geometry, (INVENTORY_HUES[0],))
    assert result is not None
    before = result
    image[:] = 255

    assert result == before
    assert InventoryState.__dataclass_params__.frozen is True
    assert InventoryPiece.__dataclass_params__.frozen is True
    assert [field.name for field in dataclasses.fields(InventoryState)] == [
        "slot_count",
        "empty_count",
        "pieces",
        "minimum_confidence",
    ]
    assert [field.name for field in dataclasses.fields(InventoryPiece)] == [
        "slot_index",
        "channel",
        "cells",
        "rows",
        "columns",
        "iou",
        "center_x",
        "center_y",
    ]
    assert type(result.pieces) is tuple
    assert all(
        type(value) in (int, float, tuple)
        for piece in result.pieces
        for value in dataclasses.astuple(piece)
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.empty_count = 0
