"""Test doubles for the catalog: an in-process store and a pickleable stub job.

``fake_recognition_job`` is submitted to the real process pool, so it must stay a
module-level function that the spawned child can import. The ``image`` bytes the
test uploads are simply the UTF-8 JSON of the canned recognition result.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.catalog.models import CatalogCandidate, CatalogEntry, CatalogStatus
from app.catalog.store import CatalogUnavailable, Observation
from app.puzzles.balloon.model import BalloonPuzzle


def fake_recognition_job(image: bytes, timeout_seconds: float) -> dict:
    """Stand-in for the OCR job: returns the JSON the test uploaded as the image."""
    return json.loads(image.decode("utf-8"))


class MemoryCatalogStore:
    """Same state transitions as the PostgreSQL store, guarded by one lock."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: dict[str, dict[str, Any]] = {}
        self._digests: set[tuple[str, str]] = set()
        self.records = 0
        self.lookups = 0

    def record(self, observation: Observation) -> tuple[CatalogEntry, bool]:
        with self._lock:
            entry = self._entries.setdefault(
                observation.code, {"status": "provisional", "candidates": {}, "updated_at": _now()}
            )
            if (observation.code, observation.image_sha256) in self._digests:
                return self._view(observation.code), False
            self._digests.add((observation.code, observation.image_sha256))
            candidate = entry["candidates"].get(observation.fingerprint)
            if candidate is None:
                candidate = {
                    "fingerprint": observation.fingerprint,
                    "puzzle": observation.puzzle,
                    "target_total_lift": observation.target_total_lift,
                    "observations": 0,
                    "first_seen": _now(),
                    "last_seen": _now(),
                }
                entry["candidates"][observation.fingerprint] = candidate
            candidate["observations"] += 1
            candidate["last_seen"] = _now()
            entry["status"] = _status(len(entry["candidates"]), candidate["observations"])
            entry["updated_at"] = _now()
            self.records += 1
            return self._view(observation.code), True

    def get(self, code: str) -> CatalogEntry | None:
        with self._lock:
            self.lookups += 1
            return self._view(code) if code in self._entries else None

    def close(self) -> None:
        return None

    def _view(self, code: str) -> CatalogEntry:
        entry = self._entries[code]
        return CatalogEntry(
            code=code,
            status=entry["status"],
            candidates=[
                CatalogCandidate(
                    fingerprint=item["fingerprint"],
                    puzzle=BalloonPuzzle.model_validate(item["puzzle"]),
                    target_total_lift=item["target_total_lift"],
                    observations=item["observations"],
                    first_seen=item["first_seen"],
                    last_seen=item["last_seen"],
                )
                for item in entry["candidates"].values()
            ],
            updated_at=entry["updated_at"],
        )


class UnavailableCatalogStore:
    """Store whose database is down or missing."""

    def record(self, observation: Observation) -> tuple[CatalogEntry, bool]:
        raise CatalogUnavailable("test store is unavailable")

    def get(self, code: str) -> CatalogEntry | None:
        raise CatalogUnavailable("test store is unavailable")

    def close(self) -> None:
        return None


class ExplodingCatalogStore(UnavailableCatalogStore):
    """Store with an unexpected bug, used to prove recognition still survives."""

    def record(self, observation: Observation) -> tuple[CatalogEntry, bool]:
        raise RuntimeError("unexpected catalog bug")

    def get(self, code: str) -> CatalogEntry | None:
        raise RuntimeError("unexpected catalog bug")


def _status(candidates: int, observations: int) -> CatalogStatus:
    if candidates > 1:
        return "disputed"
    return "verified" if observations >= 2 else "provisional"


def _now() -> datetime:
    return datetime.now(timezone.utc)
