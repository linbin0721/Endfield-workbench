"""Deterministic math primitives for circuit screenshot recognition.

The recognizer extracts observations (short-bar centers, hue samples, ...)
outside this module; the helpers here turn a screenshot into saturated
components, fit the integer line lattice, decide whether the two axis pitches
match, cluster hues on the circular OpenCV 0..179 scale, summarize a single
board cell as immutable evidence with a fixed classification, rebuild one
already segmented inventory piece mask as an immutable square grid shape,
reduce a full screenshot to the short bar stacks of both board sides plus the
candidate ensembles that share a baseline, and finally turn those candidates
into the unique board rectangle with its per channel row and column targets.
Every function is pure and keeps no reference to the source image or to any
crop.
"""

from __future__ import annotations

import math
import numbers
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

HUE_PERIOD = 180.0
MIN_SATURATION = 90
MIN_VALUE = 80

# Per cell evidence and classification constants. Every spatial fraction is
# relative to the cell crop, never to an absolute screenshot coordinate.
MIN_CELL_SIDE = 8
MAX_CHANNELS = 4
BRIGHT_NEUTRAL_MAX_SATURATION = 60
BRIGHT_NEUTRAL_MIN_VALUE = 150
CHANNEL_HUE_TOLERANCE = 10.0
MIN_CHANNEL_HUE_SEPARATION = 2.0
DISTANCE_TIE_TOLERANCE = 1e-9
CENTER_LOW = 0.25
CENTER_HIGH = 0.75
EDGE_INNER_LOW = 0.18
EDGE_INNER_HIGH = 0.82
STRIPE_GRID = 32
STRIPE_MIN_VALUE_DELTA = 12

BLOCKED_BRIGHT_NEUTRAL_RATIO = 0.30
BLOCKED_STRIPE_RATIO = 0.06
PLACED_CHANNEL_RATIO = 0.42
PLACED_EDGE_CHANNEL_RATIO = 0.20
FIXED_CHANNEL_RATIO = 0.08
FIXED_CENTERED_CHANNEL_RATIO = 0.20
FIXED_EDGE_CHANNEL_RATIO = 0.12
CONFIDENCE_THRESHOLD_MARGIN = 0.03
CHANNEL_AMBIGUITY_MARGIN = 2.0
CHANNEL_CONFIDENCE_MARGIN = 4.0


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


# ---------------------------------------------------------------------------
# single cell evidence and classification


@dataclass(frozen=True)
class CellEvidence:
    """Normalized measurements of one cell crop; no field aliases pixels.

    All ratios are shares of the cell (or of one sub region) in ``0..1`` and
    do not depend on the crop size. ``channel_distances`` follows the caller's
    hue order and holds the circular distance from the mean hue of the channel
    pixels to every input hue, or ``math.inf`` when the cell has none.
    """

    bright_neutral_ratio: float
    channel_ratio: float
    centered_channel_ratio: float
    edge_channel_ratio: float
    stripe_ratio: float
    channel_distances: tuple[float, ...]


@dataclass(frozen=True)
class CellClass:
    """Fixed classification of one cell with its confidence in ``0..1``.

    ``channel`` is ``None`` for ``empty``/``blocked`` and also for a
    ``fixed``/``placed`` cell whose channel could not be told apart from the
    evidence; the latter keeps ``confidence == 0.0`` so the caller treats the
    statement as incomplete instead of as an empty cell.
    """

    kind: Literal["empty", "blocked", "fixed", "placed"]
    channel: int | None
    confidence: float


def _circular_hue_distance(first: float, second: float) -> float:
    """Shortest distance between two angles on the circular 0..179 hue scale."""
    delta = abs(first - second) % HUE_PERIOD
    return min(delta, HUE_PERIOD - delta)


def _normalized_channel_hues(channel_hues: Sequence[float]) -> tuple[float, ...]:
    """Validate 1..4 finite hues and fold them onto the 0..179 scale.

    Hues use the OpenCV period, so 190 becomes 10 and -10 becomes 170. Two
    normalized hues closer than ``MIN_CHANNEL_HUE_SEPARATION`` cannot be told
    apart on real pixels and raise ``ValueError`` instead of being merged.
    """
    if isinstance(channel_hues, (str, bytes)) or not isinstance(
        channel_hues, (Sequence, np.ndarray)
    ):
        raise ValueError("channel_hues must be a sequence of 1 to 4 finite numbers")
    try:
        values = tuple(channel_hues)
    except TypeError as error:
        raise ValueError("channel_hues must be a sequence of 1 to 4 finite numbers") from error
    if not 1 <= len(values) <= MAX_CHANNELS:
        raise ValueError(f"channel_hues must hold 1 to {MAX_CHANNELS} hues, got {len(values)}")
    hues: list[float] = []
    for value in values:
        if not isinstance(value, numbers.Real):
            raise ValueError(f"channel_hues must be numbers, got {type(value).__name__}")
        hue = float(value)
        if not math.isfinite(hue):
            raise ValueError(f"channel_hues must be finite, got {hue!r}")
        hues.append(hue % HUE_PERIOD)
    for first in range(len(hues)):
        for second in range(first + 1, len(hues)):
            if _circular_hue_distance(hues[first], hues[second]) < MIN_CHANNEL_HUE_SEPARATION:
                raise ValueError("channel_hues are too close to be distinguished")
    return tuple(hues)


def _region_bounds(size: int, low: float, high: float) -> tuple[int, int]:
    """Half-open pixel span ``[low, high)`` of one axis as ``(start, end)``.

    The start uses ``floor`` and the end ``ceil``, and the span always keeps at
    least one pixel inside ``0..size`` so the 8 pixel minimum cell side cannot
    produce an empty region.
    """
    start = int(math.floor(low * size))
    end = int(math.ceil(high * size))
    start = min(max(start, 0), size - 1)
    end = min(max(end, start + 1), size)
    return start, end


def _channel_pixel_mask(hsv: np.ndarray, hues: tuple[float, ...]) -> np.ndarray:
    """Boolean mask of saturated pixels owned by exactly one channel hue.

    Candidate pixels satisfy ``S >= MIN_SATURATION and V >= MIN_VALUE``. Each
    candidate is compared with every channel hue on the circular scale and is
    owned by the nearest one only when that distance is at most
    ``CHANNEL_HUE_TOLERANCE`` and no other hue is equally near (within
    ``DISTANCE_TIE_TOLERANCE``). Tied pixels stay unassigned so a mix of two
    channels is never silently attributed to one of them.
    """
    hue_plane = hsv[:, :, 0].astype(np.float64)
    candidate = (hsv[:, :, 1] >= MIN_SATURATION) & (hsv[:, :, 2] >= MIN_VALUE)
    mask = np.zeros(hue_plane.shape, dtype=bool)
    positions = np.flatnonzero(candidate.reshape(-1))
    if positions.size == 0:
        return mask
    candidate_hues = hue_plane.reshape(-1)[positions]
    deltas = np.abs(candidate_hues[:, None] - np.asarray(hues, dtype=np.float64)[None, :])
    wrapped = np.mod(deltas, HUE_PERIOD)
    distances = np.minimum(wrapped, HUE_PERIOD - wrapped)
    owned = distances.min(axis=1) <= CHANNEL_HUE_TOLERANCE
    if len(hues) > 1:
        two_smallest = np.partition(distances, 1, axis=1)[:, :2]
        owned &= (two_smallest[:, 1] - two_smallest[:, 0]) > DISTANCE_TIE_TOLERANCE
    mask.reshape(-1)[positions[owned]] = True
    return mask


def _stripe_ratio(value_plane: np.ndarray, bright_neutral: np.ndarray) -> float:
    """Share of adjacent bright neutral pixel pairs split by a value step.

    The value plane is first scaled to a fixed ``STRIPE_GRID`` square with
    ``INTER_AREA`` and the mask with ``INTER_NEAREST``, so the result depends
    on the pattern rather than on the cell pixel count. Horizontal, vertical
    and both diagonal neighbours are pooled: a pair is valid when both pixels
    are bright neutral and counts as one transition when their absolute value
    difference reaches ``STRIPE_MIN_VALUE_DELTA``. With no valid pair the
    ratio is ``0.0``.
    """
    small_value = cv2.resize(
        value_plane, (STRIPE_GRID, STRIPE_GRID), interpolation=cv2.INTER_AREA
    ).astype(np.int16)
    small_neutral = cv2.resize(
        bright_neutral.astype(np.uint8),
        (STRIPE_GRID, STRIPE_GRID),
        interpolation=cv2.INTER_NEAREST,
    ).astype(bool)
    neighbors = (
        (small_value[:-1, :], small_value[1:, :], small_neutral[:-1, :], small_neutral[1:, :]),
        (small_value[:, :-1], small_value[:, 1:], small_neutral[:, :-1], small_neutral[:, 1:]),
        (
            small_value[:-1, :-1],
            small_value[1:, 1:],
            small_neutral[:-1, :-1],
            small_neutral[1:, 1:],
        ),
        (
            small_value[:-1, 1:],
            small_value[1:, :-1],
            small_neutral[:-1, 1:],
            small_neutral[1:, :-1],
        ),
    )
    valid_pairs = 0
    transitions = 0
    for first_value, second_value, first_neutral, second_neutral in neighbors:
        valid = first_neutral & second_neutral
        step = np.abs(first_value - second_value)
        valid_pairs += int(np.count_nonzero(valid))
        transitions += int(np.count_nonzero(valid & (step >= STRIPE_MIN_VALUE_DELTA)))
    if valid_pairs == 0:
        return 0.0
    return min(1.0, max(0.0, transitions / valid_pairs))


def cell_evidence(cell_bgr: np.ndarray, channel_hues: Sequence[float]) -> CellEvidence:
    """Summarize one board cell crop without keeping any of its pixels.

    ``cell_bgr`` must be a non-empty uint8 three channel BGR array at least
    8x8 pixels, and ``channel_hues`` must hold 1 to 4 finite hues that are at
    least 2.0 apart on the circular 0..179 scale; anything else raises
    ``ValueError``. One HSV conversion feeds every field:

    ``bright_neutral_ratio``
        pixels with ``S <= 60 and V >= 150``, the flat light grey of blocked
        cells and of empty board background;
    ``channel_ratio``
        saturated pixels nearest to exactly one channel hue within 10.0;
    ``centered_channel_ratio``
        channel pixels inside the central ``[25%, 75%)`` box per axis;
    ``edge_channel_ratio``
        channel pixels inside the outer 18% ring per axis;
    ``stripe_ratio``
        adjacent pair transition share of the bright neutral mask;
    ``channel_distances``
        circular distance from the circular mean hue of the channel pixels to
        each input hue, all ``math.inf`` when the cell has none.
    """
    if not isinstance(cell_bgr, np.ndarray):
        raise ValueError("cell_evidence expects a numpy array")
    if cell_bgr.dtype != np.uint8:
        raise ValueError(f"cell_evidence expects uint8 pixels, got {cell_bgr.dtype}")
    if cell_bgr.ndim != 3 or cell_bgr.shape[2] != 3:
        raise ValueError(
            f"cell_evidence expects a three channel BGR image, got shape {cell_bgr.shape}"
        )
    if cell_bgr.size == 0:
        raise ValueError("cell_evidence expects a non-empty image")
    height, width = cell_bgr.shape[:2]
    if height < MIN_CELL_SIDE or width < MIN_CELL_SIDE:
        raise ValueError(
            f"cell_evidence expects at least {MIN_CELL_SIDE}x{MIN_CELL_SIDE} pixels, "
            f"got {width}x{height}"
        )
    hues = _normalized_channel_hues(channel_hues)

    hsv = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2HSV)
    value_plane = hsv[:, :, 2]
    bright_neutral = (hsv[:, :, 1] <= BRIGHT_NEUTRAL_MAX_SATURATION) & (
        value_plane >= BRIGHT_NEUTRAL_MIN_VALUE
    )
    channel_pixels = _channel_pixel_mask(hsv, hues)
    pixel_count = float(height * width)
    channel_count = int(np.count_nonzero(channel_pixels))

    center_rows, center_columns = (
        _region_bounds(height, CENTER_LOW, CENTER_HIGH),
        _region_bounds(width, CENTER_LOW, CENTER_HIGH),
    )
    center = channel_pixels[center_rows[0] : center_rows[1], center_columns[0] : center_columns[1]]
    inner_rows, inner_columns = (
        _region_bounds(height, EDGE_INNER_LOW, EDGE_INNER_HIGH),
        _region_bounds(width, EDGE_INNER_LOW, EDGE_INNER_HIGH),
    )
    inner = channel_pixels[inner_rows[0] : inner_rows[1], inner_columns[0] : inner_columns[1]]
    edge_count = channel_count - int(np.count_nonzero(inner))
    edge_area = int(channel_pixels.size) - int(inner.size)

    if channel_count:
        angles = np.radians(hsv[:, :, 0][channel_pixels].astype(np.float64) * 2.0)
        mean_angle = math.atan2(float(np.sin(angles).sum()), float(np.cos(angles).sum()))
        mean_hue = (math.degrees(mean_angle) / 2.0) % HUE_PERIOD
        channel_distances = tuple(_circular_hue_distance(mean_hue, hue) for hue in hues)
    else:
        channel_distances = tuple(math.inf for _ in hues)

    return CellEvidence(
        bright_neutral_ratio=float(np.count_nonzero(bright_neutral)) / pixel_count,
        channel_ratio=channel_count / pixel_count,
        centered_channel_ratio=float(np.count_nonzero(center)) / float(center.size),
        edge_channel_ratio=(edge_count / edge_area) if edge_area else 0.0,
        stripe_ratio=_stripe_ratio(value_plane, bright_neutral),
        channel_distances=channel_distances,
    )


RATIO_FIELDS = (
    "bright_neutral_ratio",
    "channel_ratio",
    "centered_channel_ratio",
    "edge_channel_ratio",
    "stripe_ratio",
)


def _validated_ratios(evidence: CellEvidence) -> dict[str, float]:
    """Return the five ratios as Python floats, rejecting anything outside 0..1."""
    ratios: dict[str, float] = {}
    for name in RATIO_FIELDS:
        value = getattr(evidence, name)
        if not isinstance(value, numbers.Real):
            raise ValueError(f"{name} must be a finite ratio in 0..1")
        number = float(value)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise ValueError(f"{name} must be a finite ratio in 0..1, got {number!r}")
        ratios[name] = number
    return ratios


def _validated_distances(channel_distances: Sequence[float]) -> tuple[float, ...]:
    """Return the channel distances as Python floats, rejecting NaN and negatives."""
    if isinstance(channel_distances, (str, bytes)) or not isinstance(
        channel_distances, (Sequence, np.ndarray)
    ):
        raise ValueError("channel_distances must be a sequence of non-negative numbers")
    try:
        values = tuple(channel_distances)
    except TypeError as error:
        raise ValueError(
            "channel_distances must be a sequence of non-negative numbers"
        ) from error
    distances: list[float] = []
    for value in values:
        if not isinstance(value, numbers.Real):
            raise ValueError(f"channel_distances must hold numbers, got {type(value).__name__}")
        number = float(value)
        if math.isnan(number) or number < 0.0:
            raise ValueError(
                f"channel_distances must be non-negative and not NaN, got {number!r}"
            )
        distances.append(number)
    return tuple(distances)


def _nearest_channel(distances: tuple[float, ...]) -> tuple[int | None, bool, float]:
    """Resolve the nearest channel as ``(channel, ambiguous, runner_up_gap)``.

    A channel is only returned when its distance is at most
    ``CHANNEL_HUE_TOLERANCE`` and the runner-up is more than
    ``CHANNEL_AMBIGUITY_MARGIN`` farther; a single distance uses the same
    threshold. Missing, too far and tied distances return ``None`` with
    ``ambiguous`` set, while ``runner_up_gap`` is ``math.inf`` when there is no
    runner-up.
    """
    if not distances:
        return None, True, math.inf
    order = sorted(range(len(distances)), key=lambda index: distances[index])
    best = distances[order[0]]
    if best > CHANNEL_HUE_TOLERANCE:
        return None, True, math.inf
    if len(order) == 1:
        return order[0], False, math.inf
    gap = distances[order[1]] - best
    if gap <= CHANNEL_AMBIGUITY_MARGIN:
        return None, True, gap
    return order[0], False, gap


