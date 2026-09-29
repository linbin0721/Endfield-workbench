"""API-process catalog validation, lookup and persistence for circuit results."""

from __future__ import annotations

from typing import Any

from app.catalog.circuit_models import CircuitCatalogEntry, CircuitCatalogMatch
from app.catalog.circuit_rules import (
    circuit_puzzle_fingerprint,
    normalize_circuit_code,
)
from app.catalog.circuit_store import (
    CircuitCatalogStore,
    CircuitObservation,
)
from app.catalog.store import CatalogUnavailable
from app.puzzles.circuit.model import CircuitPuzzle
from app.puzzles.circuit.recognize import CircuitRecognitionResult
from app.puzzles.circuit.solve import solve_circuit
from app.puzzles.circuit.verify import validate_solution


class CircuitCatalogService:
    def __init__(
        self,
        store: CircuitCatalogStore | None,
        *,
        solve_time_limit_seconds: float = 3.0,
        solve_max_nodes: int = 300_000,
    ):
        self._store = store
        self._solve_time_limit_seconds = solve_time_limit_seconds
        self._solve_max_nodes = solve_max_nodes

    def lookup(self, code: str) -> CircuitCatalogEntry | None:
        """Look up one canonical code; raises when the store is unavailable."""
        return self._require_store().get(code)

    def enrich_recognition(
        self, payload: dict[str, Any], image_sha256: str
    ) -> dict[str, Any]:
        """Attach catalog context without replacing the recognized statement."""
        result = CircuitRecognitionResult.model_validate(payload)
        code = normalize_circuit_code(result.question_code)
        if code is None:
            return result.model_dump()

        match = CircuitCatalogMatch(
            code=code,
            code_confidence=result.question_code_confidence,
        )
        try:
            self._fill(match, result, code, image_sha256)
        except CatalogUnavailable:
            match.available = False
            match.issues.append(
                f"源石电路题号目录暂时不可用：本次没有查询或记录题号 {code}，仍按截图识别结果继续。"
            )
        result.catalog = match
        return result.model_dump()

    def close(self) -> None:
        if self._store is not None:
            self._store.close()

    def _require_store(self) -> CircuitCatalogStore:
        if self._store is None:
            raise CatalogUnavailable("源石电路题号目录未配置")
        return self._store

    def _fill(
        self,
        match: CircuitCatalogMatch,
        result: CircuitRecognitionResult,
        code: str,
        image_sha256: str,
    ) -> None:
        store = self._require_store()
        if result.outcome != "recognized" or result.puzzle is None:
            entry = store.get(code)
            if entry is not None:
                match.candidates = entry.candidates
            if entry is None:
                match.issues.append(
                    f"本次没有完整题面，目录中也没有题号 {code} 的记录；请上传完整截图。"
                )
            elif len(entry.candidates) == 1:
                match.issues.append(
                    f"本次没有完整题面，题号 {code} 在目录中有一个候选题面，可选择后求解。"
                )
            else:
                match.issues.append(
                    f"本次没有完整题面，题号 {code} 在目录中有多个正常变体；请核对后选择候选。"
                )
            return

        # The worker result is an untrusted process-boundary payload. Rebuild,
        # solve and independently validate it in the API process before storage.
        puzzle = CircuitPuzzle.model_validate(result.puzzle)
        verification = solve_circuit(
            puzzle,
            self._solve_time_limit_seconds,
            self._solve_max_nodes,
        )
        if verification.outcome != "solved" or verification.solution is None:
            self._fill_existing_candidates(match, store, code)
            reason = (
                "复核求解超时"
                if verification.outcome == "timeout"
                else "复核后没有可行解"
            )
            match.issues.append(
                f"本次识别题面{reason}，未写入题号 {code} 的目录；仍保留截图识别结果供排查。"
            )
            return
        try:
            validate_solution(puzzle, verification.solution)
        except ValueError:
            self._fill_existing_candidates(match, store, code)
            match.issues.append(
                f"本次识别题面的复核解答未通过独立校验，未写入题号 {code} 的目录。"
            )
            return

        fingerprint = circuit_puzzle_fingerprint(puzzle)
        entry, disposition = store.record(
            CircuitObservation(
                code=code,
                image_sha256=image_sha256,
                fingerprint=fingerprint,
                puzzle=puzzle.model_dump(),
                display_palette=tuple(result.display_palette),
            )
        )
        match.complete = True
        match.candidates = entry.candidates

        if disposition == "digest_mismatch":
            match.image_digest_mismatch = True
            match.issues.append(
                f"这张图片此前已记录为题号 {code} 的另一指纹；目录保留首次观察，本次结果未改写历史。"
            )
            return

        candidate = next(
            item for item in entry.candidates if item.fingerprint == fingerprint
        )
        match.matched_fingerprint = fingerprint
        match.matched_status = candidate.status
        if disposition == "duplicate":
            match.duplicate = True
            match.issues.append(
                f"这张截图此前已记录过题号 {code} 的同一题面，本次未重复计数。"
            )
        else:
            match.recorded = True
            if candidate.status == "verified":
                match.issues.append(
                    f"题号 {code} 的这个题面变体已由第二张不同截图确认。"
                )
            elif len(entry.candidates) > 1:
                match.issues.append(
                    f"题号 {code} 新增一个正常题面变体（首次观察，待第二张不同截图确认）。"
                )
            else:
                match.issues.append(
                    f"题号 {code} 的完整题面已记入目录（首次观察，待第二张不同截图确认）。"
                )

    @staticmethod
    def _fill_existing_candidates(
        match: CircuitCatalogMatch,
        store: CircuitCatalogStore,
        code: str,
    ) -> None:
        entry = store.get(code)
        if entry is not None:
            match.candidates = entry.candidates
