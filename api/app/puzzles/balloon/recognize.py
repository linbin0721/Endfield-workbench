"""Bounded image recognition task and its editable response contract."""

import json
import os
import subprocess
import sys
from typing import Literal

from pydantic import BaseModel, Field


class InventoryDraft(BaseModel):
    lift: int | None = None
    count: int | None = None


class BalloonRecognitionResult(BaseModel):
    outcome: Literal["draft", "no_board", "timeout", "invalid_image", "failed"]
    rows: int | None = None
    columns: int | None = None
    cells: list[Literal["usable", "blocked"] | None] | None = None
    inventory: list[InventoryDraft] = Field(default_factory=list)
    target_total_lift: int | None = None
    issues: list[str] = Field(default_factory=list)


def recognize_balloon_job(image: bytes, timeout_seconds: float) -> dict:
    """A pool worker supervises a disposable OCR process and keeps its slot until exit."""
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "ORT_NUM_THREADS": "1"})
    try:
        process = subprocess.run(
            [sys.executable, "-m", "app.puzzles.balloon.recognize_worker"],
            input=image, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=timeout_seconds, shell=False, check=False, env=env,
        )
    except subprocess.TimeoutExpired:
        return BalloonRecognitionResult(outcome="timeout", issues=["图片识别超时，请换用清晰完整截图或手动输入题面。"]).model_dump()
    if process.returncode != 0 or len(process.stdout) > 256_000:
        return BalloonRecognitionResult(outcome="failed", issues=["识别服务处理失败，请稍后重试或手动输入题面。"]).model_dump()
    try:
        return BalloonRecognitionResult.model_validate(json.loads(process.stdout)).model_dump()
    except (ValueError, UnicodeError):
        return BalloonRecognitionResult(outcome="failed", issues=["识别服务返回无效结果，请稍后重试或手动输入题面。"]).model_dump()