def _touches_threshold(value: float, threshold: float) -> bool:
    """Whether a ratio sits within the confidence margin of one threshold."""
    return abs(value - threshold) <= CONFIDENCE_THRESHOLD_MARGIN


def classify_cell(evidence: CellEvidence) -> CellClass:
    """Classify one cell by fixed thresholds with an explicit confidence.

    Every ratio must be a finite ``0..1`` number and every channel distance
    non-negative without NaN, otherwise ``ValueError``. The priority is
    ``blocked`` (``bright_neutral_ratio >= 0.30 and stripe_ratio >= 0.06``),
    ``placed`` (``channel_ratio >= 0.42 and edge_channel_ratio >= 0.20``),
    ``fixed`` (``channel_ratio >= 0.08, centered_channel_ratio >= 0.20 and
    edge_channel_ratio <= 0.12``), then ``empty``.

    ``confidence`` uses no probability model: it starts at ``1.0`` and drops
    to ``0.0`` when any threshold that decided the kind is within 0.03 of its
    evidence, when ``placed``/``fixed`` cannot resolve a unique channel, or
    when that channel's runner-up is within 4.0. A ``fixed``/``placed`` cell
    still keeps its kind with ``channel=None`` and ``confidence=0.0`` so the
    caller can mark the statement incomplete rather than treat it as empty.
    """
    if not isinstance(evidence, CellEvidence):
        raise ValueError("classify_cell expects a CellEvidence instance")
    ratios = _validated_ratios(evidence)
    distances = _validated_distances(evidence.channel_distances)
    bright_neutral = ratios["bright_neutral_ratio"]
    channel_ratio = ratios["channel_ratio"]
    centered = ratios["centered_channel_ratio"]
    edge = ratios["edge_channel_ratio"]
    stripe = ratios["stripe_ratio"]

    if bright_neutral >= BLOCKED_BRIGHT_NEUTRAL_RATIO and stripe >= BLOCKED_STRIPE_RATIO:
        stable = not (
            _touches_threshold(bright_neutral, BLOCKED_BRIGHT_NEUTRAL_RATIO)
            or _touches_threshold(stripe, BLOCKED_STRIPE_RATIO)
        )
        return CellClass(kind="blocked", channel=None, confidence=1.0 if stable else 0.0)

    if channel_ratio >= PLACED_CHANNEL_RATIO and edge >= PLACED_EDGE_CHANNEL_RATIO:
        stable = not (
            _touches_threshold(channel_ratio, PLACED_CHANNEL_RATIO)
            or _touches_threshold(edge, PLACED_EDGE_CHANNEL_RATIO)
        )
        channel, _, gap = _nearest_channel(distances)
        if channel is None or not stable or gap <= CHANNEL_CONFIDENCE_MARGIN:
            return CellClass(kind="placed", channel=channel, confidence=0.0)
        return CellClass(kind="placed", channel=channel, confidence=1.0)

    if (
        channel_ratio >= FIXED_CHANNEL_RATIO
        and centered >= FIXED_CENTERED_CHANNEL_RATIO
        and edge <= FIXED_EDGE_CHANNEL_RATIO
    ):
        stable = not (
            _touches_threshold(channel_ratio, FIXED_CHANNEL_RATIO)
            or _touches_threshold(centered, FIXED_CENTERED_CHANNEL_RATIO)
            or _touches_threshold(edge, FIXED_EDGE_CHANNEL_RATIO)
        )
        channel, _, gap = _nearest_channel(distances)
        if channel is None or not stable or gap <= CHANNEL_CONFIDENCE_MARGIN:
            return CellClass(kind="fixed", channel=channel, confidence=0.0)
        return CellClass(kind="fixed", channel=channel, confidence=1.0)

    unstable = any(
        _touches_threshold(value, threshold)
        for value, threshold in (
            (bright_neutral, BLOCKED_BRIGHT_NEUTRAL_RATIO),
            (channel_ratio, PLACED_CHANNEL_RATIO),
            (channel_ratio, FIXED_CHANNEL_RATIO),
            (centered, FIXED_CENTERED_CHANNEL_RATIO),
            (edge, PLACED_EDGE_CHANNEL_RATIO),
            (edge, FIXED_EDGE_CHANNEL_RATIO),
            (stripe, BLOCKED_STRIPE_RATIO),
        )
    )
    return CellClass(kind="empty", channel=None, confidence=0.0 if unstable else 1.0)


# ---------------------------------------------------------------------------
# inventory piece raster reconstruction
#
# B1b hands over one already segmented, clean piece mask (no morphology, no
# outlier removal). These helpers only rasterize that mask back onto the square
# game grid. Every fraction is relative to the piece crop or to one candidate
# cell, never to a screenshot coordinate.
PIECE_MAX_GRID = 5
PIECE_MIN_IOU = 0.72
PIECE_AMBIGUITY_MARGIN = 0.04
PIECE_MAX_AXIS_DELTA_RATIO = 0.12
PIECE_OCCUPIED_RATIO = 0.50
PIECE_INNER_LOW = 0.20
PIECE_INNER_HIGH = 0.80


@dataclass(frozen=True)
class PieceShape:
    """One inventory piece rebuilt as an immutable grid shape.

    ``cells`` are the occupied zero based, normalized ``(row, column)``
    coordinates sorted ascending; ``rows`` and ``columns`` are the bounding box
    of that normalized shape and ``iou`` is the achieved intersection over
    union in ``0..1``. All values are plain Python ``int``/``float``; no field
    aliases a mask, a crop or any other array.
    """

    cells: tuple[tuple[int, int], ...]
    rows: int
    columns: int
    iou: float


def _piece_unit_number(name: str, value: object) -> float:
    """Validate one ``0..1`` parameter and return it as a Python float.

    Non-numbers, NaN and infinities raise ``ValueError``. ``bool`` is a Python
    ``Real`` and therefore passes as ``0``/``1`` here; only ``max_grid``, which
    must be a plain ``int``, rejects it explicitly.
    """
    if not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be a finite number in 0..1, got {value!r}")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be a finite number in 0..1, got {number!r}")
    return number


def _piece_grid_bounds(size: int, count: int) -> tuple[int, ...] | None:
    """Integer boundaries of ``count`` cells over ``size`` pixels.

    Boundary ``i`` is ``round(i * size / count)``. ``None`` means at least one
    cell would be empty, which makes the hypothesis unusable.
    """
    bounds = tuple(int(round(index * size / count)) for index in range(count + 1))
    if any(later <= earlier for earlier, later in zip(bounds, bounds[1:])):
        return None
    return bounds


def _piece_cells_connected(cells: Sequence[tuple[int, int]]) -> bool:
    """Whether the occupied grid cells form exactly one 4-connected group."""
    remaining = set(cells)
    start = cells[0]
    remaining.discard(start)
    stack = [start]
    while stack:
        row, column = stack.pop()
        for neighbor in (
            (row - 1, column),
            (row + 1, column),
            (row, column - 1),
            (row, column + 1),
        ):
            if neighbor in remaining:
                remaining.discard(neighbor)
                stack.append(neighbor)
    return not remaining


def _piece_occupied_cells(
    foreground: np.ndarray,
    row_bounds: tuple[int, ...],
    column_bounds: tuple[int, ...],
) -> tuple[tuple[int, int], ...] | None:
    """Occupied cells of one grid, or ``None`` when the grid is unusable.

    Each cell is sampled on its inner ``[20%, 80%)`` box per axis (``floor``
    start, ``ceil`` end, at least one pixel) and is occupied when at least half
    of that box is foreground. A grid needs at least one occupied cell and its
    occupied cells must be 4-connected; nothing is dilated, closed or dropped
    here.
    """
    occupied: list[tuple[int, int]] = []
    for row in range(len(row_bounds) - 1):
        row_start = row_bounds[row]
        inner_row = _region_bounds(
            row_bounds[row + 1] - row_start, PIECE_INNER_LOW, PIECE_INNER_HIGH
        )
        for column in range(len(column_bounds) - 1):
            column_start = column_bounds[column]
            inner_column = _region_bounds(
                column_bounds[column + 1] - column_start, PIECE_INNER_LOW, PIECE_INNER_HIGH
            )
            window = foreground[
                row_start + inner_row[0] : row_start + inner_row[1],
                column_start + inner_column[0] : column_start + inner_column[1],
            ]
            if np.count_nonzero(window) / window.size >= PIECE_OCCUPIED_RATIO:
                occupied.append((row, column))
    if not occupied or not _piece_cells_connected(occupied):
        return None
    return tuple(occupied)


def _piece_candidate(
    foreground: np.ndarray, rows: int, columns: int
) -> PieceShape | None:
    """One square ``rows`` x ``columns`` hypothesis over a cropped piece mask.

    ``foreground`` is the boolean crop returned by the caller. The candidate is
    rejected when the two pitches differ by more than
    ``PIECE_MAX_AXIS_DELTA_RATIO``, when a cell boundary would collapse, when
    no cell is occupied or when the occupied cells are not 4-connected. The
    occupied coordinates are normalized so their minimum row and column are
    ``0``; ``rows``/``columns`` describe that normalized bounding box, while
    the ideal mask and the IoU use the full, unshifted cell boundaries.
    """
    height, width = foreground.shape
    row_pitch = height / rows
    column_pitch = width / columns
    if (
        abs(row_pitch - column_pitch) / max(row_pitch, column_pitch)
        > PIECE_MAX_AXIS_DELTA_RATIO
    ):
        return None
    row_bounds = _piece_grid_bounds(height, rows)
    column_bounds = _piece_grid_bounds(width, columns)
    if row_bounds is None or column_bounds is None:
        return None
    occupied = _piece_occupied_cells(foreground, row_bounds, column_bounds)
    if occupied is None:
        return None

    minimum_row = min(row for row, _ in occupied)
    minimum_column = min(column for _, column in occupied)
    cells = tuple(
        sorted((row - minimum_row, column - minimum_column) for row, column in occupied)
    )
    ideal = np.zeros(foreground.shape, dtype=bool)
    for row, column in occupied:
        ideal[
            row_bounds[row] : row_bounds[row + 1],
            column_bounds[column] : column_bounds[column + 1],
        ] = True
    intersection = int(np.count_nonzero(foreground & ideal))
    union = int(np.count_nonzero(foreground | ideal))
    return PieceShape(
        cells=cells,
        rows=cells[-1][0] + 1,
        columns=max(column for _, column in cells) + 1,
        iou=intersection / union,
    )


def _piece_candidates(foreground: np.ndarray, max_grid: int) -> tuple[PieceShape, ...]:
    """Every usable 1..``max_grid`` square hypothesis of one cropped mask.

    Hypotheses that normalize to the same ``(cells, rows, columns)`` are merged
    and only the one with the highest IoU survives.
    """
    best: dict[tuple[tuple[tuple[int, int], ...], int, int], PieceShape] = {}
    for rows in range(1, max_grid + 1):
        for columns in range(1, max_grid + 1):
            candidate = _piece_candidate(foreground, rows, columns)
            if candidate is None:
                continue
            key = (candidate.cells, candidate.rows, candidate.columns)
            previous = best.get(key)
            if previous is None or candidate.iou > previous.iou:
                best[key] = candidate
    return tuple(best.values())


def reconstruct_piece(
    mask: np.ndarray,
    *,
    max_grid: int = PIECE_MAX_GRID,
    minimum_iou: float = PIECE_MIN_IOU,
    ambiguity_margin: float = PIECE_AMBIGUITY_MARGIN,
) -> PieceShape | None:
    """Rebuild one segmented inventory piece mask as a square grid shape.

    ``mask`` must be a non-empty two dimensional ``bool`` or ``uint8`` array,
    anything else raises ``ValueError``; ``uint8`` counts every non-zero pixel
    as foreground and the array is never modified. ``max_grid`` must be a plain
    ``int`` in ``1..5`` and both ratios must be finite numbers in ``0..1``,
    otherwise ``ValueError``.

    The mask is cropped to its foreground bounding box and must then hold
    exactly one 4-connected component: isolated noise, diagonally touching
    blocks or several separate blobs return ``None``. No closing, dilation or
    small blob removal happens here; B1b has to hand over a clean piece mask.

    For every ``rows``/``columns`` in ``1..max_grid`` the two pitches must match
    within 12%, because game cells are square and a rectangular piece must not
    be read as a single cell. Cell boundaries use ``round(i * size / count)``
    and every cell has to stay non-empty. A cell counts as occupied when at
    least half of its inner ``[20%, 80%)`` box is foreground, and the occupied
    cells have to form one 4-connected group. Occupied coordinates are
    normalized to a zero based bounding box, the ideal mask is built from the
    full cell boundaries, and only hypotheses with an IoU of at least
    ``minimum_iou`` survive; equal shapes keep their best IoU.

    Among the survivors only candidates within ``ambiguity_margin`` of the best
    IoU are considered, and the one with the fewest occupied cells wins so that
    an integer multiple subdivision (a 4x4 rendering of a 2x2 L) loses against
    the coarse shape. A remaining tie between different shapes returns ``None``
    as ambiguous; enumeration order and floating point noise never decide.
    """

    if not isinstance(mask, np.ndarray):
        raise ValueError("reconstruct_piece expects a numpy array")
    if mask.dtype != np.bool_ and mask.dtype != np.uint8:
        raise ValueError(
            f"reconstruct_piece expects a bool or uint8 mask, got {mask.dtype}"
        )
    if mask.ndim != 2:
        raise ValueError(
            f"reconstruct_piece expects a two dimensional mask, got shape {mask.shape}"
        )
    if mask.size == 0:
        raise ValueError("reconstruct_piece expects a non-empty mask")
    if isinstance(max_grid, bool) or not isinstance(max_grid, int):
        raise ValueError(
            f"max_grid must be an integer in 1..{PIECE_MAX_GRID}, got {max_grid!r}"
        )
    if not 1 <= max_grid <= PIECE_MAX_GRID:
        raise ValueError(
            f"max_grid must be an integer in 1..{PIECE_MAX_GRID}, got {max_grid!r}"
        )
    minimum_iou = _piece_unit_number("minimum_iou", minimum_iou)
    ambiguity_margin = _piece_unit_number("ambiguity_margin", ambiguity_margin)

    foreground = np.array(mask, dtype=bool, copy=True)
    if not foreground.any():
        return None
    occupied_rows = np.flatnonzero(foreground.any(axis=1))
    occupied_columns = np.flatnonzero(foreground.any(axis=0))
    crop = foreground[
        occupied_rows[0] : occupied_rows[-1] + 1,
        occupied_columns[0] : occupied_columns[-1] + 1,
    ]
    component_count, _ = cv2.connectedComponents(crop.astype(np.uint8), connectivity=4)
    if component_count - 1 != 1:
        return None

    candidates = [
        candidate
        for candidate in _piece_candidates(crop, max_grid)
        if candidate.iou >= minimum_iou
    ]
    if not candidates:
        return None
    best_iou = max(candidate.iou for candidate in candidates)
    near_best = [
        candidate
        for candidate in candidates
        if best_iou - candidate.iou <= ambiguity_margin
    ]
    fewest_cells = min(len(candidate.cells) for candidate in near_best)
    finalists = [
        candidate for candidate in near_best if len(candidate.cells) == fewest_cells
    ]
    shapes = {(candidate.cells, candidate.rows, candidate.columns) for candidate in finalists}
    if len(shapes) != 1:
        return None
    chosen = finalists[0]
    return PieceShape(
        cells=chosen.cells,
        rows=chosen.rows,
        columns=chosen.columns,
        iou=float(chosen.iou),
    )


# ---------------------------------------------------------------------------
# short bar stacks and board side candidate ensembles (B1b1)
#
# A line whose target is ``n`` is drawn as ``n`` small bars stacked away from
# the board, so the bar closest to the board sits on the common outer edge of
# the board side: the bottom edge for the stacks above the board and the right
# edge for the stacks left of it. On real screenshots the bar long side is
# about 0.31 of the board step, its short side about 0.10 and the centre
# distance between two bars of one stack about 0.15. Every threshold below is a
# share of that step, so 0.5x/1x/2x renderings and crops behave identically.
# Only ``BAR_MIN_SIDE`` is an absolute pixel floor and it merely rejects sub
# pixel noise. Nothing here knows about the board, the line count or a
# filename: B1b2 fits the board from these candidates.

