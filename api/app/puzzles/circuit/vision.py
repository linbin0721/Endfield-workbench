"""Deterministic math primitives for circuit screenshot recognition.

The recognizer extracts observations (short-bar centers, hue samples, ...)
outside this module; the helpers here turn a screenshot into saturated
components, fit the integer line lattice, decide whether the two axis pitches
match, and cluster hues on the circular OpenCV 0..179 scale. Every function is
pure and keeps no reference to the source image or to any crop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np

HUE_PERIOD = 180.0
MIN_SATURATION = 90
MIN_VALUE = 80


@dataclass(frozen=True)
class Component:
    """One saturated connected component summarized without its pixels.

    ``x``/``y``/``width``/``height`` are the bounding box, ``area`` the pixel
    count and ``center_x``/``center_y`` the centroid. ``hue`` is the circular
    mean over the component pixels on the OpenCV 0..179 scale, while
    ``saturation`` and ``value`` are their medians. No field aliases an image
    array.
    """

    x: int
    y: int
    width: int
    height: int
    area: int
    center_x: float
    center_y: float
    hue: float
    saturation: float
    value: float


@dataclass(frozen=True)
class AxisLattice:
    """One integer line count fitted to the observations of a single axis.

    ``centers`` always holds the full lattice, including lines without an
    observation; ``inlier_indices`` are the ascending positions of the input
    ``values`` that landed within tolerance of a center, and
    ``residual_ratio`` is their mean distance to that center in units of
    ``step``.
    """

    start: float
    end: float
    step: float
    centers: tuple[float, ...]
    inlier_indices: tuple[int, ...]
    residual_ratio: float


@dataclass(frozen=True)
class ChannelClusters:
    """Circular hue clusters: ascending centers and one id per input sample."""

    centers: tuple[float, ...]
    assignments: tuple[int, ...]


def saturated_components(image: np.ndarray) -> tuple[Component, ...]:
    """Extract the 8-connected saturated components of one BGR screenshot.

    ``image`` must be a non-empty uint8 array with three BGR channels, anything
    else raises ``ValueError``. The mask keeps pixels whose OpenCV HSV
    saturation is at least ``MIN_SATURATION`` and whose value is at least
    ``MIN_VALUE``. No morphology and no size filter is applied: the caller fits
    the grid lattice and rejects UI outliers (title strokes, inventory pieces,
    the bottom colour strip) by their distance to that lattice.

    Every component keeps its bounding box, pixel area and centroid. Because
    the hue scale is circular (0 and 179 are neighbours), ``hue`` is the
    circular mean of the component pixels; a fully cancelled resultant falls
    back to 0.0. ``saturation`` and ``value`` are plain medians. The result is
    sorted by ``(y, x, center_y, center_x)`` so repeated runs on the same image
    give the same order.
    """
    if not isinstance(image, np.ndarray):
        raise ValueError("saturated_components expects a numpy array")
    if image.dtype != np.uint8:
        raise ValueError(f"saturated_components expects uint8 pixels, got {image.dtype}")
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(
            f"saturated_components expects a three channel BGR image, got shape {image.shape}"
        )
    if image.size == 0:
        raise ValueError("saturated_components expects a non-empty image")

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue_plane = hsv[:, :, 0]
    saturation_plane = hsv[:, :, 1]
    value_plane = hsv[:, :, 2]
    mask = ((saturation_plane >= MIN_SATURATION) & (value_plane >= MIN_VALUE)).astype(np.uint8)
    label_count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

    components: list[Component] = []
    for label in range(1, label_count):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        width = int(stats[label, cv2.CC_STAT_WIDTH])
        height = int(stats[label, cv2.CC_STAT_HEIGHT])
        window = (slice(y, y + height), slice(x, x + width))
        member = labels[window] == label
        hues = hue_plane[window][member].astype(np.float64)
        angles = np.radians(hues * (360.0 / HUE_PERIOD))
        sin_sum = float(np.sin(angles).sum())
        cos_sum = float(np.cos(angles).sum())
        components.append(
            Component(
                x=x,
                y=y,
                width=width,
                height=height,
                area=int(stats[label, cv2.CC_STAT_AREA]),
                center_x=float(centroids[label][0]),
                center_y=float(centroids[label][1]),
                hue=math.degrees(math.atan2(sin_sum, cos_sum)) / 2.0 % HUE_PERIOD,
                saturation=float(np.median(saturation_plane[window][member])),
                value=float(np.median(value_plane[window][member])),
            )
        )

    components.sort(
        key=lambda component: (component.y, component.x, component.center_y, component.center_x)
    )
    return tuple(components)


def fit_axis_lattice(
    values: Sequence[float],
    start: float,
    end: float,
    *,
    min_lines: int = 2,
    max_lines: int = 10,
    tolerance_ratio: float = 0.12,
) -> AxisLattice | None:
    """Fit ``min_lines``..``max_lines`` equally spaced centers to one axis.

    For every line count the pitch is ``(end - start) / lines`` and the center
    of line ``i`` is ``start + (i + 0.5) * pitch``. An observation is an inlier
    when it is at most ``tolerance_ratio * pitch`` away from the nearest
    center, and a candidate only counts when it explains observations on at
    least two different centers. Candidates are ranked by the number of
    explained centers, then by the number of explained observations, then by
    the smallest mean normalized residual. A complete three way tie between
    different line counts is ambiguous and returns ``None``.
    """
    if not values or end <= start or max_lines < min_lines or tolerance_ratio < 0.0:
        return None

    span = end - start
    candidates: list[tuple[tuple[int, int, float], AxisLattice]] = []
    for lines in range(max(1, min_lines), max_lines + 1):
        step = span / lines
        slack = tolerance_ratio * step
        centers = tuple(start + (index + 0.5) * step for index in range(lines))
        inlier_indices: list[int] = []
        hit_centers: set[int] = set()
        residual_sum = 0.0
        for position, value in enumerate(values):
            nearest = min(range(lines), key=lambda index: abs(centers[index] - value))
            distance = abs(centers[nearest] - value)
            if distance > slack:
                continue
            inlier_indices.append(position)
            hit_centers.add(nearest)
            residual_sum += distance / step
        if len(hit_centers) < 2:
            continue
        residual_ratio = residual_sum / len(inlier_indices)
        candidates.append(
            (
                (len(hit_centers), len(inlier_indices), -residual_ratio),
                AxisLattice(
                    start=start,
                    end=end,
                    step=step,
                    centers=centers,
                    inlier_indices=tuple(inlier_indices),
                    residual_ratio=residual_ratio,
                ),
            )
        )

    if not candidates:
        return None
    best_key = max(key for key, _ in candidates)
    best = [lattice for key, lattice in candidates if key == best_key]
    if len(best) != 1:
        return None
    return best[0]


def square_lattices(
    columns: AxisLattice | None,
    rows: AxisLattice | None,
    *,
    max_delta_ratio: float = 0.12,
) -> bool:
    """Whether both fitted axes share the same pitch within ``max_delta_ratio``.

    A missing fit on either axis never counts as square.
    """
    if columns is None or rows is None:
        return False
    scale = max(columns.step, rows.step)
    if scale <= 0.0:
        return False
    return abs(columns.step - rows.step) / scale <= max_delta_ratio


def cluster_hues(
    hues: Sequence[float],
    *,
    max_channels: int = 4,
    merge_distance: float = 10.0,
) -> ChannelClusters | None:
    """Cluster OpenCV hues (0..179) into circular groups.

    Two samples belong to the same channel as long as they are chained through
    circular neighbors that are at most ``merge_distance`` apart, so 0 and 179
    merge across the wrap. Cluster centers are circular means, channels are
    numbered by ascending center, and ``assignments`` follows the input order.
    An empty input returns empty clusters; more than ``max_channels`` clusters
    return ``None``.
    """
    values = tuple(float(hue) for hue in hues)
    if not values:
        return ChannelClusters(centers=(), assignments=())
    if max_channels < 1:
        return None

    positions = tuple(value % HUE_PERIOD for value in values)
    order = sorted(range(len(values)), key=lambda index: positions[index])

    cuts: list[int] = []
    for offset, index in enumerate(order):
        following = order[(offset + 1) % len(order)]
        gap = (positions[following] - positions[index]) % HUE_PERIOD
        if gap > merge_distance:
            cuts.append(offset)

    groups: list[list[int]] = []
    if not cuts:
        groups.append(list(order))
    else:
        for offset, cut in enumerate(cuts):
            if offset + 1 < len(cuts):
                groups.append(list(order[cut + 1 : cuts[offset + 1] + 1]))
            else:
                groups.append(list(order[cut + 1 :]) + list(order[: cuts[0] + 1]))

    def circular_mean(indices: Sequence[int]) -> float:
        sin_sum = math.fsum(math.sin(math.radians(positions[index] * 2.0)) for index in indices)
        cos_sum = math.fsum(math.cos(math.radians(positions[index] * 2.0)) for index in indices)
        return (math.degrees(math.atan2(sin_sum, cos_sum)) / 2.0) % HUE_PERIOD

    clusters = sorted(((circular_mean(group), group) for group in groups), key=lambda item: item[0])
    if len(clusters) > max_channels:
        return None

    centers: list[float] = []
    assignments = [0] * len(values)
    for channel, (center, group) in enumerate(clusters):
        centers.append(center)
        for position in group:
            assignments[position] = channel
    return ChannelClusters(centers=tuple(centers), assignments=tuple(assignments))
