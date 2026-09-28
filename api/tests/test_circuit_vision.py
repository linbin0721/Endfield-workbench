"""Synthetic coverage for the circuit recognition math primitives (EW-006 B1a).

Only the pure helpers ``fit_axis_lattice``, ``square_lattices`` and
``cluster_hues`` are exercised. No image is read and no other recognition stage
is imported.
"""

import pytest

from app.puzzles.circuit.vision import (
    AxisLattice,
    ChannelClusters,
    cluster_hues,
    fit_axis_lattice,
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
