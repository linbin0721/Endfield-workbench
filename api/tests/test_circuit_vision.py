"""Synthetic coverage for the circuit recognition math primitives (EW-006 B1a).

Only the pure helpers ``saturated_components``, ``fit_axis_lattice``,
``square_lattices`` and ``cluster_hues`` are exercised. Every image is built in
memory from simple rectangles, no file is read and no other recognition stage
is imported.
"""

import dataclasses

import cv2
import numpy as np
import pytest

from app.puzzles.circuit.vision import (
    AxisLattice,
    ChannelClusters,
    Component,
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