BAR_LONG_RATIO = 0.31
BAR_SHORT_RATIO = 0.10
BAR_STEP_RATIO = 0.15
# Dimming, anti aliasing and clipping shrink the saturated core of a bar, so a
# measured aspect ratio of a real bar ranges from about 2.4 to about 5.
BAR_ASPECT_MIN = 2.2
BAR_ASPECT_MAX = 5.0
BAR_MIN_SIDE = 3
BAR_MAX_COUNT = 10
# Relative spread accepted when one screenshot's bars are collected into a
# single scale, and when a bar is compared with the stack it may join.
BAR_SCALE_TOLERANCE = 0.30
BAR_SIZE_TOLERANCE = 0.30
# Within one stack, in units of the estimated step.
BAR_ANCHOR_TOLERANCE = 0.12
BAR_SPACING_TOLERANCE = 0.35
# A stack is one colour; the screenshot wide hue gradient stays well below this.
BAR_HUE_TOLERANCE = 8.0
# Ensemble gates, in units of the ensemble step.
BAR_BASELINE_TOLERANCE = 0.20
BAR_BASELINE_SPAN_TOLERANCE = 0.40
BAR_ENSEMBLE_STEP_TOLERANCE = 0.25

_ORIENTATION_ORDER = {"horizontal": 0, "vertical": 1}


@dataclass(frozen=True)
class BarStack:
    """One physical stack of equally coloured bars of a single line.

    ``orientation`` is ``horizontal`` for the stacks above the board and
    ``vertical`` for the stacks left of it. ``anchor`` is the perpendicular
    centre (``x`` for horizontal, ``y`` for vertical) and ``baseline`` the
    outer edge of the bar closest to the board (bottom edge for horizontal,
    right edge for vertical). ``hue`` is the circular mean of the member hues
    on the OpenCV 0..179 scale, ``count`` the number of bars (1..10) and
    ``step`` the board pitch estimated from the bar size and from the centre
    distances inside the stack. ``residual_ratio`` is the mean absolute
    deviation of those centre distances from ``BAR_STEP_RATIO * step`` in units
    of ``step``; a single bar has no spacing evidence and reports ``0.0``.

    All fields are plain Python scalars and no field aliases a pixel, a mask or
    a contour. Two stacks of the same logical line but of different colour keep
    their own fixed anchor offset and stay separate here.
    """

    orientation: Literal["horizontal", "vertical"]
    anchor: float
    baseline: float
    hue: float
    count: int
    step: float
    residual_ratio: float


@dataclass(frozen=True)
class BarEnsemble:
    """The stacks of one board side that share a baseline and a step.

    ``baseline`` and ``step`` are the median of the member values, ``stacks``
    holds the members ordered by ascending ``anchor``, and ``residual_ratio``
    is the mean normalized deviation of the member baselines and steps from
    those medians. An ensemble always covers at least two different anchors, so
    a lone title stroke, one inventory piece or the bottom colour strip can
    never become a valid ensemble on its own.
    """

    orientation: Literal["horizontal", "vertical"]
    baseline: float
    step: float
    stacks: tuple[BarStack, ...]
    residual_ratio: float


@dataclass(frozen=True)
class _Bar:
    """One saturated component that may be a short bar; never returned."""

    orientation: Literal["horizontal", "vertical"]
    anchor: float
    position: float
    baseline: float
    size_step: float
    hue: float


def _circular_mean_hue(hues: Sequence[float]) -> float:
    """Circular mean of OpenCV hues on the 0..179 scale.

    A fully cancelled resultant falls back to ``0.0``, exactly like the
    per component hue of ``saturated_components``.
    """
    angles = [math.radians(hue * 2.0) for hue in hues]
    sin_sum = math.fsum(math.sin(angle) for angle in angles)
    cos_sum = math.fsum(math.cos(angle) for angle in angles)
    return math.degrees(math.atan2(sin_sum, cos_sum)) / 2.0 % HUE_PERIOD


def _bar_candidates(components: Sequence[Component]) -> list[_Bar]:
    """The saturated components that could be one short bar of any step.

    A component is elongated when its long side is ``BAR_ASPECT_MIN`` to
    ``BAR_ASPECT_MAX`` times its short side, and its short side must reach
    ``BAR_MIN_SIDE`` pixels. ``size_step`` is the geometric mean of the step
    implied by the long side (``long / BAR_LONG_RATIO``) and by the short side
    (``short / BAR_SHORT_RATIO``); the geometric mean keeps the estimate
    symmetric when anti aliasing shaves pixels off one side only.
    """
    bars: list[_Bar] = []
    for component in components:
        horizontal = component.width >= component.height
        long_side = component.width if horizontal else component.height
        short_side = component.height if horizontal else component.width
        if short_side < BAR_MIN_SIDE:
            continue
        aspect = long_side / short_side
        if aspect < BAR_ASPECT_MIN or aspect > BAR_ASPECT_MAX:
            continue
        bars.append(
            _Bar(
                orientation="horizontal" if horizontal else "vertical",
                anchor=float(component.center_x if horizontal else component.center_y),
                position=float(component.center_y if horizontal else component.center_x),
                baseline=float(
                    component.y + component.height
                    if horizontal
                    else component.x + component.width
                ),
                size_step=float(
                    math.sqrt(
                        (long_side / BAR_LONG_RATIO) * (short_side / BAR_SHORT_RATIO)
                    )
                ),
                hue=float(component.hue),
            )
        )
    return bars


def _dominant_size_scale(values: Sequence[float]) -> float | None:
    """The median of the widest cluster of mutually compatible ``values``.

    Two values are compatible when their relative difference is at most
    ``BAR_SCALE_TOLERANCE``, so the window grows until the next sorted value
    leaves the band opened by its smallest member. A tie keeps the window
    holding the smallest values, which makes the result deterministic. The
    returned median is the provisional scale of the screenshot; the spacing
    inside the stacks corrects its bias afterwards.
    """
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    best_start = 0
    best_end = 0
    for start in range(len(ordered)):
        end = start
        while (
            end + 1 < len(ordered)
            and ordered[end + 1] <= ordered[start] * (1.0 + BAR_SCALE_TOLERANCE)
        ):
            end += 1
        if end - start > best_end - best_start:
            best_start, best_end = start, end
    return float(statistics.median(ordered[best_start : best_end + 1]))


def _bar_members(
    bars: Sequence[_Bar], seed: int, scale: float, selected: Sequence[int]
) -> list[int]:
    """Grow one stack from ``seed`` along both stacking directions.

    ``scale`` is the provisional step of the screenshot and ``selected`` lists
    the still unassigned candidate indices. A member has to share the seed's
    orientation, keep the seed's anchor within ``BAR_ANCHOR_TOLERANCE * scale``,
    its hue within ``BAR_HUE_TOLERANCE`` and its own size estimate within
    ``BAR_SIZE_TOLERANCE`` of the seed's. Along the stacking direction each next
    bar must sit one slot away, where a slot is ``BAR_STEP_RATIO`` of the scale
    with ``BAR_SPACING_TOLERANCE`` slack; a larger gap therefore ends the stack
    instead of bridging it. The nearest slot wins, and a smaller position
    breaks a remaining tie, so the walk never depends on input order.
    """
    expected = BAR_STEP_RATIO * scale
    minimum = expected * (1.0 - BAR_SPACING_TOLERANCE)
    maximum = expected * (1.0 + BAR_SPACING_TOLERANCE)
    remaining = sorted(selected)
    remaining.remove(seed)
    members = [seed]
    for direction in (-1.0, 1.0):
        cursor = bars[seed]
        while True:
            chosen: tuple[tuple[float, float, float], int] | None = None
            for index in remaining:
                candidate = bars[index]
                if candidate.orientation != bars[seed].orientation:
                    continue
                if abs(candidate.anchor - bars[seed].anchor) > BAR_ANCHOR_TOLERANCE * scale:
                    continue
                if _circular_hue_distance(candidate.hue, bars[seed].hue) > BAR_HUE_TOLERANCE:
                    continue
                if (
                    abs(candidate.size_step - bars[seed].size_step)
                    > BAR_SIZE_TOLERANCE * bars[seed].size_step
                ):
                    continue
                spacing = (candidate.position - cursor.position) * direction
                if spacing < minimum or spacing > maximum:
                    continue
                key = (abs(spacing - expected), spacing, candidate.position)
                if chosen is None or key < chosen[0]:
                    chosen = (key, index)
            if chosen is None:
                break
            remaining.remove(chosen[1])
            members.append(chosen[1])
            cursor = bars[chosen[1]]
    return members


def _bar_stack(bars: Sequence[_Bar], members: Sequence[int], calibration: float) -> BarStack:
    """Summarize one stack as an immutable :class:`BarStack`.

    ``calibration`` corrects the size estimate of a single bar stack: the
    per screenshot ratio between the spacing estimate (unbiased) and the size
    estimate (shrunk by dimming) measured over every stack that has spacing
    evidence. A stack with two or more bars uses its own spacing directly.
    """
    ordered = sorted(members, key=lambda index: (bars[index].position, bars[index].anchor))
    positions = [bars[index].position for index in ordered]
    spacings = [later - earlier for earlier, later in zip(positions, positions[1:])]
    size_step = float(statistics.median([bars[index].size_step for index in ordered]))
    if spacings:
        step = float(statistics.median(spacings) / BAR_STEP_RATIO)
        residual = sum(abs(spacing - BAR_STEP_RATIO * step) for spacing in spacings) / (
            len(spacings) * step
        )
    else:
        step = float(size_step * calibration)
        residual = 0.0
    return BarStack(
        orientation=bars[ordered[0]].orientation,
        anchor=float(statistics.fmean([bars[index].anchor for index in ordered])),
        baseline=float(max(bars[index].baseline for index in ordered)),
        hue=float(_circular_mean_hue([bars[index].hue for index in ordered])),
        count=int(len(ordered)),
        step=step,
        residual_ratio=float(residual),
    )


def extract_bar_stacks(image: np.ndarray) -> tuple[BarStack, ...]:
    """Extract the physical short bar stacks of one full BGR screenshot.

    ``image`` is validated by :func:`saturated_components`, so anything that
    function rejects (a non array, a non uint8, a non three channel or an empty
    image) raises ``ValueError`` here as well.

    The saturated components are reduced to elongated bar candidates, the
    dominant candidate size picks the screenshot scale, candidates outside
    ``BAR_SCALE_TOLERANCE`` of it are dropped, and the survivors are chained
    into stacks of 1 to ``BAR_MAX_COUNT`` bars that share orientation, anchor,
    hue, size and one slot spacing. The current UI title strokes, inventory
    pieces and the bottom colour strip are allowed to survive as lone
    candidates; ``group_bar_ensembles`` is what rejects them.

    Stacks are returned ordered by ``(orientation, baseline, anchor)`` so the
    top stacks read left to right and the left stacks top to bottom. Every
    field is a Python scalar and no returned object keeps a pixel, a mask, a
    contour or a component.
    """
    bars = _bar_candidates(saturated_components(image))
    if not bars:
        return ()
    scale = _dominant_size_scale([bar.size_step for bar in bars])
    if scale is None or scale <= 0.0:
        return ()
    selected = [
        index
        for index, bar in enumerate(bars)
        if abs(bar.size_step - scale) <= BAR_SCALE_TOLERANCE * scale
    ]
    groups: list[list[int]] = []
    assigned: set[int] = set()
    for seed in selected:
        if seed in assigned:
            continue
        members = _bar_members(
            bars, seed, scale, [index for index in selected if index not in assigned]
        )
        assigned.update(members)
        groups.append(members)

    ratios: list[float] = []
    for members in groups:
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda index: bars[index].position)
        positions = [bars[index].position for index in ordered]
        spacings = [later - earlier for earlier, later in zip(positions, positions[1:])]
        size_step = float(statistics.median([bars[index].size_step for index in ordered]))
        if size_step > 0.0:
            ratios.append(float(statistics.median(spacings) / BAR_STEP_RATIO / size_step))
    calibration = float(statistics.median(ratios)) if ratios else 1.0

    stacks: list[BarStack] = []
    for members in groups:
        ordered = sorted(members, key=lambda index: (bars[index].position, bars[index].anchor))
        for start in range(0, len(ordered), BAR_MAX_COUNT):
            stacks.append(_bar_stack(bars, ordered[start : start + BAR_MAX_COUNT], calibration))
    stacks.sort(
        key=lambda stack: (
            _ORIENTATION_ORDER[stack.orientation],
            stack.baseline,
            stack.anchor,
            stack.hue,
            stack.count,
        )
    )
    return tuple(stacks)


def _validated_stacks(
    stacks: Sequence[BarStack], function: str = "group_bar_ensembles"
) -> tuple[BarStack, ...]:
    """Validate a stack sequence and return it as a tuple of ``BarStack``.

    Anything but a sequence of well formed :class:`BarStack` values raises
    ``ValueError``: a wrong type, an unknown orientation, a count outside
    ``1..BAR_MAX_COUNT``, a non positive or non finite ``step``, a negative or
    non finite ``residual_ratio`` and a non finite anchor, baseline or hue are
    all rejected instead of silently producing an unusable ensemble.
    """
    if isinstance(stacks, (str, bytes)) or not isinstance(stacks, (Sequence, np.ndarray)):
        raise ValueError(f"{function} expects a sequence of BarStack instances")
    result: list[BarStack] = []
    for stack in stacks:
        if not isinstance(stack, BarStack):
            raise ValueError(
                f"{function} expects BarStack instances, got {type(stack).__name__}"
            )
        if stack.orientation not in _ORIENTATION_ORDER:
            raise ValueError(f"unknown bar stack orientation {stack.orientation!r}")
        if not 1 <= stack.count <= BAR_MAX_COUNT:
            raise ValueError(
                f"bar stack count must be 1 to {BAR_MAX_COUNT}, got {stack.count!r}"
            )
        for name in ("anchor", "baseline", "hue"):
            value = getattr(stack, name)
            if not isinstance(value, numbers.Real) or not math.isfinite(float(value)):
                raise ValueError(f"bar stack {name} must be a finite number, got {value!r}")
        if not isinstance(stack.step, numbers.Real) or not math.isfinite(float(stack.step)):
            raise ValueError(f"bar stack step must be a finite number, got {stack.step!r}")
        if float(stack.step) <= 0.0:
            raise ValueError(f"bar stack step must be positive, got {stack.step!r}")
        if not isinstance(stack.residual_ratio, numbers.Real) or not math.isfinite(
            float(stack.residual_ratio)
        ):
            raise ValueError(
                f"bar stack residual_ratio must be a finite number, got {stack.residual_ratio!r}"
            )
        if float(stack.residual_ratio) < 0.0:
            raise ValueError(
                f"bar stack residual_ratio must not be negative, got {stack.residual_ratio!r}"
            )
        result.append(stack)
    return tuple(result)


def _distinct_anchor_count(anchors: Sequence[float], tolerance: float) -> int:
    """Number of anchor clusters when neighbours within ``tolerance`` merge.

    Each cluster is compared with its first, ascending member, so a slow drift
    cannot chain two far apart anchors into one cluster.
    """
    count = 0
    reference: float | None = None
    for anchor in sorted(anchors):
        if reference is None or anchor - reference > tolerance:
            count += 1
            reference = anchor
    return count


