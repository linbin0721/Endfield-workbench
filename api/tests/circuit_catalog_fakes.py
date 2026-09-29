"""Thread-safe test doubles for the independent source-circuit catalog."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.catalog.circuit_models import (
    CircuitCatalogCandidate,
    CircuitCatalogEntry,
)
from app.catalog.circuit_store import (
    CircuitObservation,
    CircuitRecordDisposition,
)
from app.catalog.store import CatalogUnavailable
from app.puzzles.circuit.model import CircuitPuzzle


def fake_circuit_recognition_job(
    image: bytes,
    timeout_seconds: float,
    solve_time_limit_seconds: float,
    solve_max_nodes: int,
) -> dict:
    """Spawn-safe OCR stand-in that also exposes the received service limits."""
    payload = json.loads(image.decode("utf-8"))
    payload.setdefault("issues", []).append(
        f"limits={timeout_seconds:g},{solve_time_limit_seconds:g},{solve_max_nodes}"
    )
    return payload


class MemoryCircuitCatalogStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: dict[str, dict[str, Any]] = {}
        self._digests: dict[tuple[str, str], str] = {}
        self.records = 0
        self.lookups = 0
        self.closes = 0

    def record(
        self, observation: CircuitObservation
    ) -> tuple[CircuitCatalogEntry, CircuitRecordDisposition]:
        with self._lock:
            now = _now()
            entry = self._entries.setdefault(
                observation.code,
                {"candidates": {}, "created_at": now, "updated_at": now},
            )
            digest_key = (observation.code, observation.image_sha256)
            prior = self._digests.get(digest_key)
            if prior is not None:
                disposition: CircuitRecordDisposition = (
                    "duplicate"
                    if prior == observation.fingerprint
                    else "digest_mismatch"
                )
                if disposition == "duplicate":
                    self._backfill_palette(entry, observation)
                return self._view(observation.code), disposition

            self._digests[digest_key] = observation.fingerprint
            candidate = entry["candidates"].get(observation.fingerprint)
            if candidate is None:
                candidate = {
                    "fingerprint": observation.fingerprint,
                    "puzzle": copy.deepcopy(observation.puzzle),
                    "display_palette": list(observation.display_palette),
                    "observations": 0,
                    "first_seen": now,
                    "last_seen": now,
                    "id": len(entry["candidates"]) + 1,
                }
                entry["candidates"][observation.fingerprint] = candidate
            else:
                self._backfill_palette(entry, observation)
            candidate["observations"] += 1
            candidate["last_seen"] = now
            entry["updated_at"] = now
            self.records += 1
            return self._view(observation.code), "recorded"

    def get(self, code: str) -> CircuitCatalogEntry | None:
        with self._lock:
            self.lookups += 1
            return self._view(code) if code in self._entries else None

    def close(self) -> None:
        self.closes += 1

    def _view(self, code: str) -> CircuitCatalogEntry:
        entry = self._entries[code]
        items = sorted(
            entry["candidates"].values(),
            key=lambda item: (
                -(item["observations"] >= 2),
                -item["observations"],
                item["first_seen"],
                item["id"],
            ),
        )
        return CircuitCatalogEntry(
            code=code,
            candidates=[
                CircuitCatalogCandidate(
                    fingerprint=item["fingerprint"],
                    puzzle=CircuitPuzzle.model_validate(item["puzzle"]),
                    display_palette=item["display_palette"],
                    status=(
                        "verified"
                        if item["observations"] >= 2
                        else "provisional"
                    ),
                    observations=item["observations"],
                    first_seen=item["first_seen"],
                    last_seen=item["last_seen"],
                )
                for item in items
            ],
            updated_at=entry["updated_at"],
        )

    @staticmethod
    def _backfill_palette(
        entry: dict[str, Any], observation: CircuitObservation
    ) -> bool:
        candidate = entry["candidates"].get(observation.fingerprint)
        if (
            candidate is None
            or candidate["display_palette"]
            or candidate["puzzle"] != observation.puzzle
        ):
            return False
        candidate["display_palette"] = list(observation.display_palette)
        entry["updated_at"] = _now()
        return True


class UnavailableCircuitCatalogStore:
    def record(self, observation: CircuitObservation):  # noqa: ANN201
        raise CatalogUnavailable("test circuit catalog unavailable")

    def get(self, code: str):  # noqa: ANN201
        raise CatalogUnavailable("test circuit catalog unavailable")

    def close(self) -> None:
        return None


class ExplodingCircuitCatalogStore(UnavailableCircuitCatalogStore):
    def record(self, observation: CircuitObservation):  # noqa: ANN201
        raise RuntimeError("unexpected circuit catalog bug")

    def get(self, code: str):  # noqa: ANN201
        raise RuntimeError("unexpected circuit catalog bug")


def _now() -> datetime:
    return datetime.now(timezone.utc)
