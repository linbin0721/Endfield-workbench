"""Pure rules for source-circuit catalog codes and puzzle fingerprints."""

from __future__ import annotations

import hashlib
import itertools
import json
import re
import unicodedata
from typing import Any

from app.puzzles.circuit.model import CircuitPuzzle, ROTATIONS


_DASHES = "-\u058a\u05be\u1400\u1806\u2010\u2011\u2012\u2013\u2014\u2015\u2212\u2e3a\u2e3b\ufe58\ufe63\uff0d"
_TRIANGLES = "△▲▵▴Δ∆"


def normalize_circuit_code(raw: Any) -> str | None:
    """Normalize only decorated ``V#####`` and ``WL####`` circuit codes."""
    if not isinstance(raw, str):
        return None
    normalized = unicodedata.normalize("NFKC", raw)
    token = "".join(
        character
        for character in normalized
        if not character.isspace()
        and not (
            "\ufe00" <= character <= "\ufe0f"
            or "\U000e0100" <= character <= "\U000e01ef"
        )
    )
    match = re.fullmatch(
        rf"[{re.escape(_TRIANGLES)}]?[{re.escape(_DASHES)}]?(V[0-9]{{5}}|WL[0-9]{{4}})",
        token,
    )
    return match.group(1) if match is not None else None


def _normalize_shape(cells: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    minimum_row = min(row for row, _ in cells)
    minimum_column = min(column for _, column in cells)
    return tuple(
        sorted(
            (row - minimum_row, column - minimum_column)
            for row, column in cells
        )
    )


def _canonical_shape(cells: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    current = _normalize_shape(cells)
    orientations: list[tuple[tuple[int, int], ...]] = []
    for rotation in ROTATIONS:
        if rotation:
            current = _normalize_shape(
                [(column, -row) for row, column in current]
            )
        orientations.append(current)
    return min(orientations)


def circuit_puzzle_fingerprint(puzzle: CircuitPuzzle | dict[str, Any]) -> str:
    """Return a stable digest modulo ordering, piece rotation and channel names."""
    validated = CircuitPuzzle.model_validate(puzzle)
    channel_count = len(validated.channels)
    canonical_payloads: list[str] = []

    for permutation in itertools.permutations(range(channel_count)):
        remap = {old: permutation[old] for old in range(channel_count)}
        channels = sorted(
            (
                remap[channel.index],
                tuple(channel.row_targets),
                tuple(channel.column_targets),
            )
            for channel in validated.channels
        )
        fixed = sorted(
            (cell.row, cell.column, remap[cell.channel])
            for cell in validated.fixed_cells
        )
        pieces = sorted(
            (
                remap[piece.channel],
                _canonical_shape(
                    [(cell.row, cell.column) for cell in piece.cells]
                ),
            )
            for piece in validated.pieces
        )
        canonical = {
            "rule_version": validated.rule_version,
            "rows": validated.rows,
            "columns": validated.columns,
            "blocked_cells": sorted(
                (cell.row, cell.column) for cell in validated.blocked_cells
            ),
            "fixed_cells": fixed,
            "channels": channels,
            "pieces": pieces,
        }
        canonical_payloads.append(
            json.dumps(
                canonical,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        )

    payload = min(canonical_payloads)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()
