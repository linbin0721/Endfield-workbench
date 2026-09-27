"""Pure inventory-completion rules.

This module never touches image data. It only combines values that OCR already
read with the constraints of the puzzle (target total lift, usable cell count),
and it returns a recovered entry only when exactly one completion is possible.
Zero or multiple candidates keep the field empty, so a draft never guesses.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

MAX_LIFT = 100
MAX_COUNT = 18
TARGET_MIN_CONFIDENCE = 0.85

# ``[升力...6]`` / ``[升力：..3]``. The marker keeps ``4级回收气球`` (a level,
# not a lift) out of the match.
_LIFT_TEXT = re.compile(r"升力[^0-9]{0,6}([0-9]+)")


def lift_from_lift_text(value: str) -> int | None:
    """Return the lift written in a stock text item, or None when ambiguous.

    The game draws an upward arrow after the number and OCR sometimes reads it
    as one more digit (``[升力..11]`` for lift 1). Only an isolated digit run is
    accepted as unambiguous evidence; multi-digit text stays unread instead of
    turning into a wrong lift.
    """
    match = _LIFT_TEXT.search(value)
    if match is None or len(match.group(1)) != 1:
        return None
    lift = int(match.group(1))
    return lift if 1 <= lift <= MAX_LIFT else None


@dataclass(frozen=True)
class MissingEntry:
    """One strictly derivable inventory entry."""

    index: int
    lift: int
    count: int
    message: str


def _known_total_count(entries: Sequence[tuple[int | None, int | None]]) -> int:
    return sum(count for _, count in entries if count is not None)


def _known_total_lift(entries: Sequence[tuple[int | None, int | None]]) -> int:
    return sum(lift * count for lift, count in entries if lift is not None and count is not None)


def _derive_missing_count(entries: Sequence[tuple[int | None, int | None]],
                          target: int, capacity: int) -> tuple[int, int, int] | None:
    """Pattern 1: every lift is known and unique, exactly one count is missing."""
    missing = [index for index, (lift, count) in enumerate(entries) if lift is not None and count is None]
    if len(missing) != 1 or any(lift is None for lift, _ in entries):
        return None
    index = missing[0]
    lift = entries[index][0]
    residual = target - _known_total_lift(entries)
    if residual <= 0 or lift is None or residual % lift != 0:
        return None
    count = residual // lift
    if not 1 <= count <= MAX_COUNT:
        return None
    if _known_total_count(entries) + count > capacity:
        return None
    return index, lift, count


def _derive_missing_lift(entries: Sequence[tuple[int | None, int | None]],
                         target: int, capacity: int, existing_lifts: set[int]) -> tuple[int, int, int] | None:
    """Pattern 2: every count is known and exactly one lift is missing."""
    missing = [index for index, (lift, count) in enumerate(entries) if lift is None and count is not None]
    if len(missing) != 1 or any(count is None for _, count in entries):
        return None
    if any(lift is None for index, (lift, _) in enumerate(entries) if index != missing[0]):
        return None
    if _known_total_count(entries) > capacity:
        return None
    index = missing[0]
    count = entries[index][1]
    residual = target - _known_total_lift(entries)
    if residual <= 0 or count is None or residual % count != 0:
        return None
    lift = residual // count
    if not 1 <= lift <= MAX_LIFT or lift in existing_lifts:
        return None
    return index, lift, count


def _derive_missing_row(entries: Sequence[tuple[int | None, int | None]],
                        target: int, capacity: int, existing_lifts: set[int]) -> tuple[int, int, int] | None:
    """Pattern 3: exactly one row lost both values, every other row is complete."""
    missing = [index for index, (lift, count) in enumerate(entries) if lift is None and count is None]
    if len(missing) != 1:
        return None
    if any((lift is None) != (count is None) for lift, count in entries):
        return None
    index = missing[0]
    remaining = capacity - _known_total_count(entries)
    residual = target - _known_total_lift(entries)
    if remaining < 1 or residual <= 0:
        return None
    candidates = {(lift, count) for lift in range(1, MAX_LIFT + 1) if lift not in existing_lifts
                  for count in range(1, remaining + 1) if lift * count == residual}
    if len(candidates) != 1:
        return None
    lift, count = candidates.pop()
    return index, lift, count


def _message(index: int, lift: int, count: int, target: int, pattern: str) -> str:
    row = index + 1
    if pattern == "count":
        return (f"第 {row} 行库存缺少数量：已按目标总升力 {target} 唯一推导为升力 {lift} × {count} 个，请核对。")
    if pattern == "lift":
        return (f"第 {row} 行库存缺少升力：已按目标总升力 {target} 唯一推导为升力 {lift} × {count} 个，请核对。")
    return (f"第 {row} 行库存的升力和数量均缺失："
            f"已按目标总升力 {target} 唯一推导为升力 {lift} × {count} 个，请核对。")


def derive_missing_entry(entries: Sequence[tuple[int | None, int | None]],
                         target_total_lift: int | None,
                         usable_cells: int,
                         *,
                         target_confidence: float | None,
                         conflict_index: int | None = None) -> MissingEntry | None:
    """Recover one missing inventory entry from an OCR-read target total lift.

    ``entries`` are ``(lift, count)`` pairs in screen order. Derivation is only
    allowed when the target itself was read with at least
    ``TARGET_MIN_CONFIDENCE`` and no total-lift conflict happened in this run
    (``conflict_index``): the count cleared by a conflict must not be filled
    again from the same target that just contradicted it.
    """
    if target_total_lift is None or target_total_lift <= 0:
        return None
    if target_confidence is None or target_confidence < TARGET_MIN_CONFIDENCE:
        return None
    if conflict_index is not None or usable_cells < 1 or not entries:
        return None
    lifts = [lift for lift, _ in entries if lift is not None]
    if len(set(lifts)) != len(lifts):
        return None
    capacity = min(MAX_COUNT, usable_cells)
    found = _derive_missing_lift(entries, target_total_lift, capacity, set(lifts))
    pattern = "lift" if found is not None else ""
    if found is None:
        if _known_total_count(entries) >= capacity:
            return None
        found = _derive_missing_count(entries, target_total_lift, capacity)
        pattern = "count" if found is not None else ""
    if found is None:
        found = _derive_missing_row(entries, target_total_lift, capacity, set(lifts))
        pattern = "row" if found is not None else ""
    if found is None:
        return None
    index, lift, count = found
    if not (1 <= lift <= MAX_LIFT and 1 <= count <= MAX_COUNT):
        return None
    completed = [(lift, count) if position == index else pair for position, pair in enumerate(entries)]
    if sum(item_lift * item_count for item_lift, item_count in completed) != target_total_lift:
        return None
    return MissingEntry(index=index, lift=lift, count=count,
                        message=_message(index, lift, count, target_total_lift, pattern))