def group_bar_ensembles(stacks: Sequence[BarStack]) -> tuple[BarEnsemble, ...]:
    """Group stacks into candidate board sides without touching any pixel.

    ``stacks`` must be a sequence of :class:`BarStack`; anything else raises
    ``ValueError``. The stacks are first ordered by
    ``(orientation, baseline, anchor, hue, count)``, so the result never
    depends on the caller's order. Each remaining stack then starts a group
    that walks the ascending baselines: a later stack joins while it stays
    within ``BAR_BASELINE_TOLERANCE`` of the last accepted baseline, within
    ``BAR_BASELINE_SPAN_TOLERANCE`` of the seed baseline and within
    ``BAR_ENSEMBLE_STEP_TOLERANCE`` of the seed step. Chaining one bar slot at a
    time keeps a stack whose innermost bar was clipped or merged with the board
    border in the same ensemble, while an unrelated cluster of UI components
    hundreds of pixels away still stays out. A group is only returned when it
    covers at least two distinct anchors, which is what keeps a single title
    stroke, one inventory piece or the bottom colour strip from becoming a
    valid ensemble on its own. Multi colour constraints keep their physical
    stacks here: two colours of one line differ by a fixed anchor offset and
    are not merged.

    ``baseline`` and ``step`` of the result are the member medians, the members
    are ordered by anchor and ``residual_ratio`` is the mean deviation of the
    member baselines and steps from those medians, in units of the ensemble
    step. Ensembles are returned by ``(orientation, baseline, anchor)``.
    """
    ordered = sorted(
        _validated_stacks(stacks),
        key=lambda stack: (
            _ORIENTATION_ORDER[stack.orientation],
            stack.baseline,
            stack.anchor,
            stack.hue,
            stack.count,
        ),
    )
    assigned = [False] * len(ordered)
    ensembles: list[BarEnsemble] = []
    for seed in range(len(ordered)):
        if assigned[seed]:
            continue
        reference = ordered[seed]
        members = [seed]
        last_baseline = reference.baseline
        for index in range(seed + 1, len(ordered)):
            if assigned[index]:
                continue
            candidate = ordered[index]
            if candidate.orientation != reference.orientation:
                continue
            if candidate.baseline - last_baseline > BAR_BASELINE_TOLERANCE * reference.step:
                continue
            if (
                candidate.baseline - reference.baseline
                > BAR_BASELINE_SPAN_TOLERANCE * reference.step
            ):
                continue
            scale = max(candidate.step, reference.step)
            if abs(candidate.step - reference.step) / scale > BAR_ENSEMBLE_STEP_TOLERANCE:
                continue
            members.append(index)
            last_baseline = candidate.baseline

        anchors = [ordered[index].anchor for index in members]
        if _distinct_anchor_count(anchors, BAR_ANCHOR_TOLERANCE * reference.step) < 2:
            continue

        chosen = sorted(
            (ordered[index] for index in members), key=lambda stack: stack.anchor
        )
        step = float(statistics.median([stack.step for stack in chosen]))
        baseline = float(statistics.median([stack.baseline for stack in chosen]))
        residual = sum(
            abs(stack.baseline - baseline) + abs(stack.step - step) for stack in chosen
        ) / (2.0 * len(chosen) * step)
        ensembles.append(
            BarEnsemble(
                orientation=chosen[0].orientation,
                baseline=baseline,
                step=step,
                stacks=tuple(chosen),
                residual_ratio=float(residual),
            )
        )
        for index in members:
            assigned[index] = True
    return tuple(ensembles)


# ---------------------------------------------------------------------------
# board geometry and bar line targets (B1b2)
#
# The stacks above the board and the stacks left of it fix the two baselines
# and, together, one square pitch: the cell grid starts a fraction of a pitch
# below/right of the bar baseline and the first observed stack sits on the
# first line whose target is non zero. The rectangle is then grown outwards
# from that corner one line at a time: a line still belongs to the board while
# every one of its cells carries board texture (corner strokes, grid lines,
# blocked hatching) or saturated game content (fixed cells, placed pieces), so
# a line whose target is zero is still part of the board while the decorative
# frame, the page background and the UI panels around it are not. Every spatial
# threshold below is a share of the fitted pitch; only the saturation and value
# gates are absolute colour thresholds, exactly like the B1a helpers.
BOARD_STEP_TOLERANCE = 0.12
BOARD_MAX_LINES = 10
BOARD_MIN_LINES = 2
BOARD_SCALE_LOW = 0.86
BOARD_SCALE_HIGH = 1.14
BOARD_SCALE_RESOLUTION = 0.002
BOARD_REFINE_RESOLUTION = 0.0005
BOARD_FIT_TOLERANCE = 0.30
BOARD_GAP_MAX = 0.65
BOARD_HALF_RANGES = (0.06, 0.46, 0.54, 0.94)
BOARD_TEXTURE_LOW = 0.20
BOARD_TEXTURE_HIGH = 0.80
BOARD_TEXTURE_MIN = 0.40
BOARD_TEXTURE_EXTEND_MIN = 0.35
BOARD_CONTENT_SATURATION = 120
BOARD_CONTENT_VALUE = 25
BOARD_CONTENT_RATIO = 0.50
BOARD_CONTENT_BOX = (0.28, 0.72)
BOARD_MIN_SCORE = 0.50
BOARD_MIN_SCORE_MARGIN = 0.15
BOARD_MIN_SUPPORT_LINES = 2
BAR_CENTER_TOLERANCE = 0.30
BAR_OFFSET_TOLERANCE = 0.25
BAR_ENSEMBLE_GAP_MAX = 0.65


@dataclass(frozen=True)
class BoardGeometry:
    """The unique board rectangle fitted to one screenshot.

    ``left``/``top``/``right``/``bottom`` are the outer boundary of the cell
    grid (the decorative frame around it is not part of the rectangle),
    ``step`` is the square pitch fitted to the two bar axes and ``rows``/
    ``columns`` are the cell counts in ``2..BOARD_MAX_LINES``.
    ``row_centers``/``column_centers`` hold one centre per line, in ascending
    order, so their length equals ``rows``/``columns``.

    ``evidence_ratio`` is the share of the rectangle's cells that carry board
    evidence: either in-cell texture (the minimum structure energy over the
    four half cells reaches ``BOARD_TEXTURE_MIN``) or saturated game content
    (the central box is at least ``BOARD_CONTENT_RATIO`` saturated pixels).
    A dimmed completed board whose covered cells are flat still counts through
    the content test, and a zero target line whose cells only show the faint
    cell texture still counts through the texture test.

    ``score_margin`` is the difference between this rectangle's score
    (``evidence_ratio`` minus the share of supported cells in the ring just
    outside the rectangle) and the score of the closest distinct alternative
    geometry; when no other geometry was found it is the score itself, i.e.
    its distance from the 0 baseline. A small margin means the screenshot does
    not single out one rectangle and ``locate_bar_board`` returns ``None``.

    Every field is a plain Python scalar or tuple and no field aliases a pixel,
    a mask, a contour or a crop.
    """

    left: float
    top: float
    right: float
    bottom: float
    step: float
    rows: int
    columns: int
    row_centers: tuple[float, ...]
    column_centers: tuple[float, ...]
    evidence_ratio: float
    score_margin: float


@dataclass(frozen=True)
class BarTargets:
    """Per channel row and column targets of one confirmed board.

    ``channel_hues`` are the stable circular hue centres on the OpenCV 0..179
    scale in ascending order, so ``row_targets[channel][row]`` and
    ``column_targets[channel][column]`` are the bar counts of that colour on
    that line; a line without any physical stack of the channel is ``0``.
    ``residual_ratio`` is the mean distance between a stack's display offset
    and its channel's robust offset on the same axis, in units of the board
    step: single colour lines keep no offset, multi colour lines keep about
    +/-0.2 step, and an unstable offset rejects the whole decoding.

    Targets hold plain Python ``int`` and every tuple follows the input channel
    order; no field aliases a pixel, a stack or an ensemble.
    """

    channel_hues: tuple[float, ...]
    row_targets: tuple[tuple[int, ...], ...]
    column_targets: tuple[tuple[int, ...], ...]
    residual_ratio: float


@dataclass(frozen=True)
class _AxisFit:
    """One axis: the fitted pitch and the centre of its first line."""

    pitch: float
    first_center: float


@dataclass(frozen=True)
class _BoardCandidate:
    """One board rectangle fitted from one ensemble pair; never returned."""

    first_center_x: float
    first_center_y: float
    pitch: float
    rows: int
    columns: int
    evidence_ratio: float
    ring_ratio: float
    score: float


def _validated_ensembles(
    ensembles: Sequence[BarEnsemble], function: str
) -> tuple[BarEnsemble, ...]:
    """Validate an ensemble sequence and return it as a tuple.

    Anything but a sequence of well formed :class:`BarEnsemble` values raises
    ``ValueError``: a wrong type, an unknown orientation, a non positive or non
    finite baseline/step, a negative or non finite ``residual_ratio``, an empty
    stack tuple and every invalid nested :class:`BarStack` are rejected instead
    of silently producing an unusable board. ``function`` only names the public
    caller in the error message.
    """
    if isinstance(ensembles, (str, bytes)) or not isinstance(
        ensembles, (Sequence, np.ndarray)
    ):
        raise ValueError(f"{function} expects a sequence of BarEnsemble instances")
    result: list[BarEnsemble] = []
    for ensemble in ensembles:
        if not isinstance(ensemble, BarEnsemble):
            raise ValueError(
                f"{function} expects BarEnsemble instances, "
                f"got {type(ensemble).__name__}"
            )
        if ensemble.orientation not in _ORIENTATION_ORDER:
            raise ValueError(f"unknown bar ensemble orientation {ensemble.orientation!r}")
        for name in ("baseline", "step"):
            value = getattr(ensemble, name)
            if not isinstance(value, numbers.Real) or not math.isfinite(float(value)):
                raise ValueError(
                    f"bar ensemble {name} must be a finite number, got {value!r}"
                )
        if float(ensemble.step) <= 0.0:
            raise ValueError(f"bar ensemble step must be positive, got {ensemble.step!r}")
        if not isinstance(ensemble.residual_ratio, numbers.Real) or not math.isfinite(
            float(ensemble.residual_ratio)
        ):
            raise ValueError(
                "bar ensemble residual_ratio must be a finite number, "
                f"got {ensemble.residual_ratio!r}"
            )
        if float(ensemble.residual_ratio) < 0.0:
            raise ValueError(
                "bar ensemble residual_ratio must not be negative, "
                f"got {ensemble.residual_ratio!r}"
            )
        if not isinstance(ensemble.stacks, (tuple, list)):
            raise ValueError("bar ensemble stacks must be a sequence of BarStack instances")
        if not ensemble.stacks:
            raise ValueError("bar ensemble stacks must not be empty")
        _validated_stacks(ensemble.stacks, function)
        if any(stack.orientation != ensemble.orientation for stack in ensemble.stacks):
            raise ValueError("bar ensemble and nested stack orientations must agree")
        result.append(ensemble)
    return tuple(result)


def _validated_board_image(image: np.ndarray, function: str) -> None:
    """Reject everything that is not one non-empty three channel uint8 image."""
    if not isinstance(image, np.ndarray):
        raise ValueError(f"{function} expects a numpy array")
    if image.dtype != np.uint8:
        raise ValueError(f"{function} expects uint8 pixels, got {image.dtype}")
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(
            f"{function} expects a three channel BGR image, got shape {image.shape}"
        )
    if image.size == 0:
        raise ValueError(f"{function} expects a non-empty image")


def _axis_concentration(anchors: Sequence[float], pitch: float) -> tuple[float, float]:
    """Circular concentration and mean phase of ``(anchor / pitch) mod 1``.

    Every line centre is ``first + index * pitch``, so the fractional parts of
    all anchors share one phase; two colours of one line shift that anchor by
    at most ``BAR_CENTER_TOLERANCE`` of a pitch and cancel in the circular
    mean. A wrong pitch spreads the phases and lowers the concentration, which
    is what makes the pitch identifiable without any absolute coordinate.
    """
    angles = [2.0 * math.pi * ((anchor / pitch) % 1.0) for anchor in anchors]
    sin_sum = math.fsum(math.sin(angle) for angle in angles)
    cos_sum = math.fsum(math.cos(angle) for angle in angles)
    concentration = math.hypot(sin_sum, cos_sum) / len(anchors)
    phase = (math.atan2(sin_sum, cos_sum) / (2.0 * math.pi)) % 1.0
    return float(concentration), float(phase)


def _axis_fit(
    anchors: Sequence[float], baseline: float, pitch: float
) -> _AxisFit | None:
    """Fit one axis at a fixed ``pitch`` from its anchors and bar baseline.

    The mean phase gives the first line centre up to a whole pitch; the bar
    baseline picks the period whose cell grid starts within ``BOARD_GAP_MAX``
    pitches of the baseline (the innermost bar sits about one slot outside the
    board). The fit is rejected when any anchor is farther than
    ``BOARD_FIT_TOLERANCE`` pitches from its nearest line centre, which happens
    when the anchors do not belong to this pitch at all.
    """
    concentration, phase = _axis_concentration(anchors, pitch)
    order = round((baseline + 0.5 * pitch - phase * pitch) / pitch)
    first = (phase + order) * pitch
    if not baseline - 1e-6 <= first - 0.5 * pitch <= baseline + BOARD_GAP_MAX * pitch:
        return None
    worst = max(
        abs(anchor - (first + round((anchor - first) / pitch) * pitch))
        for anchor in anchors
    )
    if worst > BOARD_FIT_TOLERANCE * pitch:
        return None
    return _AxisFit(pitch=float(pitch), first_center=float(first))


def _fit_board(
    column_anchors: Sequence[float],
    column_baseline: float,
    row_anchors: Sequence[float],
    row_baseline: float,
    pitch: float,
) -> tuple[_AxisFit, _AxisFit] | None:
    """Fit one square pitch and both first centres to the two bar axes.

    The pitch is scanned around the median ensemble step; a candidate pitch
    must fit both axes (see :func:`_axis_fit`) and is ranked by the summed
    circular concentration, by the worst residual and, only as a tie break, by
    its distance to the provisional step. Both axes share one pitch because the
    game grid is square and the two beams only disagree by a few percent. The
    scan is deterministic: a fixed resolution, a rounded key and no dependence
    on input order.
    """
    if pitch <= 0.0 or not math.isfinite(pitch):
        return None
    best: tuple[tuple[float, ...], _AxisFit, _AxisFit] | None = None
    steps = int(round((BOARD_SCALE_HIGH - BOARD_SCALE_LOW) / BOARD_SCALE_RESOLUTION))
    for index in range(steps + 1):
        scale = BOARD_SCALE_LOW + index * BOARD_SCALE_RESOLUTION
        candidate = pitch * scale
        columns = _axis_fit(column_anchors, column_baseline, candidate)
        rows = _axis_fit(row_anchors, row_baseline, candidate)
        if columns is None or rows is None:
            continue
        concentration, _ = _axis_concentration(column_anchors, candidate)
        row_concentration, _ = _axis_concentration(row_anchors, candidate)
        worst = max(
            _fit_worst(column_anchors, columns), _fit_worst(row_anchors, rows)
        )
        score = (
            concentration
            + row_concentration
            - abs(scale - 1.0)
            - 0.5 * worst / candidate
        )
        key = (round(score, 9), -round(abs(scale - 1.0), 9), round(candidate, 9))
        if best is None or key > best[0]:
            best = (key, columns, rows)
    if best is None:
        return None
    _, column_fit, row_fit = best
    # A short local walk removes the discretization of the coarse scan.
    best_worst = max(
        _fit_worst(column_anchors, column_fit), _fit_worst(row_anchors, row_fit)
    )
    for index in range(-20, 21):
        candidate = column_fit.pitch + index * BOARD_REFINE_RESOLUTION * pitch
        walked_columns = _axis_fit(column_anchors, column_baseline, candidate)
        walked_rows = _axis_fit(row_anchors, row_baseline, candidate)
        if walked_columns is None or walked_rows is None:
            continue
        worst = max(
            _fit_worst(column_anchors, walked_columns),
            _fit_worst(row_anchors, walked_rows),
        )
        key = (
            -round(worst, 9),
            -round(abs(candidate / pitch - 1.0), 9),
            -round(abs(candidate - column_fit.pitch), 9),
        )
        previous = (
            -round(best_worst, 9),
            -round(abs(column_fit.pitch / pitch - 1.0), 9),
            0.0,
        )
        if key > previous:
            best_worst = worst
            column_fit, row_fit = walked_columns, walked_rows
    return column_fit, row_fit


def _fit_worst(anchors: Sequence[float], fit: _AxisFit) -> float:
    """Largest distance between an anchor and its nearest line centre."""
    return max(
        abs(anchor - (fit.first_center + round((anchor - fit.first_center) / fit.pitch) * fit.pitch))
        for anchor in anchors
    )


def _board_signals(image: np.ndarray, step: float) -> tuple[np.ndarray, np.ndarray]:
    """Structure energy and saturated content planes of one screenshot.

    ``structure`` is the absolute difference between the grey image and a
    Gaussian blur whose sigma scales with the board pitch, capped so that one
    very bright UI element cannot dominate an average. ``content`` marks pixels
    that are saturated enough to be game colour even when a completion overlay
    dims the whole board: the value floor is far below B1a's component floor on
    purpose, because a dimmed placed piece still has to be recognized as board
    content.
    """
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    sigma = max(0.8, 0.025 * step)
    structure = np.minimum(np.abs(grey - cv2.GaussianBlur(grey, (0, 0), sigma)), 60.0)
    content = (hsv[:, :, 1] >= BOARD_CONTENT_SATURATION) & (
        hsv[:, :, 2] >= BOARD_CONTENT_VALUE
    )
    return structure, content


