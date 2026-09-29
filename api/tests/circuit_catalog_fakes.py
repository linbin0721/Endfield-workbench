"""Thread-safe test doubles for the independent source-circuit catalog."""

from __future__ import annotations

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


class MemoryCircuitCatalogStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: dict[str, dict[str, Any]] = {}
        self._digests: dict[tuple[str, str], str] = {}
        self.records = 0
        self.lookups = 0

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
                return self._view(observation.code), disposition

            self._digests[digest_key] = observation.fingerprint
            candidate = entry["candidates"].get(observation.fingerprint)
            if candidate is None:
                candidate = {
                    "fingerprint": observation.fingerprint,
                    "puzzle": observation.puzzle,
                    "observations": 0,
                    "first_seen": now,
                    "last_seen": now,
                    "id": len(entry["candidates"]) + 1,
                }
                entry["candidates"][observation.fingerprint] = candidate
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
        return None

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
