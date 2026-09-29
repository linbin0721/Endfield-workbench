"""Formal circuit recognition response and disposable-worker supervisor."""

from __future__ import annotations

import json
import math
import numbers
import os
import subprocess
import sys
import tempfile
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.catalog.circuit_models import CircuitCatalogMatch
from app.catalog.circuit_rules import normalize_circuit_code
from app.puzzles.circuit.model import CircuitPuzzle
from app.puzzles.circuit.presentation import (
    CircuitDisplayColor,
    palette_matches_channels,
)


RecognitionOutcome = Literal[
    "recognized",
    "incomplete",
    "no_board",
    "already_completed",
    "timeout",
    "invalid_image",
    "failed",
]
RecognitionNotation = Literal["bars", "digits", "roman", "mixed"]

_OUTPUT_LIMIT_BYTES = 256 * 1024
_THREAD_ENVIRONMENT = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "ORT_NUM_THREADS": "1",
}


class CircuitRecognitionResult(BaseModel):
    """Serializable result returned across the recognition process boundary."""

    model_config = ConfigDict(extra="forbid")

    outcome: RecognitionOutcome
    puzzle: CircuitPuzzle | None = None
    display_palette: list[CircuitDisplayColor] = Field(default_factory=list)
    notation: RecognitionNotation | None = None
    question_code: str | None = None
    question_code_confidence: float | None = None
    catalog: CircuitCatalogMatch | None = None
    issues: list[str] = Field(default_factory=list)

    @field_validator("question_code_confidence", mode="before")
    @classmethod
    def reject_boolean_confidence(cls, value: object) -> object:
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, numbers.Real)
        ):
            raise ValueError("question code confidence must be numeric")
        return value

    @model_validator(mode="after")
    def validate_result(self) -> "CircuitRecognitionResult":
        if self.outcome == "recognized":
            if self.puzzle is None:
                raise ValueError("a recognized result must carry a puzzle")
            if self.notation is None:
                raise ValueError("a recognized result must carry notation")
            if not palette_matches_channels(
                self.display_palette,
                range(len(self.puzzle.channels)),
            ):
                raise ValueError(
                    "a recognized result palette must match puzzle channels"
                )
        elif self.puzzle is not None or self.display_palette:
            raise ValueError(
                "only a recognized result may carry a puzzle or display palette"
            )

        if self.outcome == "no_board" and self.notation is not None:
            raise ValueError("a no_board result cannot carry notation")
        if self.outcome in {"timeout", "invalid_image", "failed"} and self.notation is not None:
            raise ValueError("an infrastructure result cannot carry notation")

        if self.question_code is None:
            if self.question_code_confidence is not None:
                raise ValueError("a missing question code cannot have confidence")
        else:
            if normalize_circuit_code(self.question_code) != self.question_code:
                raise ValueError("a question code must already be canonical")
            confidence = self.question_code_confidence
            if (
                isinstance(confidence, bool)
                or not isinstance(confidence, numbers.Real)
                or not math.isfinite(float(confidence))
                or not 0.0 <= float(confidence) <= 1.0
            ):
                raise ValueError("question code confidence must be finite in 0..1")
        return self


def _failure(issue: str) -> dict:
    return CircuitRecognitionResult(outcome="failed", issues=[issue]).model_dump()


def recognize_circuit_job(
    image_bytes: bytes,
    timeout_seconds: float,
    solve_time_limit_seconds: float,
    solve_max_nodes: int,
) -> dict:
    """Supervise one disposable circuit OCR worker and validate its JSON."""
    if (
        not isinstance(image_bytes, bytes)
        or isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, numbers.Real)
        or not math.isfinite(float(timeout_seconds))
        or timeout_seconds <= 0
        or isinstance(solve_time_limit_seconds, bool)
        or not isinstance(solve_time_limit_seconds, numbers.Real)
        or not math.isfinite(float(solve_time_limit_seconds))
        or solve_time_limit_seconds <= 0
        or isinstance(solve_max_nodes, bool)
        or not isinstance(solve_max_nodes, int)
        or solve_max_nodes <= 0
    ):
        return _failure("识别服务参数无效，请稍后重试。")

    env = os.environ.copy()
    env.update(_THREAD_ENVIRONMENT)
    command = [
        sys.executable,
        "-m",
        "app.puzzles.circuit.recognize_worker",
        "--solve-time-limit-seconds",
        str(float(solve_time_limit_seconds)),
        "--solve-max-nodes",
        str(solve_max_nodes),
    ]
    try:
        # A file-backed sink prevents a faulty child from making the parent
        # retain unbounded stdout in memory. Only the accepted limit plus one
        # byte is ever read back for validation.
        with tempfile.TemporaryFile() as stdout_sink:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=stdout_sink,
                stderr=subprocess.DEVNULL,
                shell=False,
                env=env,
            )
            try:
                process.communicate(
                    input=image_bytes, timeout=float(timeout_seconds)
                )
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                process.wait()
                return CircuitRecognitionResult(
                    outcome="timeout",
                    issues=["图片识别超时，请换用清晰完整截图后重试。"],
                ).model_dump()
            stdout_sink.seek(0)
            stdout = stdout_sink.read(_OUTPUT_LIMIT_BYTES + 1)
    except (OSError, ValueError, subprocess.SubprocessError):
        return _failure("识别服务处理失败，请稍后重试。")

    if process.returncode != 0 or len(stdout) > _OUTPUT_LIMIT_BYTES:
        return _failure("识别服务处理失败，请稍后重试。")
    try:
        payload = json.loads(stdout)
        return CircuitRecognitionResult.model_validate(payload).model_dump()
    except (TypeError, ValueError, UnicodeError):
        return _failure("识别服务返回无效结果，请稍后重试。")