def _rectangle_mean(plane: np.ndarray, x0: float, x1: float, y0: float, y1: float) -> float:
    """Mean of one pixel rectangle clipped to the plane; 0.0 when it is empty."""
    height, width = plane.shape[:2]
    left = max(0, int(x0))
    right = min(width, int(x1))
    top = max(0, int(y0))
    bottom = min(height, int(y1))
    if right <= left or bottom <= top:
        return 0.0
    return float(plane[top:bottom, left:right].mean())


def _board_cell(
    structure: np.ndarray, content: np.ndarray, x0: float, y0: float, step: float
) -> tuple[float, float]:
    """``(texture, content_ratio)`` of one cell without keeping its pixels.

    ``texture`` is the smallest mean structure energy over the four half cells
    (left/right/top/bottom bands), so a frame line or a piece outline that only
    hugs one edge of the cell cannot fake board texture; ``content_ratio`` is
    the share of saturated pixels in the central ``BOARD_CONTENT_BOX`` box,
    which ignores such an edge band by construction.
    """
    near_low, near_high, far_low, far_high = BOARD_HALF_RANGES
    outer_low = BOARD_TEXTURE_LOW * step
    outer_high = BOARD_TEXTURE_HIGH * step
    left = _rectangle_mean(
        structure, x0 + near_low * step, x0 + near_high * step, y0 + outer_low, y0 + outer_high
    )
    right = _rectangle_mean(
        structure, x0 + far_low * step, x0 + far_high * step, y0 + outer_low, y0 + outer_high
    )
    top = _rectangle_mean(
        structure, x0 + outer_low, x0 + outer_high, y0 + near_low * step, y0 + near_high * step
    )
    bottom = _rectangle_mean(
        structure, x0 + outer_low, x0 + outer_high, y0 + far_low * step, y0 + far_high * step
    )
    height, width = content.shape[:2]
    box_left = max(0, int(x0 + BOARD_CONTENT_BOX[0] * step))
    box_right = min(width, int(x0 + BOARD_CONTENT_BOX[1] * step))
    box_top = max(0, int(y0 + BOARD_CONTENT_BOX[0] * step))
    box_bottom = min(height, int(y0 + BOARD_CONTENT_BOX[1] * step))
    ratio = 0.0
    if box_right > box_left and box_bottom > box_top:
        ratio = float(content[box_top:box_bottom, box_left:box_right].mean())
    return min(left, right, top, bottom), ratio


def _board_supported(
    texture: float, content: float, *, extending: bool
) -> bool:
    """Whether one cell carries board evidence.

    While the rectangle grows outwards the texture gate is slightly lower, so a
    zero target line with only faint in-cell strokes still joins the board;
    cells inside the final rectangle and cells of the ring outside it use the
    same, stricter gate, which keeps the comparison between them fair.
    """
    minimum = BOARD_TEXTURE_EXTEND_MIN if extending else BOARD_TEXTURE_MIN
    return texture >= minimum or content >= BOARD_CONTENT_RATIO


def _line_count(anchors: Sequence[float], fit: _AxisFit) -> int:
    """Number of lines from the first centre to the last observed anchor."""
    last = max(round((anchor - fit.first_center) / fit.pitch) for anchor in anchors)
    return last + 1


def _board_pair_candidate(
    image: np.ndarray, horizontal: BarEnsemble, vertical: BarEnsemble
) -> _BoardCandidate | None:
    """Fit one board rectangle from one horizontal/vertical ensemble pair.

    ``None`` means this pair cannot be a board: the two ensemble pitches differ
    by more than ``BOARD_STEP_TOLERANCE``, no common pitch starts both cell
    grids just outside their baselines, the first observed line is not the
    first line of the board, the rectangle is smaller than two lines, fewer
    than two rows and two columns carry evidence, or the ring just outside the
    rectangle carries so much evidence that the rectangle is not maximal.
    """
    scale = max(horizontal.step, vertical.step)
    if abs(horizontal.step - vertical.step) / scale > BOARD_STEP_TOLERANCE:
        return None
    provisional = float(statistics.median([horizontal.step, vertical.step]))
    fits = _fit_board(
        [stack.anchor for stack in horizontal.stacks],
        vertical.baseline,
        [stack.anchor for stack in vertical.stacks],
        horizontal.baseline,
        provisional,
    )
    if fits is None:
        return None
    columns_fit, rows_fit = fits
    columns = _line_count([stack.anchor for stack in horizontal.stacks], columns_fit)
    rows = _line_count([stack.anchor for stack in vertical.stacks], rows_fit)
    if not BOARD_MIN_LINES <= rows <= BOARD_MAX_LINES:
        return None
    if not BOARD_MIN_LINES <= columns <= BOARD_MAX_LINES:
        return None

    structure, content = _board_signals(image, columns_fit.pitch)
    limit = BOARD_MAX_LINES + 1
    texture = [[0.0] * limit for _ in range(limit)]
    ratio = [[0.0] * limit for _ in range(limit)]
    for row in range(limit):
        for column in range(limit):
            texture[row][column], ratio[row][column] = _board_cell(
                structure,
                content,
                columns_fit.first_center + (column - 0.5) * columns_fit.pitch,
                rows_fit.first_center + (row - 0.5) * rows_fit.pitch,
                columns_fit.pitch,
            )

    def supported(row: int, column: int) -> bool:
        return _board_supported(texture[row][column], ratio[row][column], extending=False)

    def extends(row: int, column: int) -> bool:
        return _board_supported(texture[row][column], ratio[row][column], extending=True)

    grew = True
    while grew:
        grew = False
        if rows < BOARD_MAX_LINES and all(extends(rows, column) for column in range(columns)):
            rows += 1
            grew = True
        if columns < BOARD_MAX_LINES and all(extends(row, columns) for row in range(rows)):
            columns += 1
            grew = True

    supported_rows: set[int] = set()
    supported_columns: set[int] = set()
    supported_cells = 0
    for row in range(rows):
        for column in range(columns):
            if supported(row, column):
                supported_rows.add(row)
                supported_columns.add(column)
                supported_cells += 1
    if len(supported_rows) < BOARD_MIN_SUPPORT_LINES:
        return None
    if len(supported_columns) < BOARD_MIN_SUPPORT_LINES:
        return None
    evidence_ratio = supported_cells / float(rows * columns)
    ring = [(row, columns) for row in range(rows)] + [(rows, column) for column in range(columns)]
    ring_supported = sum(1 for row, column in ring if supported(row, column))
    ring_ratio = ring_supported / float(len(ring))
    score = evidence_ratio - ring_ratio
    if score < BOARD_MIN_SCORE:
        return None
    return _BoardCandidate(
        first_center_x=float(columns_fit.first_center),
        first_center_y=float(rows_fit.first_center),
        pitch=float(columns_fit.pitch),
        rows=int(rows),
        columns=int(columns),
        evidence_ratio=float(evidence_ratio),
        ring_ratio=float(ring_ratio),
        score=float(score),
    )


def _distinct_candidates(candidates: Sequence[_BoardCandidate]) -> list[_BoardCandidate]:
    """Collapse near identical rectangles and rank them by score.

    Two candidates describe the same rectangle when their first centres stay
    within 5% of a pitch, their pitches within 2% and their line counts match;
    the best score survives, so a duplicated geometry can never be mistaken for
    the runner-up that decides the margin. The result is ordered by descending
    score, descending evidence and ascending geometry, which makes the choice
    independent of the ensemble order.
    """
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            -candidate.score,
            -candidate.evidence_ratio,
            candidate.rows,
            candidate.columns,
            candidate.first_center_x,
            candidate.first_center_y,
            candidate.pitch,
        ),
    )
    merged: list[_BoardCandidate] = []
    for candidate in ordered:
        if any(
            keep.rows == candidate.rows
            and keep.columns == candidate.columns
            and abs(keep.pitch - candidate.pitch) <= 0.02 * candidate.pitch
            and abs(keep.first_center_x - candidate.first_center_x)
            <= 0.05 * candidate.pitch
            and abs(keep.first_center_y - candidate.first_center_y)
            <= 0.05 * candidate.pitch
            for keep in merged
        ):
            continue
        merged.append(candidate)
    return merged


def locate_bar_board(
    image: np.ndarray, ensembles: Sequence[BarEnsemble]
) -> BoardGeometry | None:
    """Locate the unique bar board rectangle of one full BGR screenshot.

    ``image`` is validated exactly like :func:`saturated_components`, so a non
    array, a non uint8, a non three channel or an empty image raises
    ``ValueError``. ``ensembles`` must be a sequence of :class:`BarEnsemble`
    values; anything else raises ``ValueError``.

    Every horizontal/vertical ensemble pair whose pitches agree within
    ``BOARD_STEP_TOLERANCE`` is fitted as a candidate board: one square pitch
    and the two first line centres are read from the stack anchors, the cell
    grid has to start within ``BOARD_GAP_MAX`` pitches below/right of the bar
    baselines (the bar closest to the board sits about one slot outside it),
    and the rectangle is grown line by line while its cells still carry board
    texture or saturated content. That growth is what accepts a last line whose
    target is zero and rejects a rectangle that would end inside a larger
    board, while the decorative frame around the board never passes the texture
    gate because it only hugs the cell edges. A candidate also needs evidence
    on at least two rows and two columns, an ``evidence_ratio`` high enough to
    reach ``BOARD_MIN_SCORE`` after the ring outside the rectangle is
    subtracted, and a unique best score: near identical rectangles are merged
    first, and when a second, different rectangle scores within
    ``BOARD_MIN_SCORE_MARGIN`` the screenshot does not single out one geometry
    and ``None`` is returned.

    The returned :class:`BoardGeometry` holds only Python scalars and tuples
    and never a pixel, a mask, a contour or a crop.
    """
    _validated_board_image(image, "locate_bar_board")
    pool = _validated_ensembles(ensembles, "locate_bar_board")
    horizontals = [item for item in pool if item.orientation == "horizontal"]
    verticals = [item for item in pool if item.orientation == "vertical"]
    candidates: list[_BoardCandidate] = []
    for horizontal in horizontals:
        for vertical in verticals:
            candidate = _board_pair_candidate(image, horizontal, vertical)
            if candidate is not None:
                candidates.append(candidate)
    ranked = _distinct_candidates(candidates)
    if not ranked:
        return None
    best = ranked[0]
    margin = best.score - ranked[1].score if len(ranked) > 1 else best.score
    if margin < BOARD_MIN_SCORE_MARGIN:
        return None

    pitch = best.pitch
    column_centers = tuple(
        float(best.first_center_x + index * pitch) for index in range(best.columns)
    )
    row_centers = tuple(
        float(best.first_center_y + index * pitch) for index in range(best.rows)
    )
    return BoardGeometry(
        left=float(best.first_center_x - 0.5 * pitch),
        top=float(best.first_center_y - 0.5 * pitch),
        right=float(best.first_center_x + (best.columns - 0.5) * pitch),
        bottom=float(best.first_center_y + (best.rows - 0.5) * pitch),
        step=float(pitch),
        rows=int(best.rows),
        columns=int(best.columns),
        row_centers=row_centers,
        column_centers=column_centers,
        evidence_ratio=float(best.evidence_ratio),
        score_margin=float(margin),
    )


def _validated_geometry(geometry: BoardGeometry, function: str) -> None:
    """Reject a board geometry whose own fields contradict each other.

    This is a programmer error check, not a recognition step: a wrong type, a
    non finite or non positive number, unordered boundaries, line counts
    outside ``2..BOARD_MAX_LINES``, centre tuples whose length differs from the
    line count, non increasing or non finite centres, centres that do not sit
    inside their own cell, spacings that disagree with ``step`` or with each
    other by more than ``BOARD_STEP_TOLERANCE``, a ratio outside ``0..1`` or a
    negative margin all raise ``ValueError``.
    """
    if not isinstance(geometry, BoardGeometry):
        raise ValueError(f"{function} expects a BoardGeometry instance")
    for name in ("left", "top", "right", "bottom", "step", "evidence_ratio", "score_margin"):
        value = getattr(geometry, name)
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise ValueError(f"board geometry {name} must be a finite number, got {value!r}")
        if not math.isfinite(float(value)):
            raise ValueError(f"board geometry {name} must be a finite number, got {value!r}")
    if not float(geometry.step) > 0.0:
        raise ValueError(f"board geometry step must be positive, got {geometry.step!r}")
    if not (
        float(geometry.right) > float(geometry.left)
        and float(geometry.bottom) > float(geometry.top)
    ):
        raise ValueError("board geometry boundaries must be ordered")
    for name in ("rows", "columns"):
        value = getattr(geometry, name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"board geometry {name} must be an integer in "
                f"{BOARD_MIN_LINES}..{BOARD_MAX_LINES}, got {value!r}"
            )
        if not BOARD_MIN_LINES <= value <= BOARD_MAX_LINES:
            raise ValueError(
                f"board geometry {name} must be an integer in "
                f"{BOARD_MIN_LINES}..{BOARD_MAX_LINES}, got {value!r}"
            )
    evidence = float(geometry.evidence_ratio)
    if not 0.0 <= evidence <= 1.0:
        raise ValueError(
            f"board geometry evidence_ratio must be a ratio in 0..1, got {evidence!r}"
        )
    if float(geometry.score_margin) < 0.0:
        raise ValueError(
            f"board geometry score_margin must not be negative, got {geometry.score_margin!r}"
        )

    pitches: list[float] = []
    axes = (
        ("column_centers", geometry.column_centers, geometry.columns, geometry.left, geometry.right),
        ("row_centers", geometry.row_centers, geometry.rows, geometry.top, geometry.bottom),
    )
    for name, centers, count, low, high in axes:
        if isinstance(centers, (str, bytes)) or not isinstance(
            centers, (Sequence, np.ndarray)
        ):
            raise ValueError(f"board geometry {name} must be a sequence of centres")
        values = tuple(centers)
        if len(values) != count:
            raise ValueError(
                f"board geometry {name} must hold {count} centres, got {len(values)}"
            )
        previous: float | None = None
        for value in values:
            if isinstance(value, bool) or not isinstance(value, numbers.Real):
                raise ValueError(f"board geometry {name} must hold finite numbers")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"board geometry {name} must hold finite numbers")
            if previous is not None and number <= previous:
                raise ValueError(f"board geometry {name} must be strictly increasing")
            previous = number
        step = float(geometry.step)
        if abs((values[0] - 0.5 * step) - float(low)) > BOARD_FIT_TOLERANCE * step:
            raise ValueError(f"board geometry {name} disagrees with the near boundary")
        if abs((values[-1] + 0.5 * step) - float(high)) > BOARD_FIT_TOLERANCE * step:
            raise ValueError(f"board geometry {name} disagrees with the far boundary")
        spacing = values[1] - values[0]
        for earlier, later in zip(values, values[1:]):
            if abs((later - earlier) - spacing) > 0.01 * step:
                raise ValueError(f"board geometry {name} must be equally spaced")
        if abs(spacing - step) > BOARD_STEP_TOLERANCE * step:
            raise ValueError(f"board geometry {name} spacing disagrees with step")
        pitches.append(spacing)
    if abs(pitches[0] - pitches[1]) > BOARD_STEP_TOLERANCE * max(pitches):
        raise ValueError("board geometry row and column pitches disagree")


