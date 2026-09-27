"""Pure catalog rules: code normalization, completeness checks and fingerprints.

No database or OCR imports live here, so the disposable OCR worker can reuse the
same normalization without pulling in the PostgreSQL driver.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from app.puzzles.balloon.model import BalloonPuzzle

if TYPE_CHECKING:
    from app.puzzles.balloon.recognize import BalloonRecognitionResult


RULE_VERSION = "center-torque-v1"
MIN_CODE_CONFIDENCE = 0.95
_CODE_PATTERN = re.compile(r"WL[-\u2010-\u2015]?A(\d{4})")
_CODE_EDGE = "|[](){}<>\u00b7.,:;\"'`"
_CODE_BLANKS = re.compile(r"[\s_\u00a0]+")


def normalize_code(raw: Any) -> str | None:
    """Return ``WL-A1234`` for a recognizable question number, else ``None``.

    Only the canonical shape ``WL-A`` plus exactly four digits is accepted; OCR
    spacing, case and a missing hyphen are normalized away.
    """
    if not isinstance(raw, str):
        return None
    text = _CODE_BLANKS.sub("", raw).upper().strip(_CODE_EDGE)
    match = _CODE_PATTERN.fullmatch(text)
    return f"WL-A{match.group(1)}" if match else None


def puzzle_fingerprint(puzzle: dict) -> str:
    """Stable digest of the puzzle statement, independent of ordering."""
    canonical = {
        "rows": puzzle["rows"],
        "columns": puzzle["columns"],
        "usable_cells": sorted([cell["row"], cell["column"]] for cell in puzzle["usable_cells"]),
        "inventory": sorted([item["lift"], item["count"]] for item in puzzle["inventory"]),
    }
    payload = json.dumps(canonical, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def complete_puzzle(result: BalloonRecognitionResult) -> dict | None:
    """Return a validated puzzle payload only for a complete, consistent draft.

    The recognizer uses ``None`` for cells without a detected white placement
    outline; the existing solve flow treats those cells as unavailable. Catalog
    normalization must use the same rule, otherwise every ordinary board would
    be rejected. Inventory values and the on-screen target must still be fully
    known and mutually consistent before anything is stored.
    """
    if getattr(result, "outcome", None) != "draft":
        return None
    rows, columns, cells = result.rows, result.columns, result.cells
    if not isinstance(rows, int) or not isinstance(columns, int) or not 2 <= rows <= 6 or not 2 <= columns <= 6:
        return None
    if (not isinstance(cells, list) or len(cells) != rows * columns or
            any(cell not in ("usable", "blocked", None) for cell in cells)):
        return None
    usable_cells = [{"row": index // columns, "column": index % columns}
                    for index, cell in enumerate(cells) if cell == "usable"]
    if not usable_cells:
        return None
    inventory: list[dict[str, int]] = []
    for item in result.inventory or []:
        lift, count = getattr(item, "lift", None), getattr(item, "count", None)
        if not isinstance(lift, int) or not isinstance(count, int):
            return None
        inventory.append({"lift": lift, "count": count})
    if not inventory:
        return None
    if not isinstance(result.target_total_lift, int):
        return None
    try:
        puzzle = BalloonPuzzle(rule_version=RULE_VERSION, rows=rows, columns=columns,
                               usable_cells=usable_cells, inventory=inventory)
    except ValidationError:
        return None
    if sum(item.lift * item.count for item in puzzle.inventory) != result.target_total_lift:
        return None
    return puzzle.model_dump()
