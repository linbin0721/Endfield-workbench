"""Deterministic math primitives for circuit screenshot recognition.

The recognizer extracts observations (short-bar centers, hue samples, ...)
outside this module; the helpers here turn a screenshot into saturated
components, fit the integer line lattice, decide whether the two axis pitches
match, cluster hues on the circular OpenCV 0..179 scale, summarize a single
board cell as immutable evidence with a fixed classification, and rebuild one
already segmented inventory piece mask as an immutable square grid shape. Every
function is pure and keeps no reference to the source image or to any crop.
"""

from __future__ import annotations

import math
import numbers
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