def extract_bar_targets(
    geometry: BoardGeometry, ensembles: Sequence[BarEnsemble]
) -> BarTargets | None:
    """Decode the row and column targets of one already located board.

    ``geometry`` must be a self consistent :class:`BoardGeometry` (see
    :func:`_validated_geometry`) and ``ensembles`` a sequence of well formed
    :class:`BarEnsemble` values, anything else raises ``ValueError``.

    Only the unique horizontal ensemble just above the board and the unique
    vertical ensemble just left of it are used: both have to agree with the
    board pitch within ``BOARD_STEP_TOLERANCE`` and their baseline has to sit
    within ``BAR_ENSEMBLE_GAP_MAX`` pitches outside the corresponding board
    edge. Zero or several adjacent ensembles on either axis return ``None``,
    because the board does not select one pair.

    The stack hues are clustered with :func:`cluster_hues` into one to four
    stable channels, every stack maps to the nearest line of its axis and to
    exactly one channel, and each stack count is added to that channel's line.
    A stack farther than ``BAR_CENTER_TOLERANCE`` pitches from any line centre,
    a duplicate ``(channel, line)``, a channel whose display offsets on one
    axis are not stable within ``BAR_OFFSET_TOLERANCE`` around their robust
    median, a line target above its capacity, a channel whose row and column
    totals differ, an empty channel or the combined channel targets exceeding
    a row or column capacity return ``None`` as well. Lines
    without a physical stack of a channel are the only thing filled in with
    ``0``, and that only happens once the geometry is unique: a completed board
    whose innermost bar was swallowed by the board highlight therefore stays
    incomplete instead of being guessed.

    ``channel_hues`` keeps the ascending OpenCV hue order of
    :func:`cluster_hues`, targets use the channel first layout
    ``row_targets[channel][row]`` / ``column_targets[channel][column]`` and
    ``residual_ratio`` is the mean offset deviation from the per channel robust
    median in units of the board step.
    """
    _validated_geometry(geometry, "extract_bar_targets")
    pool = _validated_ensembles(ensembles, "extract_bar_targets")
    step = float(geometry.step)

    adjacent: dict[str, list[BarEnsemble]] = {"horizontal": [], "vertical": []}
    for ensemble in pool:
        scale = max(ensemble.step, step)
        if abs(ensemble.step - step) / scale > BOARD_STEP_TOLERANCE:
            continue
        if ensemble.orientation == "horizontal":
            gap = float(geometry.top) - float(ensemble.baseline)
        else:
            gap = float(geometry.left) - float(ensemble.baseline)
        if 0.0 <= gap <= BAR_ENSEMBLE_GAP_MAX * step:
            adjacent[ensemble.orientation].append(ensemble)
    if len(adjacent["horizontal"]) != 1 or len(adjacent["vertical"]) != 1:
        return None
    stacks = tuple(adjacent["horizontal"][0].stacks) + tuple(adjacent["vertical"][0].stacks)

    clusters = cluster_hues([stack.hue for stack in stacks])
    if clusters is None:
        return None
    channels = len(clusters.centers)
    row_targets = [[0] * geometry.rows for _ in range(channels)]
    column_targets = [[0] * geometry.columns for _ in range(channels)]

    entries: list[tuple[int, str, int, int, float]] = []
    offsets: dict[tuple[int, str], list[float]] = {}
    for position, stack in enumerate(stacks):
        if stack.orientation == "horizontal":
            centers = geometry.column_centers
            axis = "column"
        else:
            centers = geometry.row_centers
            axis = "row"
        nearest = min(
            range(len(centers)), key=lambda index: abs(float(centers[index]) - stack.anchor)
        )
        offset = (stack.anchor - float(centers[nearest])) / step
        if abs(offset) > BAR_CENTER_TOLERANCE:
            return None
        channel = int(clusters.assignments[position])
        entries.append((channel, axis, nearest, int(stack.count), offset))
        offsets.setdefault((channel, axis), []).append(offset)

    medians = {
        key: float(statistics.median(values)) for key, values in offsets.items()
    }
    seen: set[tuple[int, str, int]] = set()
    residual_sum = 0.0
    for channel, axis, index, count, offset in entries:
        deviation = abs(offset - medians[(channel, axis)])
        if deviation > BAR_OFFSET_TOLERANCE:
            return None
        if (channel, axis, index) in seen:
            return None
        seen.add((channel, axis, index))
        if axis == "column":
            if count > geometry.rows:
                return None
            column_targets[channel][index] += count
        else:
            if count > geometry.columns:
                return None
            row_targets[channel][index] += count
        residual_sum += deviation

    for channel in range(channels):
        rows_total = sum(row_targets[channel])
        columns_total = sum(column_targets[channel])
        if rows_total != columns_total or rows_total == 0:
            return None
        if any(target > geometry.columns for target in row_targets[channel]):
            return None
        if any(target > geometry.rows for target in column_targets[channel]):
            return None
    if any(
        sum(row_targets[channel][row] for channel in range(channels)) > geometry.columns
        for row in range(geometry.rows)
    ):
        return None
    if any(
        sum(column_targets[channel][column] for channel in range(channels)) > geometry.rows
        for column in range(geometry.columns)
    ):
        return None

    return BarTargets(
        channel_hues=tuple(float(hue) for hue in clusters.centers),
        row_targets=tuple(tuple(int(value) for value in row) for row in row_targets),
        column_targets=tuple(
            tuple(int(value) for value in column) for column in column_targets
        ),
        residual_ratio=float(residual_sum / len(entries)),
    )


# ---------------------------------------------------------------------------
# board cell states (B1b3a)

CELL_DIM_MIN_SATURATION = 180
CELL_DIM_MIN_VALUE = 30
CELL_INNER_LOW = 0.06
CELL_INNER_HIGH = 0.94
CELL_COLORED_RATIO = 0.25
CELL_COLORED_AMBIGUITY_RATIO = 0.15
CELL_COLORED_THRESHOLD_MARGIN = 0.03
CELL_SEAM_HALF_WIDTH = 0.06
CELL_SEAM_MIN_RATIO = 0.45
CELL_SEAM_THRESHOLD_MARGIN = 0.03

CELL_LOCK_WINDOW_LOW = 0.28
CELL_LOCK_WINDOW_HIGH = 0.72
CELL_LOCK_VALUE_DELTA = 30
CELL_LOCK_MIN_RATIO = 0.28
CELL_LOCK_MAX_RATIO = 0.50
CELL_LOCK_MIN_SYMMETRY = 0.55
CELL_LOCK_THRESHOLD_MARGIN = 0.02
CELL_FIXED_BORDER_WIDTH = 0.025
CELL_FIXED_MIN_BORDER_GAP = 0.28
CELL_FIXED_BORDER_MARGIN = 0.03

CELL_NEUTRAL_MAX_SATURATION = 60
CELL_BLOCKED_MIN_NEUTRAL_RATIO = 0.70
CELL_BLOCKED_MIN_STRUCTURE_RATIO = 0.35
CELL_BLOCKED_STRONG_STRUCTURE_RATIO = 0.28
CELL_BLOCKED_LOCAL_VALUE_DELTA = 2
CELL_BLOCKED_BASELINE_MINIMUM = 3
CELL_BLOCKED_THRESHOLD_MARGIN = 0.005


@dataclass(frozen=True)
class BoardCellMap:
    """Complete immutable state matrix of one already located board.

    ``cells`` is row major and has exactly the dimensions of the supplied
    :class:`BoardGeometry`. ``minimum_confidence`` is the smallest confidence
    in that matrix. The public function returns ``None`` instead of this value
    when any cell is too close to a decision boundary, so no partial map can
    be mistaken for a complete puzzle statement.
    """

    cells: tuple[tuple[CellClass, ...], ...]
    minimum_confidence: float


def _board_channel_masks(
    hsv: np.ndarray, hues: tuple[float, ...]
) -> tuple[np.ndarray, ...]:
    """Mutually exclusive nearest-channel masks for one board ROI.

    The normal tier preserves the B1a saturation/value floor. The second tier
    admits completion screens darkened by the game's overlay, but only when
    saturation is high enough that a smooth page glow cannot become content.
    """
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    candidate = ((saturation >= MIN_SATURATION) & (value >= MIN_VALUE)) | (
        (saturation >= CELL_DIM_MIN_SATURATION) & (value >= CELL_DIM_MIN_VALUE)
    )
    masks = tuple(np.zeros(candidate.shape, dtype=bool) for _ in hues)
    positions = np.flatnonzero(candidate.reshape(-1))
    if positions.size == 0:
        return masks

    samples = hsv[:, :, 0].reshape(-1)[positions].astype(np.float64)
    deltas = np.abs(samples[:, None] - np.asarray(hues, dtype=np.float64)[None, :])
    distances = np.minimum(deltas, HUE_PERIOD - deltas)
    owners = np.argmin(distances, axis=1)
    accepted = distances[np.arange(len(positions)), owners] <= CHANNEL_HUE_TOLERANCE
    if len(hues) > 1:
        nearest = np.partition(distances, 1, axis=1)[:, :2]
        accepted &= nearest[:, 1] - nearest[:, 0] > CHANNEL_AMBIGUITY_MARGIN
    for channel, mask in enumerate(masks):
        mask.reshape(-1)[positions[accepted & (owners == channel)]] = True
    return masks


def _board_cell_boxes(
    geometry: BoardGeometry, origin_x: int, origin_y: int, width: int, height: int
) -> tuple[tuple[tuple[int, int, int, int], ...], ...] | None:
    """Integer ``(left, top, right, bottom)`` boxes relative to a board ROI."""
    step = float(geometry.step)
    rows: list[tuple[tuple[int, int, int, int], ...]] = []
    for center_y in geometry.row_centers:
        top = int(round(float(center_y) - origin_y - 0.5 * step))
        bottom = int(round(float(center_y) - origin_y + 0.5 * step))
        line: list[tuple[int, int, int, int]] = []
        for center_x in geometry.column_centers:
            left = int(round(float(center_x) - origin_x - 0.5 * step))
            right = int(round(float(center_x) - origin_x + 0.5 * step))
            if (
                left < 0
                or top < 0
                or right > width
                or bottom > height
                or right - left < MIN_CELL_SIDE
                or bottom - top < MIN_CELL_SIDE
            ):
                return None
            inner_x = _region_bounds(right - left, CELL_INNER_LOW, CELL_INNER_HIGH)
            inner_y = _region_bounds(bottom - top, CELL_INNER_LOW, CELL_INNER_HIGH)
            if inner_x[1] - inner_x[0] < MIN_CELL_SIDE:
                return None
            if inner_y[1] - inner_y[0] < MIN_CELL_SIDE:
                return None
            line.append((left, top, right, bottom))
        rows.append(tuple(line))
    return tuple(rows)


def _board_box_ratio(mask: np.ndarray, box: tuple[int, int, int, int]) -> float:
    """Foreground share of one non-empty integer box."""
    left, top, right, bottom = box
    return float(np.count_nonzero(mask[top:bottom, left:right])) / float(
        (right - left) * (bottom - top)
    )


