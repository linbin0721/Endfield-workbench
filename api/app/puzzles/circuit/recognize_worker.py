"""Disposable circuit OCR worker. Raw image bytes are read only from stdin."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import sys

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from rapidocr_onnxruntime import RapidOCR

from app.puzzles.circuit.analyze import DecodedImageAnalysis, analyze_decoded_image
from app.puzzles.circuit.recognize import CircuitRecognitionResult


MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_SOURCE_PIXELS = 20_000_000
MAX_WORKING_SIDE = 3_200
MAX_WORKING_PIXELS = 4_000_000
SUPPORTED_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})


class _InvalidImage(ValueError):
    """Expected user-image failure that maps to ``invalid_image``."""


def _working_size(width: int, height: int) -> tuple[int, int]:
    scale = min(
        1.0,
        MAX_WORKING_SIDE / max(width, height),
        math.sqrt(MAX_WORKING_PIXELS / (width * height)),
    )
    if scale >= 1.0:
        return width, height
    resized_width = max(1, int(math.floor(width * scale)))
    resized_height = max(1, int(math.floor(height * scale)))
    while (
        resized_width > MAX_WORKING_SIDE
        or resized_height > MAX_WORKING_SIDE
        or resized_width * resized_height > MAX_WORKING_PIXELS
    ):
        if resized_width >= resized_height and resized_width > 1:
            resized_width -= 1
        elif resized_height > 1:
            resized_height -= 1
        else:
            break
    return resized_width, resized_height


def decode_image(raw: bytes) -> np.ndarray:
    """Decode, orient and bound one supported image as contiguous uint8 BGR."""
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise _InvalidImage("empty or oversized image")
    try:
        with Image.open(io.BytesIO(raw)) as source:
            width, height = source.size
            if (
                source.format not in SUPPORTED_FORMATS
                or width <= 0
                or height <= 0
                or width * height > MAX_SOURCE_PIXELS
            ):
                raise _InvalidImage("unsupported image header")
            oriented = ImageOps.exif_transpose(source)
            rgb = oriented.convert("RGB")
            target_size = _working_size(*rgb.size)
            if target_size != rgb.size:
                rgb = rgb.resize(target_size, Image.Resampling.LANCZOS)
            rgb_array = np.asarray(rgb, dtype=np.uint8)
            bgr = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
            return np.ascontiguousarray(bgr, dtype=np.uint8)
    except _InvalidImage:
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        ValueError,
        cv2.error,
    ) as exc:
        raise _InvalidImage("image decode failed") from exc


def result_from_analysis(analysis: DecodedImageAnalysis) -> CircuitRecognitionResult:
    """Drop the internal solution while preserving the formal recognition data."""
    return CircuitRecognitionResult(
        outcome=analysis.outcome,
        puzzle=analysis.puzzle,
        notation=analysis.notation,
        question_code=analysis.question_code,
        question_code_confidence=analysis.question_code_confidence,
        issues=list(analysis.issues),
    )


def recognize_image(
    image: np.ndarray, *, solve_time_limit_seconds: float, solve_max_nodes: int
) -> CircuitRecognitionResult:
    """Construct exactly one OCR engine and analyze one decoded image."""
    with contextlib.redirect_stdout(sys.stderr):
        ocr = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
        analysis = analyze_decoded_image(
            image,
            ocr,
            time_limit_seconds=solve_time_limit_seconds,
            max_nodes=solve_max_nodes,
        )
    return result_from_analysis(analysis)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--solve-time-limit-seconds", required=True, type=float)
    parser.add_argument("--solve-max-nodes", required=True, type=int)
    args = parser.parse_args()
    if (
        not math.isfinite(args.solve_time_limit_seconds)
        or args.solve_time_limit_seconds <= 0
        or args.solve_max_nodes <= 0
    ):
        raise ValueError("invalid solver limits")
    return args


def _invalid_image(issue: str) -> CircuitRecognitionResult:
    return CircuitRecognitionResult(outcome="invalid_image", issues=[issue])


def _failed() -> CircuitRecognitionResult:
    return CircuitRecognitionResult(
        outcome="failed", issues=["识别服务处理失败，请稍后重试。"]
    )


def main() -> None:
    cv2.setNumThreads(1)
    try:
        args = _arguments()
        raw = sys.stdin.buffer.read(MAX_IMAGE_BYTES + 1)
        if len(raw) > MAX_IMAGE_BYTES:
            result = _invalid_image("图片不能超过 12 MiB。")
        else:
            try:
                image = decode_image(raw)
            except _InvalidImage:
                result = _invalid_image(
                    "图片为空、无法解码、格式不支持或超过 2000 万像素。"
                )
            else:
                try:
                    result = recognize_image(
                        image,
                        solve_time_limit_seconds=args.solve_time_limit_seconds,
                        solve_max_nodes=args.solve_max_nodes,
                    )
                except Exception:
                    result = _failed()
    except Exception:
        result = _failed()

    payload = json.dumps(
        result.model_dump(mode="json"), ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
    sys.stdout.buffer.write(payload)


if __name__ == "__main__":
    main()
