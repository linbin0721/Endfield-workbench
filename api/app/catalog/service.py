"""Catalog application service.

The API process calls :meth:`CatalogService.enrich_recognition` after an OCR job
finishes: the disposable OCR subprocess only reports the recognized question
number and draft, and this service decides what may be recorded or reused.
"""

from __future__ import annotations

from typing import Any

from app.catalog.models import CatalogEntry, CatalogMatch
from app.catalog.rules import complete_puzzle, normalize_code, puzzle_fingerprint
from app.catalog.store import CatalogStore, CatalogUnavailable, Observation
from app.puzzles.balloon.model import BalloonPuzzle
from app.puzzles.balloon.recognize import BalloonRecognitionResult
from app.puzzles.balloon.solve import solve_balloon


class CatalogService:
    def __init__(self, store: CatalogStore | None, *, solve_time_limit_seconds: float = 3,
                 solve_max_nodes: int = 300_000):
        self._store = store
        self._solve_time_limit_seconds = solve_time_limit_seconds
        self._solve_max_nodes = solve_max_nodes

    def lookup(self, code: str) -> CatalogEntry | None:
        """Look up one normalized question number; raises ``CatalogUnavailable``."""
        return self._require_store().get(code)

    def enrich_recognition(self, payload: dict[str, Any], image_sha256: str) -> dict[str, Any]:
        """Attach catalog context to a finished recognition result.

        A missing database is reported inside the result. Unexpected programming
        errors are contained by the task manager's finalize guard.
        """
        result = BalloonRecognitionResult.model_validate(payload)
        code = normalize_code(result.question_code)
        if code is None:
            # Still return the normalized model so every recognition result keeps
            # the same shape, including catalog=None.
            return result.model_dump()
        match = CatalogMatch(code=code, code_confidence=result.question_code_confidence)
        try:
            self._fill(match, result, code, image_sha256)
        except CatalogUnavailable:
            match.available = False
            match.issues.append(f"题号目录暂时不可用：本次没有查询或记录题号 {code}，仍按截图识别结果继续。")
        result.catalog = match
        return result.model_dump()

    def close(self) -> None:
        if self._store is not None:
            self._store.close()

    def _require_store(self) -> CatalogStore:
        if self._store is None:
            raise CatalogUnavailable("题号目录未配置")
        return self._store

    def _fill(self, match: CatalogMatch, result: BalloonRecognitionResult,
              code: str, image_sha256: str) -> None:
        store = self._require_store()
        puzzle = complete_puzzle(result)
        if puzzle is None:
            entry = store.get(code)
            if entry is not None:
                match.status = entry.status
                match.candidates = entry.candidates
            if entry is None:
                match.issues.append(f"本次题面不完整，目录中也没有题号 {code} 的完整记录；请补全缺失字段或换一张完整截图。")
            elif len(entry.candidates) == 1:
                match.issues.append(f"本次题面不完整，但题号 {code} 在目录中有唯一完整题面，可直接使用目录题面求解。")
            else:
                match.issues.append(f"本次题面不完整，且题号 {code} 在目录中存在多个不同题面；请核对后选择正确候选。")
            return
        verification = solve_balloon(BalloonPuzzle.model_validate(puzzle),
                                     self._solve_time_limit_seconds, self._solve_max_nodes)
        if verification.outcome != "solved":
            entry = store.get(code)
            if entry is not None:
                match.status = entry.status
                match.candidates = entry.candidates
            reason = "求解超时" if verification.outcome == "timeout" else "没有可行解"
            match.issues.append(
                f"本次识别题面{reason}，未写入题号 {code} 的目录；请换一张清晰截图或使用已有候选。"
            )
            return
        fingerprint = puzzle_fingerprint(puzzle)
        entry, recorded = store.record(Observation(
            code=code,
            image_sha256=image_sha256,
            fingerprint=fingerprint,
            puzzle=puzzle,
            target_total_lift=result.target_total_lift,
        ))
        match.complete = True
        match.recorded = recorded
        match.duplicate = not recorded
        match.matched_fingerprint = (fingerprint
                                     if any(item.fingerprint == fingerprint for item in entry.candidates) else None)
        match.status = entry.status
        match.candidates = entry.candidates
        if not recorded:
            match.issues.append(f"这张截图此前已记录过题号 {code} 的同一题面，本次未重复计数。")
        elif entry.status == "disputed":
            match.issues.append(f"题号 {code} 在目录中已有不同题面：本次题面已另行保留，未覆盖原记录，请核对并选择正确题面。")
        elif entry.status == "verified":
            match.issues.append(f"题号 {code} 的题面已由第二张不同截图确认，目录记录升级为“已确认”。")
        else:
            match.issues.append(f"题号 {code} 的完整题面已记入目录（首次观察，待第二张不同截图确认）。")