def _board_inner_box(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """The fixed inner sampling rectangle of one cell box."""
    left, top, right, bottom = box
    inner_x = _region_bounds(right - left, CELL_INNER_LOW, CELL_INNER_HIGH)
    inner_y = _region_bounds(bottom - top, CELL_INNER_LOW, CELL_INNER_HIGH)
    return (
        left + inner_x[0],
        top + inner_y[0],
        left + inner_x[1],
        top + inner_y[1],
    )


def _board_lock_evidence(
    channel_mask: np.ndarray,
    value: np.ndarray,
    box: tuple[int, int, int, int],
) -> tuple[float, float]:
    """Central glyph coverage and vertical mirror IoU of one colored cell."""
    left, top, right, bottom = box
    window_x = _region_bounds(right - left, CELL_LOCK_WINDOW_LOW, CELL_LOCK_WINDOW_HIGH)
    window_y = _region_bounds(bottom - top, CELL_LOCK_WINDOW_LOW, CELL_LOCK_WINDOW_HIGH)
    x0, x1 = left + window_x[0], left + window_x[1]
    y0, y1 = top + window_y[0], top + window_y[1]
    mask = channel_mask[y0:y1, x0:x1]
    if np.count_nonzero(mask) < MIN_CELL_SIDE:
        return 0.0, 0.0
    window_value = value[y0:y1, x0:x1].astype(np.float64)
    median = float(np.median(window_value[mask]))
    glyph = mask & (np.abs(window_value - median) >= CELL_LOCK_VALUE_DELTA)
    ratio = float(np.count_nonzero(glyph)) / float(glyph.size)
    mirrored = glyph[:, ::-1]
    union = int(np.count_nonzero(glyph | mirrored))
    symmetry = 0.0 if union == 0 else float(np.count_nonzero(glyph & mirrored)) / union
    return ratio, symmetry


def _board_border_gap(
    channel_mask: np.ndarray,
    box: tuple[int, int, int, int],
    inner_ratio: float,
) -> float:
    """Difference between cell fill and the four narrow boundary bands.

    Fixed squares keep their own dark outline on every side. A placed piece
    can contain a lock-like highlight, but its channel normally continues to
    one or more grid boundaries. Averaging all four bands gives an independent
    square-border signal without depending on an absolute line thickness.
    """
    left, top, right, bottom = box
    width = max(1, int(round(CELL_FIXED_BORDER_WIDTH * (right - left))))
    height = max(1, int(round(CELL_FIXED_BORDER_WIDTH * (bottom - top))))
    sides = (
        (left, top, min(right, left + width), bottom),
        (max(left, right - width), top, right, bottom),
        (left, top, right, min(bottom, top + height)),
        (left, max(top, bottom - height), right, bottom),
    )
    border_ratio = statistics.fmean(
        _board_box_ratio(channel_mask, side) for side in sides
    )
    return float(inner_ratio - border_ratio)


def _board_seam_ratio(
    mask: np.ndarray,
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
    step: float,
) -> float:
    """Channel coverage in the thin band shared by adjacent cell boxes."""
    half = max(1, int(round(CELL_SEAM_HALF_WIDTH * step)))
    first_left, first_top, first_right, first_bottom = first
    second_left, second_top, second_right, second_bottom = second
    if first_top == second_top:
        boundary = int(round((first_right + second_left) / 2.0))
        box = (
            max(0, boundary - half),
            max(first_top, second_top),
            min(mask.shape[1], boundary + half),
            min(first_bottom, second_bottom),
        )
    else:
        boundary = int(round((first_bottom + second_top) / 2.0))
        box = (
            max(first_left, second_left),
            max(0, boundary - half),
            min(first_right, second_right),
            min(mask.shape[0], boundary + half),
        )
    if box[2] <= box[0] or box[3] <= box[1]:
        return 0.0
    return _board_box_ratio(mask, box)


def _board_neutral_features(
    hsv: np.ndarray, box: tuple[int, int, int, int]
) -> tuple[float, float, float]:
    """Neutral coverage, median value and distributed structure of one cell."""
    left, top, right, bottom = box
    crop = hsv[top:bottom, left:right]
    neutral = crop[:, :, 1] <= CELL_NEUTRAL_MAX_SATURATION
    neutral_count = int(np.count_nonzero(neutral))
    if neutral_count == 0:
        return 0.0, 0.0, 0.0
    values = crop[:, :, 2].astype(np.float64)
    median = float(np.median(values[neutral]))

    # Empty cells may sit under a strong but smooth page glow. Measuring a
    # deviation from the cell median would turn that gradient into structure,
    # so normalize the cell to a fixed grid and compare it with a local blur.
    # The obstacle hatch and central prohibition glyph retain local contrast;
    # a smooth glow and the sparse empty-cell corner ticks do not.
    normalized_value = cv2.resize(
        crop[:, :, 2], (48, 48), interpolation=cv2.INTER_AREA
    ).astype(np.float32)
    normalized_saturation = cv2.resize(
        crop[:, :, 1], (48, 48), interpolation=cv2.INTER_AREA
    )
    normalized_neutral = normalized_saturation <= CELL_NEUTRAL_MAX_SATURATION
    local_mean = cv2.GaussianBlur(normalized_value, (7, 7), 0)
    structured = normalized_neutral & (
        np.abs(normalized_value - local_mean) >= CELL_BLOCKED_LOCAL_VALUE_DELTA
    )
    normalized_neutral_count = int(np.count_nonzero(normalized_neutral))
    return (
        neutral_count / float(neutral.size),
        median,
        0.0
        if normalized_neutral_count == 0
        else float(np.count_nonzero(structured)) / normalized_neutral_count,
    )


def _board_empty_baseline(values: Sequence[float]) -> tuple[float, float]:
    """Robust dark-cell baseline and spread, resistant to bright blockers."""
    ordered = sorted(float(value) for value in values)
    lower_count = max(1, (len(ordered) + 1) // 2)
    lower = ordered[:lower_count]
    baseline = float(statistics.median(lower))
    mad = float(statistics.median(abs(value - baseline) for value in lower))
    return baseline, max(2.0, 1.4826 * mad)


def extract_board_cells(
    image: np.ndarray,
    geometry: BoardGeometry,
    channel_hues: Sequence[float],
) -> BoardCellMap | None:
    """Classify every cell of an already confirmed board rectangle.

    Invalid argument types or contradictory immutable inputs raise
    ``ValueError``. A valid screenshot whose board is clipped or whose visual
    evidence is incomplete returns ``None``. The function performs one HSV
    conversion for the whole board, resolves channel ownership globally,
    confirms lock-bearing fixed cells before joining placed cells across grid
    seams, then distinguishes neutral blockers from empty cells with a robust
    within-board brightness baseline and distributed structure.
    """
    _validated_board_image(image, "extract_board_cells")
    _validated_geometry(geometry, "extract_board_cells")
    hues = _normalized_channel_hues(channel_hues)

    left = int(math.floor(float(geometry.left)))
    top = int(math.floor(float(geometry.top)))
    right = int(math.ceil(float(geometry.right)))
    bottom = int(math.ceil(float(geometry.bottom)))
    height, width = image.shape[:2]
    if left < 0 or top < 0 or right > width or bottom > height:
        return None
    roi = image[top:bottom, left:right]
    if roi.shape[0] < MIN_CELL_SIDE or roi.shape[1] < MIN_CELL_SIDE:
        return None

    boxes = _board_cell_boxes(geometry, left, top, roi.shape[1], roi.shape[0])
    if boxes is None:
        return None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    value = hsv[:, :, 2]
    masks = _board_channel_masks(hsv, hues)

    owners: list[list[int | None]] = []
    owner_ratios: list[list[float]] = []
    for row in range(geometry.rows):
        owner_row: list[int | None] = []
        ratio_row: list[float] = []
        for column in range(geometry.columns):
            inner = _board_inner_box(boxes[row][column])
            ratios = [_board_box_ratio(mask, inner) for mask in masks]
            order = sorted(range(len(ratios)), key=lambda index: ratios[index], reverse=True)
            best = float(ratios[order[0]])
            second = float(ratios[order[1]]) if len(order) > 1 else 0.0
            if second >= CELL_COLORED_AMBIGUITY_RATIO:
                return None
            if abs(best - CELL_COLORED_RATIO) <= CELL_COLORED_THRESHOLD_MARGIN:
                return None
            owner_row.append(int(order[0]) if best > CELL_COLORED_RATIO else None)
            ratio_row.append(best)
        owners.append(owner_row)
        owner_ratios.append(ratio_row)

    kinds: list[list[Literal["empty", "blocked", "fixed", "placed"] | None]] = [
        [None] * geometry.columns for _ in range(geometry.rows)
    ]
    confidences = [[1.0] * geometry.columns for _ in range(geometry.rows)]

    # Locks are conclusive before connectivity: adjacent fixed squares can be
    # close enough to share saturated antialiasing, but each keeps its own
    # centred, mirror-symmetric padlock glyph.
    for row in range(geometry.rows):
        for column in range(geometry.columns):
            owner = owners[row][column]
            if owner is None:
                continue
            glyph_ratio, symmetry = _board_lock_evidence(
                masks[owner], value, boxes[row][column]
            )
            border_gap = _board_border_gap(
                masks[owner], boxes[row][column], owner_ratios[row][column]
            )
            near_lock = (
                CELL_LOCK_MIN_RATIO - CELL_LOCK_THRESHOLD_MARGIN
                <= glyph_ratio
                <= CELL_LOCK_MAX_RATIO + CELL_LOCK_THRESHOLD_MARGIN
                and symmetry >= CELL_LOCK_MIN_SYMMETRY - CELL_LOCK_THRESHOLD_MARGIN
            )
            locked = (
                CELL_LOCK_MIN_RATIO < glyph_ratio < CELL_LOCK_MAX_RATIO
                and symmetry > CELL_LOCK_MIN_SYMMETRY
            )
            bordered = border_gap > CELL_FIXED_MIN_BORDER_GAP
            if locked and bordered:
                if (
                    abs(glyph_ratio - CELL_LOCK_MIN_RATIO) <= CELL_LOCK_THRESHOLD_MARGIN
                    or abs(glyph_ratio - CELL_LOCK_MAX_RATIO) <= CELL_LOCK_THRESHOLD_MARGIN
                    or symmetry - CELL_LOCK_MIN_SYMMETRY <= CELL_LOCK_THRESHOLD_MARGIN
                    or border_gap - CELL_FIXED_MIN_BORDER_GAP
                    <= CELL_FIXED_BORDER_MARGIN
                ):
                    return None
                kinds[row][column] = "fixed"
            elif (
                near_lock
                and abs(border_gap - CELL_FIXED_MIN_BORDER_GAP)
                <= CELL_FIXED_BORDER_MARGIN
            ):
                return None
            elif near_lock and not locked:
                return None

    # Remove fixed boxes from the masks before joining placed cells. This is
    # what prevents a lock cell touching a completed piece from joining it.
    placed_masks = [mask.copy() for mask in masks]
    for row in range(geometry.rows):
        for column in range(geometry.columns):
            if kinds[row][column] != "fixed":
                continue
            owner = owners[row][column]
            assert owner is not None
            box = boxes[row][column]
            placed_masks[owner][box[1] : box[3], box[0] : box[2]] = False

    adjacency: dict[tuple[int, int], set[tuple[int, int]]] = {}
    seam_margins: dict[tuple[int, int], list[float]] = {}
    for row in range(geometry.rows):
        for column in range(geometry.columns):
            if owners[row][column] is None or kinds[row][column] == "fixed":
                continue
            point = (row, column)
            adjacency.setdefault(point, set())
            seam_margins.setdefault(point, [])
            for neighbor in ((row, column + 1), (row + 1, column)):
                other_row, other_column = neighbor
                if other_row >= geometry.rows or other_column >= geometry.columns:
                    continue
                owner = owners[row][column]
                if owner != owners[other_row][other_column]:
                    continue
                if kinds[other_row][other_column] == "fixed":
                    continue
                assert owner is not None
                seam = _board_seam_ratio(
                    placed_masks[owner],
                    boxes[row][column],
                    boxes[other_row][other_column],
                    float(geometry.step),
                )
                if abs(seam - CELL_SEAM_MIN_RATIO) <= CELL_SEAM_THRESHOLD_MARGIN:
                    return None
                if seam > CELL_SEAM_MIN_RATIO:
                    adjacency.setdefault(neighbor, set()).add(point)
                    adjacency[point].add(neighbor)
                    margin = seam - CELL_SEAM_MIN_RATIO
                    seam_margins[point].append(margin)
                    seam_margins.setdefault(neighbor, []).append(margin)

    pending = set(adjacency)
    while pending:
        start = min(pending)
        group = {start}
        stack = [start]
        pending.remove(start)
        while stack:
            point = stack.pop()
            for neighbor in adjacency[point]:
                if neighbor not in group:
                    group.add(neighbor)
                    pending.discard(neighbor)
                    stack.append(neighbor)
        if len(group) < 2:
            return None
        for row, column in group:
            kinds[row][column] = "placed"
            minimum_margin = min(seam_margins[(row, column)])
            confidences[row][column] = min(
                1.0,
                minimum_margin / (2.0 * CELL_SEAM_THRESHOLD_MARGIN),
            )

    # Remaining cells have no recognized channel. Neutral candidates use the
    # same-board lower half as the empty brightness baseline, so the bright
    # blocker population cannot pull the reference up to itself.
    neutral: list[list[tuple[float, float, float] | None]] = [
        [None] * geometry.columns for _ in range(geometry.rows)
    ]
    baseline_values: list[float] = []
    for row in range(geometry.rows):
        for column in range(geometry.columns):
            if owners[row][column] is not None:
                continue
            features = _board_neutral_features(hsv, boxes[row][column])
            neutral[row][column] = features
            if features[0] >= 0.50:
                baseline_values.append(features[1])
    if baseline_values:
        baseline, spread = _board_empty_baseline(baseline_values)
    else:
        baseline, spread = 0.0, 2.0
    brightness_threshold = baseline + 3.0 * spread
    thin_baseline = len(baseline_values) < CELL_BLOCKED_BASELINE_MINIMUM

    for row in range(geometry.rows):
        for column in range(geometry.columns):
            if kinds[row][column] in ("fixed", "placed"):
                continue
            if owners[row][column] is not None:
                # A colored singleton without a confirmed lock is an
                # indistinguishable one-cell placed piece, never a guess.
                return None
            features = neutral[row][column]
            assert features is not None
            neutral_ratio, neutral_value, structure_ratio = features
            bright = neutral_value > brightness_threshold
            if thin_baseline:
                # A nearly completed board can leave only blockers outside the
                # channel mask, so there may be no dark empty population from
                # which to infer brightness. In that case the dense neutral
                # cover and the scale-normalized hatch/symbol must both be
                # strong; weaker evidence stays incomplete.
                blocked = (
                    neutral_ratio >= 0.85
                    and structure_ratio >= CELL_BLOCKED_STRONG_STRUCTURE_RATIO
                )
                structure_threshold = CELL_BLOCKED_STRONG_STRUCTURE_RATIO
            else:
                blocked = (
                    neutral_ratio > CELL_BLOCKED_MIN_NEUTRAL_RATIO
                    and structure_ratio > CELL_BLOCKED_MIN_STRUCTURE_RATIO
                    and bright
                )
                structure_threshold = CELL_BLOCKED_MIN_STRUCTURE_RATIO
            if blocked:
                near_boundary = (
                    neutral_ratio
                    - (0.85 if thin_baseline else CELL_BLOCKED_MIN_NEUTRAL_RATIO)
                    <= CELL_BLOCKED_THRESHOLD_MARGIN
                    or structure_ratio - structure_threshold
                    <= CELL_BLOCKED_THRESHOLD_MARGIN
                )
                # A thin baseline is used precisely when a nearly completed
                # board has too few dark empty cells to provide a trustworthy
                # brightness reference. Do not apply that unavailable signal
                # as a confidence margin after the structural test succeeds.
                if not thin_baseline:
                    near_boundary |= (
                        (neutral_value - brightness_threshold)
                        / max(1.0, brightness_threshold)
                        <= CELL_BLOCKED_THRESHOLD_MARGIN
                    )
                if near_boundary:
                    return None
                kinds[row][column] = "blocked"
            else:
                kinds[row][column] = "empty"

    cells: list[tuple[CellClass, ...]] = []
    for row in range(geometry.rows):
        line: list[CellClass] = []
        for column in range(geometry.columns):
            kind = kinds[row][column]
            assert kind is not None
            channel = owners[row][column] if kind in ("fixed", "placed") else None
            confidence = float(confidences[row][column])
            line.append(CellClass(kind=kind, channel=channel, confidence=confidence))
        cells.append(tuple(line))
    minimum_confidence = min(cell.confidence for row in cells for cell in row)
    return BoardCellMap(cells=tuple(cells), minimum_confidence=float(minimum_confidence))


# ---------------------------------------------------------------------------
# inventory slots and pieces (B1b3b)

INVENTORY_SLOT_SIDE_RATIOS = (1.55, 1.57, 1.59)
INVENTORY_SLOT_PITCH_RATIOS = (1.70, 1.72, 1.74)
INVENTORY_SLOT_BORDER_WIDTH = 0.035
INVENTORY_FRAME_SEGMENTS = 4
INVENTORY_STRUCTURE_SIGMA = 0.02
INVENTORY_MIN_FRAME_RESPONSE = 0.25
INVENTORY_RELATIVE_FRAME_RESPONSE = 0.35
INVENTORY_GRID_AMBIGUITY_RATIO = 0.75
INVENTORY_GRID_DEDUP_DISTANCE = 0.10
INVENTORY_MAX_SLOTS = 32
INVENTORY_CANDIDATE_LIMIT = 96
INVENTORY_CONTENT_LOW = 0.16
INVENTORY_CONTENT_HIGH = 0.84
INVENTORY_CONTENT_MIN_AREA = 0.020
INVENTORY_CONTENT_SMALL_AREA = 0.006
INVENTORY_CONTENT_CLOSE_SIZE = 0.04
INVENTORY_DIVIDER_MIN_GRADIENT = 0.75
INVENTORY_DIVIDER_AXIS_DELTA = 0.20


@dataclass(frozen=True)
class InventoryPiece:
    """One uniquely reconstructed piece in a confirmed inventory slot."""

    slot_index: int
    channel: int
    cells: tuple[tuple[int, int], ...]
    rows: int
    columns: int
    iou: float
    center_x: float
    center_y: float


@dataclass(frozen=True)
class InventoryState:
    """Complete immutable inventory, including slots that are empty."""

    slot_count: int
    empty_count: int
    pieces: tuple[InventoryPiece, ...]
    minimum_confidence: float


@dataclass(frozen=True)
class _InventoryGrid:
    """Internal slot lattice; every coordinate is a plain Python scalar."""

    columns: int
    side: int
    pitch: int
    left: int
    top: int
    slot_count: int
    scores: tuple[float, ...]
    threshold: float


def _inventory_frame_response(
    structure: np.ndarray, side: int, band: int
) -> np.ndarray:
    """Weakest distributed response over four segmented square-frame sides.

    A single mean per side can be raised by short, strong crossings from four
    neighboring slots. Splitting every side and taking the weakest segment
    requires continuous frame support while retaining dim but complete slots.
    """
    height, width = structure.shape
    valid_height = height - side + 1
    valid_width = width - side + 1
    if valid_height <= 0 or valid_width <= 0:
        return np.zeros((0, 0), dtype=np.float32)
    response = np.full((valid_height, valid_width), np.inf, dtype=np.float32)
    for segment in range(INVENTORY_FRAME_SEGMENTS):
        start = int(round(segment * side / INVENTORY_FRAME_SEGMENTS))
        end = int(round((segment + 1) * side / INVENTORY_FRAME_SEGMENTS))
        length = end - start
        horizontal = cv2.boxFilter(
            structure,
            -1,
            (length, band),
            anchor=(0, 0),
            normalize=True,
            borderType=cv2.BORDER_CONSTANT,
        )
        vertical = cv2.boxFilter(
            structure,
            -1,
            (band, length),
            anchor=(0, 0),
            normalize=True,
            borderType=cv2.BORDER_CONSTANT,
        )
        response = np.minimum.reduce(
            (
                response,
                horizontal[:valid_height, start : start + valid_width],
                horizontal[
                    side - band : side - band + valid_height,
                    start : start + valid_width,
                ],
                vertical[start : start + valid_height, :valid_width],
                vertical[
                    start : start + valid_height,
                    side - band : side - band + valid_width,
                ],
            )
        )
    return response


def _inventory_grid_position(
    left: int, top: int, pitch: int, columns: int, index: int
) -> tuple[int, int]:
    """Top-left pixel of one row-major slot lattice position."""
    row, column = divmod(index, columns)
    return left + column * pitch, top + row * pitch


def _inventory_grid_candidate(
    response: np.ndarray,
    *,
    left: int,
    top: int,
    side: int,
    pitch: int,
    columns: int,
    minimum_left: int,
    minimum_response: float,
) -> _InventoryGrid | None:
    """Confirm a maximal one/two-column row-major frame prefix."""
    height, width = response.shape
    if not (0 <= top < height and minimum_left <= left < width):
        return None
    anchor_scores: list[float] = []
    for index in range(columns):
        x, y = _inventory_grid_position(left, top, pitch, columns, index)
        if x < 0 or y < 0 or x >= width or y >= height:
            return None
        anchor_scores.append(float(response[y, x]))
    anchor = min(anchor_scores)
    if anchor < minimum_response:
        return None
    threshold = max(
        minimum_response,
        INVENTORY_RELATIVE_FRAME_RESPONSE * anchor,
    )
    if any(score < threshold for score in anchor_scores):
        return None

    # A candidate beginning in the second real row/column is a suffix, not a
    # complete inventory. Reject any same-lattice frame above or to its left.
    previous_left = left - pitch
    if previous_left >= minimum_left and float(response[top, previous_left]) >= threshold:
        return None
    previous_top = top - pitch
    while previous_top >= 0:
        for column in range(columns):
            x = left + column * pitch
            if x < width and float(response[previous_top, x]) >= threshold:
                return None
        previous_top -= pitch

    if columns == 1:
        # A one-column interpretation may not ignore frames in the parallel
        # position where a second column would live. Otherwise a damaged
        # two-column grid could collapse to an apparently valid shorter list.
        parallel_left = left + pitch
        parallel_top = top
        while parallel_left < width and parallel_top < height:
            if float(response[parallel_top, parallel_left]) >= threshold:
                return None
            parallel_top += pitch

    scores: list[float] = []
    check_limit = INVENTORY_MAX_SLOTS + 4
    for index in range(check_limit):
        x, y = _inventory_grid_position(left, top, pitch, columns, index)
        if x < 0 or y < 0 or x >= width or y >= height:
            break
        scores.append(float(response[y, x]))
    if not scores:
        return None
    present = tuple(score >= threshold for score in scores)
    try:
        slot_count = present.index(False)
    except ValueError:
        # The image never shows a complete blank terminator. The panel may be
        # clipped or contain more pieces than the domain permits.
        return None
    if slot_count < 1 or slot_count > INVENTORY_MAX_SLOTS:
        return None
    if any(present[slot_count + 1 :]):
        return None

    # A partially visible next slot can otherwise look like a blank terminator
    # because one of its four sides is missing. Reject when that predicted box
    # crosses an image edge; a fully visible blank box is the completeness
    # witness for this prefix.
    next_x, next_y = _inventory_grid_position(
        left, top, pitch, columns, slot_count
    )
    if not (0 <= next_x < width and 0 <= next_y < height):
        return None
    return _InventoryGrid(
        columns=int(columns),
        side=int(side),
        pitch=int(pitch),
        left=int(left),
        top=int(top),
        slot_count=int(slot_count),
        scores=tuple(float(score) for score in scores[:slot_count]),
        threshold=float(threshold),
    )


def _inventory_same_grid(
    first: _InventoryGrid, second: _InventoryGrid, step: float
) -> bool:
    """Whether two nearby scale hypotheses describe the same slot boxes."""
    if first.slot_count != second.slot_count or first.columns != second.columns:
        return False
    tolerance = INVENTORY_GRID_DEDUP_DISTANCE * step
    for index in range(first.slot_count):
        first_x, first_y = _inventory_grid_position(
            first.left, first.top, first.pitch, first.columns, index
        )
        second_x, second_y = _inventory_grid_position(
            second.left, second.top, second.pitch, second.columns, index
        )
        first_center = (first_x + 0.5 * first.side, first_y + 0.5 * first.side)
        second_center = (second_x + 0.5 * second.side, second_y + 0.5 * second.side)
        if math.dist(first_center, second_center) > tolerance:
            return False
    return True


def _inventory_grid_score(grid: _InventoryGrid) -> tuple[int, float, float]:
    """Prefer the longest prefix, then its weakest and mean frame support."""
    return (
        grid.slot_count,
        min(grid.scores),
        float(statistics.fmean(grid.scores)),
    )


def _inventory_locate_grid(
    image: np.ndarray, geometry: BoardGeometry
) -> _InventoryGrid | None:
    """Locate one unique inventory frame grid to the right of the board."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    sigma = max(0.8, INVENTORY_STRUCTURE_SIGMA * float(geometry.step))
    structure = np.abs(gray - cv2.GaussianBlur(gray, (0, 0), sigma))
    minimum_left = max(0, int(math.ceil(geometry.right + 0.20 * geometry.step)))
    candidates: list[_InventoryGrid] = []

    for side_ratio in INVENTORY_SLOT_SIDE_RATIOS:
        side = int(round(side_ratio * geometry.step))
        band = max(2, int(round(INVENTORY_SLOT_BORDER_WIDTH * geometry.step)))
        response = _inventory_frame_response(structure, side, band)
        if response.size == 0 or minimum_left >= response.shape[1]:
            continue
        search = response.copy()
        search[:, :minimum_left] = -1.0
        # A first slot may sit above or below the board top, but it cannot start
        # far below the board itself. This keeps unrelated bottom controls out.
        maximum_top = min(
            response.shape[0] - 1,
            int(math.ceil(geometry.bottom + 0.50 * geometry.step)),
        )
        if maximum_top + 1 < response.shape[0]:
            search[maximum_top + 1 :, :] = -1.0
        minimum_response = max(
            INVENTORY_MIN_FRAME_RESPONSE,
            INVENTORY_RELATIVE_FRAME_RESPONSE * float(np.max(search)),
        )
        radius = max(3, int(round(0.12 * geometry.step)))
        maxima = cv2.dilate(search, np.ones((radius, radius), dtype=np.uint8))
        points = np.argwhere(
            (search >= minimum_response) & (search >= maxima - 1e-6)
        )
        ranked = sorted(
            ((float(search[y, x]), int(x), int(y)) for y, x in points),
            key=lambda item: (-item[0], item[2], item[1]),
        )[:INVENTORY_CANDIDATE_LIMIT]

        for pitch_ratio in INVENTORY_SLOT_PITCH_RATIOS:
            pitch = int(round(pitch_ratio * geometry.step))
            for _, left, top in ranked:
                for columns in (1, 2):
                    candidate = _inventory_grid_candidate(
                        response,
                        left=left,
                        top=top,
                        side=side,
                        pitch=pitch,
                        columns=columns,
                        minimum_left=minimum_left,
                        minimum_response=minimum_response,
                    )
                    if candidate is not None:
                        candidates.append(candidate)
    if not candidates:
        return None

    candidates.sort(key=_inventory_grid_score, reverse=True)
    groups: list[list[_InventoryGrid]] = []
    for candidate in candidates:
        matching = next(
            (
                group
                for group in groups
                if _inventory_same_grid(group[0], candidate, geometry.step)
            ),
            None,
        )
        if matching is None:
            groups.append([candidate])
        else:
            matching.append(candidate)
    best_per_group = [max(group, key=_inventory_grid_score) for group in groups]
    best_per_group.sort(key=_inventory_grid_score, reverse=True)
    best = best_per_group[0]
    if len(best_per_group) > 1:
        second = best_per_group[1]
        best_score = _inventory_grid_score(best)
        second_score = _inventory_grid_score(second)
        if second.slot_count == best.slot_count and (
            second_score[1] >= INVENTORY_GRID_AMBIGUITY_RATIO * best_score[1]
        ):
            return None
    return best


def _inventory_trim(mask: np.ndarray) -> np.ndarray | None:
    """Tight boolean bounding box, or ``None`` for an empty mask."""
    rows, columns = np.nonzero(mask)
    if not len(rows):
        return None
    return mask[
        int(rows.min()) : int(rows.max()) + 1,
        int(columns.min()) : int(columns.max()) + 1,
    ]


def _inventory_piece_mask(
    mask: np.ndarray, step: float
) -> np.ndarray | None:
    """Join one piece's fill/outline and return one filled concave contour."""
    kernel_side = max(1, int(round(INVENTORY_CONTENT_CLOSE_SIZE * step)))
    closed = cv2.morphologyEx(
        mask.astype(np.uint8),
        cv2.MORPH_CLOSE,
        np.ones((kernel_side, kernel_side), dtype=np.uint8),
    )
    label_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        closed, connectivity=8
    )
    substantial: list[int] = []
    small_area = 0
    for label in range(1, label_count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area >= INVENTORY_CONTENT_MIN_AREA * step * step:
            substantial.append(label)
        else:
            small_area += area
    if len(substantial) != 1:
        return None
    if small_area > INVENTORY_CONTENT_SMALL_AREA * step * step:
        return None
    primary = (labels == substantial[0]).astype(np.uint8)
    contours, _ = cv2.findContours(primary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if len(contours) != 1:
        return None
    filled = np.zeros(primary.shape, dtype=np.uint8)
    cv2.drawContours(filled, contours, 0, 1, cv2.FILLED)
    # Rasterizing a concave external contour can leave one diagonally attached
    # corner pixel as its own 4-connected component. Drop only such collectively
    # tiny contour remnants; two substantive 4-connected parts remain invalid.
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        filled, connectivity=4
    )
    if count - 1 > 1:
        ordered = sorted(
            range(1, count),
            key=lambda label: int(stats[label, cv2.CC_STAT_AREA]),
            reverse=True,
        )
        discarded_area = sum(
            int(stats[label, cv2.CC_STAT_AREA]) for label in ordered[1:]
        )
        if discarded_area > INVENTORY_CONTENT_SMALL_AREA * step * step:
            return None
        filled = (labels == ordered[0]).astype(np.uint8)
    trimmed = _inventory_trim(filled.astype(bool))
    return None if trimmed is None else trimmed.astype(np.uint8)


def _inventory_divider_counts(profile: np.ndarray, step: float) -> tuple[int, ...]:
    """Axis subdivision counts whose every internal divider is visible."""
    values = np.asarray(profile, dtype=np.float32).reshape(1, -1)
    if values.shape[1] < 2:
        return (1,)
    smooth = cv2.GaussianBlur(
        values, (0, 0), max(0.8, 0.02 * values.shape[1])
    ).reshape(-1)
    gradient = np.abs(np.diff(smooth))
    low = max(0, int(round(0.10 * len(gradient))))
    high = min(len(gradient), int(round(0.90 * len(gradient))))
    interior = gradient[low:high] if high > low else gradient
    median = float(np.median(interior))
    mad = float(np.median(np.abs(interior - median)))
    threshold = max(INVENTORY_DIVIDER_MIN_GRADIENT, median + 3.0 * mad)
    radius = max(1, int(round(0.015 * step)))
    supported = [1]
    for count in range(2, PIECE_MAX_GRID + 1):
        signals: list[float] = []
        for divider in range(1, count):
            position = int(round(divider * values.shape[1] / count))
            start = max(0, position - radius)
            end = min(len(gradient), position + radius)
            signals.append(0.0 if end <= start else float(np.max(gradient[start:end])))
        if signals and min(signals) >= threshold:
            supported.append(count)
    return tuple(supported)


def _inventory_refine_rectangle(
    shape: PieceShape,
    clean: np.ndarray,
    value_crop: np.ndarray,
    step: float,
) -> PieceShape:
    """Resolve integer subdivisions hidden by a solid rectangular silhouette.

    ``reconstruct_piece`` deliberately prefers the coarsest near-best mask, so
    a filled 2x2 square is indistinguishable from one large cell and a slightly
    stretched four-cell line can look like three cells. The UI draws internal
    cell dividers even when the channel mask is solid. For rectangular results
    only, use those dividers to select a finer square grid; concave shapes keep
    the independently reconstructed result unchanged.
    """
    expected_rectangle = tuple(
        (row, column)
        for row in range(shape.rows)
        for column in range(shape.columns)
    )
    if shape.cells != expected_rectangle:
        return shape
    if value_crop.shape != clean.shape:
        value_crop = cv2.resize(
            value_crop,
            (clean.shape[1], clean.shape[0]),
            interpolation=cv2.INTER_AREA,
        )
    height, width = clean.shape
    central_rows = _region_bounds(height, 0.20, 0.80)
    central_columns = _region_bounds(width, 0.20, 0.80)
    column_profile = np.median(
        value_crop[central_rows[0] : central_rows[1], :], axis=0
    )
    row_profile = np.median(
        value_crop[:, central_columns[0] : central_columns[1]], axis=1
    )
    column_counts = _inventory_divider_counts(column_profile, step)
    row_counts = _inventory_divider_counts(row_profile, step)
    candidates: list[tuple[int, float, int, int]] = []
    for rows in row_counts:
        if rows < shape.rows:
            continue
        for columns in column_counts:
            if columns < shape.columns:
                continue
            row_pitch = height / rows
            column_pitch = width / columns
            delta = abs(row_pitch - column_pitch) / max(row_pitch, column_pitch)
            if delta <= INVENTORY_DIVIDER_AXIS_DELTA:
                candidates.append((rows * columns, -delta, rows, columns))
    if not candidates:
        return shape
    _, _, rows, columns = max(candidates)
    if rows * columns <= len(shape.cells):
        return shape
    cells = tuple(
        (row, column) for row in range(rows) for column in range(columns)
    )
    return PieceShape(
        cells=cells,
        rows=int(rows),
        columns=int(columns),
        iou=float(np.count_nonzero(clean) / clean.size),
    )


def extract_inventory(
    image: np.ndarray,
    geometry: BoardGeometry,
    channel_hues: Sequence[float],
) -> InventoryState | None:
    """Recover every right-side inventory slot and its optional piece.

    Invalid arguments raise ``ValueError``. A valid image whose complete slot
    lattice, content channel or piece shape is not unique returns ``None``;
    an independently confirmed inventory in which every slot is empty returns
    a normal :class:`InventoryState` with an empty ``pieces`` tuple.
    """
    _validated_board_image(image, "extract_inventory")
    _validated_geometry(geometry, "extract_inventory")
    hues = _normalized_channel_hues(channel_hues)
    grid = _inventory_locate_grid(image, geometry)
    if grid is None:
        return None

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    channel_masks = _board_channel_masks(hsv, hues)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    candidate_pixels = ((saturation >= MIN_SATURATION) & (value >= MIN_VALUE)) | (
        (saturation >= CELL_DIM_MIN_SATURATION) & (value >= CELL_DIM_MIN_VALUE)
    )
    assigned_pixels = np.logical_or.reduce(channel_masks)
    pieces: list[InventoryPiece] = []
    confidences: list[float] = []
    empty_count = 0
    minimum_area = INVENTORY_CONTENT_MIN_AREA * geometry.step * geometry.step

    for slot_index in range(grid.slot_count):
        left, top = _inventory_grid_position(
            grid.left, grid.top, grid.pitch, grid.columns, slot_index
        )
        right, bottom = left + grid.side, top + grid.side
        if left < 0 or top < 0 or right > image.shape[1] or bottom > image.shape[0]:
            return None
        inner_x = _region_bounds(
            grid.side, INVENTORY_CONTENT_LOW, INVENTORY_CONTENT_HIGH
        )
        inner_y = _region_bounds(
            grid.side, INVENTORY_CONTENT_LOW, INVENTORY_CONTENT_HIGH
        )
        x0, x1 = left + inner_x[0], left + inner_x[1]
        y0, y1 = top + inner_y[0], top + inner_y[1]
        candidate = candidate_pixels[y0:y1, x0:x1]
        unassigned = (candidate & ~assigned_pixels[y0:y1, x0:x1]).astype(np.uint8)
        unassigned_count, _, unassigned_stats, _ = cv2.connectedComponentsWithStats(
            unassigned, connectivity=8
        )
        if any(
            int(unassigned_stats[label, cv2.CC_STAT_AREA]) >= minimum_area
            for label in range(1, unassigned_count)
        ):
            return None
        areas = tuple(
            int(np.count_nonzero(mask[y0:y1, x0:x1])) for mask in channel_masks
        )
        owners = tuple(index for index, area in enumerate(areas) if area >= minimum_area)
        if len(owners) > 1:
            return None
        frame_confidence = min(
            1.0,
            grid.scores[slot_index] / (2.0 * grid.threshold),
        )
        if not owners:
            if np.count_nonzero(candidate) >= minimum_area:
                return None
            empty_count += 1
            content_confidence = max(
                0.0,
                1.0 - float(np.count_nonzero(candidate)) / minimum_area,
            )
            confidences.append(min(frame_confidence, content_confidence))
            continue

        channel = owners[0]
        slot_mask = channel_masks[channel][y0:y1, x0:x1]
        clean = _inventory_piece_mask(slot_mask, geometry.step)
        if clean is None:
            return None
        shape = reconstruct_piece(clean)
        if shape is None:
            return None
        occupied_rows, occupied_columns = np.nonzero(slot_mask)
        value_crop = value[
            y0 + int(occupied_rows.min()) : y0 + int(occupied_rows.max()) + 1,
            x0 + int(occupied_columns.min()) : x0 + int(occupied_columns.max()) + 1,
        ].astype(np.float32)
        shape = _inventory_refine_rectangle(
            shape, clean, value_crop, geometry.step
        )
        pieces.append(
            InventoryPiece(
                slot_index=int(slot_index),
                channel=int(channel),
                cells=tuple((int(row), int(column)) for row, column in shape.cells),
                rows=int(shape.rows),
                columns=int(shape.columns),
                iou=float(shape.iou),
                center_x=float(left + 0.5 * grid.side),
                center_y=float(top + 0.5 * grid.side),
            )
        )
        confidences.append(min(frame_confidence, float(shape.iou)))

    return InventoryState(
        slot_count=int(grid.slot_count),
        empty_count=int(empty_count),
        pieces=tuple(pieces),
        minimum_confidence=float(min(confidences)),
    )
