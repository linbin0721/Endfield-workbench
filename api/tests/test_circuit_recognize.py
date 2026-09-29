"""Process-boundary tests for circuit screenshot recognition (EW-006 B2c)."""

from __future__ import annotations

import io
import json
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from app.puzzles.circuit.analyze import DecodedImageAnalysis
from app.puzzles.circuit.model import CircuitPlacement, CircuitSolution
from app.puzzles.circuit.recognize import (
    CircuitRecognitionResult,
    recognize_circuit_job,
)
from app.puzzles.circuit import recognize as recognize_module
from app.puzzles.circuit import recognize_worker as worker


PUZZLE = {
    "rule_version": "line-count-v1",
    "rows": 2,
    "columns": 2,
    "channels": [
        {"index": 0, "row_targets": [2, 0], "column_targets": [1, 1]}
    ],
    "blocked_cells": [],
    "fixed_cells": [],
    "pieces": [
        {
            "channel": 0,
            "cells": [{"row": 0, "column": 0}, {"row": 0, "column": 1}],
        }
    ],
}


def recognized_payload() -> dict:
    return {
        "outcome": "recognized",
        "puzzle": PUZZLE,
        "notation": "digits",
        "question_code": "V40020",
        "question_code_confidence": 0.99,
        "issues": [],
    }


@pytest.mark.parametrize(
    "outcome",
    [
        "incomplete",
        "no_board",
        "already_completed",
        "timeout",
        "invalid_image",
        "failed",
    ],
)
def test_formal_result_accepts_each_nonrecognized_outcome(outcome: str) -> None:
    result = CircuitRecognitionResult(outcome=outcome)  # type: ignore[arg-type]
    assert result.model_dump()["outcome"] == outcome
    assert result.puzzle is None


def test_formal_result_recognized_contract_and_extra_fields() -> None:
    result = CircuitRecognitionResult.model_validate(recognized_payload())
    assert result.puzzle is not None
    assert result.puzzle.rows == result.puzzle.columns == 2

    for field in ("solution", "catalog", "future"):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            CircuitRecognitionResult.model_validate(
                {**recognized_payload(), field: {}}
            )


@pytest.mark.parametrize(
    "payload",
    [
        {"outcome": "recognized", "notation": "digits"},
        {"outcome": "recognized", "puzzle": PUZZLE},
        {"outcome": "incomplete", "puzzle": PUZZLE, "notation": "digits"},
        {"outcome": "no_board", "notation": "bars"},
        {"outcome": "timeout", "notation": "bars"},
    ],
)
def test_formal_result_rejects_puzzle_and_notation_invariant_violations(
    payload: dict,
) -> None:
    with pytest.raises(ValidationError):
        CircuitRecognitionResult.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"outcome": "incomplete", "question_code": "v40020", "question_code_confidence": 0.99},
        {"outcome": "incomplete", "question_code": "V40020"},
        {"outcome": "incomplete", "question_code_confidence": 0.99},
        {"outcome": "incomplete", "question_code": "V40020", "question_code_confidence": -0.1},
        {"outcome": "incomplete", "question_code": "V40020", "question_code_confidence": 1.1},
        {"outcome": "incomplete", "question_code": "V40020", "question_code_confidence": float("nan")},
        {"outcome": "incomplete", "question_code": "V40020", "question_code_confidence": True},
        {"outcome": "incomplete", "question_code": "V40020", "question_code_confidence": "0.99"},
    ],
)
def test_formal_result_rejects_invalid_question_code_pairs(payload: dict) -> None:
    with pytest.raises(ValidationError):
        CircuitRecognitionResult.model_validate(payload)


def image_bytes(
    image: Image.Image, image_format: str, *, orientation: int | None = None
) -> bytes:
    output = io.BytesIO()
    kwargs: dict = {}
    if image_format == "JPEG":
        kwargs.update(quality=100, subsampling=0)
    if orientation is not None:
        exif = Image.Exif()
        exif[274] = orientation
        kwargs["exif"] = exif
    image.save(output, format=image_format, **kwargs)
    return output.getvalue()


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "WEBP"])
def test_decode_supported_formats_as_contiguous_bgr(image_format: str) -> None:
    source = Image.new("RGB", (13, 7), (240, 20, 10))
    decoded = worker.decode_image(image_bytes(source, image_format))

    assert decoded.shape == (7, 13, 3)
    assert decoded.dtype == np.uint8
    assert decoded.flags.c_contiguous
    assert int(decoded[3, 6, 2]) > int(decoded[3, 6, 0])


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"damaged",
        image_bytes(Image.new("RGB", (5, 5)), "GIF"),
        b"x" * (worker.MAX_IMAGE_BYTES + 1),
    ],
)
def test_decode_rejects_empty_corrupt_unsupported_and_oversized_bytes(
    raw: bytes,
) -> None:
    with pytest.raises(ValueError):
        worker.decode_image(raw)


@pytest.mark.parametrize("size", [(0, 10), (10, 0), (5000, 4001)])
def test_decode_rejects_invalid_header_dimensions_before_pixels_are_loaded(
    monkeypatch: pytest.MonkeyPatch, size: tuple[int, int]
) -> None:
    class HeaderOnly:
        format = "PNG"

        def __init__(self) -> None:
            self.size = size

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(worker.Image, "open", lambda stream: HeaderOnly())
    monkeypatch.setattr(
        worker.ImageOps,
        "exif_transpose",
        lambda image: pytest.fail("pixels must not load after an invalid header"),
    )
    with pytest.raises(ValueError):
        worker.decode_image(b"header")


def quadrant_image() -> Image.Image:
    image = Image.new("RGB", (40, 30))
    pixels = np.zeros((30, 40, 3), dtype=np.uint8)
    pixels[:15, :20] = (255, 0, 0)
    pixels[:15, 20:] = (0, 255, 0)
    pixels[15:, :20] = (0, 0, 255)
    pixels[15:, 20:] = (255, 255, 0)
    return Image.fromarray(pixels)


@pytest.mark.parametrize(
    ("orientation", "shape", "top_left_bgr"),
    [
        (1, (30, 40), (0, 0, 255)),
        (3, (30, 40), (0, 255, 255)),
        (6, (40, 30), (255, 0, 0)),
        (8, (40, 30), (0, 255, 0)),
    ],
)
def test_decode_applies_exif_orientation(
    orientation: int, shape: tuple[int, int], top_left_bgr: tuple[int, int, int]
) -> None:
    decoded = worker.decode_image(
        image_bytes(quadrant_image(), "JPEG", orientation=orientation)
    )
    assert decoded.shape[:2] == shape
    assert np.allclose(decoded[5, 5], top_left_bgr, atol=12)


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((20, 10), (20, 10)),
        ((3201, 1000), (3200, 999)),
        ((4000, 2000), (2828, 1414)),
    ],
)
def test_decode_never_enlarges_and_honors_both_working_limits(
    size: tuple[int, int], expected: tuple[int, int]
) -> None:
    raw = image_bytes(Image.new("RGB", size, "black"), "PNG")
    decoded = worker.decode_image(raw)
    height, width = decoded.shape[:2]
    assert (width, height) == expected
    assert max(width, height) <= worker.MAX_WORKING_SIDE
    assert width * height <= worker.MAX_WORKING_PIXELS


def test_worker_constructs_one_ocr_and_drops_internal_solution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple] = []

    class FakeOCR:
        def __init__(self, **kwargs) -> None:
            calls.append(("init", kwargs, self))

    solution = CircuitSolution(
        placements=[
            CircuitPlacement(piece_index=0, row=0, column=0, rotation=0)
        ]
    )

    def fake_analyze(image, ocr, *, time_limit_seconds, max_nodes):
        calls.append(("analyze", image, ocr, time_limit_seconds, max_nodes))
        return DecodedImageAnalysis(
            outcome="recognized",
            notation="digits",
            question_code="V40020",
            question_code_confidence=0.99,
            puzzle=CircuitRecognitionResult.model_validate(
                recognized_payload()
            ).puzzle,
            solution=solution,
        )

    monkeypatch.setattr(worker, "RapidOCR", FakeOCR)
    monkeypatch.setattr(worker, "analyze_decoded_image", fake_analyze)
    image = np.zeros((10, 20, 3), dtype=np.uint8)
    result = worker.recognize_image(
        image, solve_time_limit_seconds=2.5, solve_max_nodes=12345
    )
    payload = result.model_dump()

    assert [entry[0] for entry in calls] == ["init", "analyze"]
    assert calls[0][1] == {
        "intra_op_num_threads": 1,
        "inter_op_num_threads": 1,
    }
    assert calls[1][1] is image
    assert calls[1][2] is calls[0][2]
    assert calls[1][3:] == (2.5, 12345)
    assert payload["outcome"] == "recognized"
    assert "solution" not in payload


class FakeProcess:
    def __init__(
        self,
        stdout: bytes = b"",
        *,
        returncode: int = 0,
        timeout: bool = False,
    ) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.timeout = timeout
        self.calls: list[tuple] = []
        self.stdout_sink = None

    def communicate(self, input=None, timeout=None):
        self.calls.append(("communicate", input, timeout))
        if self.timeout:
            self.timeout = False
            raise subprocess.TimeoutExpired("worker", timeout)
        if self.stdout_sink is not None and self.stdout:
            self.stdout_sink.write(self.stdout)
            self.stdout_sink.flush()
        return None, None

    def kill(self) -> None:
        self.calls.append(("kill",))

    def wait(self) -> int:
        self.calls.append(("wait",))
        return self.returncode


def install_process(
    monkeypatch: pytest.MonkeyPatch, process: FakeProcess
) -> list[tuple]:
    popen_calls: list[tuple] = []

    def fake_popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        process.stdout_sink = kwargs["stdout"]
        return process

    monkeypatch.setattr(recognize_module.subprocess, "Popen", fake_popen)
    return popen_calls


def run_supervisor() -> dict:
    return recognize_circuit_job(b"image", 25.0, 3.0, 300_000)


def test_supervisor_passes_limits_bytes_and_single_thread_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = FakeProcess(json.dumps(recognized_payload()).encode())
    popen_calls = install_process(monkeypatch, process)
    result = run_supervisor()

    assert result["outcome"] == "recognized"
    command, kwargs = popen_calls[0]
    assert command[:3] == [
        recognize_module.sys.executable,
        "-m",
        "app.puzzles.circuit.recognize_worker",
    ]
    assert command[-4:] == [
        "--solve-time-limit-seconds",
        "3.0",
        "--solve-max-nodes",
        "300000",
    ]
    assert kwargs["shell"] is False
    assert kwargs["stdin"] is subprocess.PIPE
    assert kwargs["stdout"] is not subprocess.PIPE
    assert kwargs["stdout"].closed
    assert kwargs["stderr"] is subprocess.DEVNULL
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "ORT_NUM_THREADS"):
        assert kwargs["env"][name] == "1"
    assert process.calls == [("communicate", b"image", 25.0)]


def test_supervisor_kills_and_waits_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = FakeProcess(timeout=True)
    install_process(monkeypatch, process)
    result = run_supervisor()

    assert result["outcome"] == "timeout"
    assert process.calls == [
        ("communicate", b"image", 25.0),
        ("kill",),
        ("communicate", None, None),
        ("wait",),
    ]


@pytest.mark.parametrize(
    ("stdout", "returncode"),
    [
        (json.dumps(recognized_payload()).encode(), 1),
        (b"x" * (256 * 1024 + 1), 0),
        (b"not json", 0),
        (b"\xff", 0),
        (json.dumps({"outcome": "recognized"}).encode(), 0),
        (json.dumps({**recognized_payload(), "solution": {}}).encode(), 0),
        (b"{}{}", 0),
    ],
)
def test_supervisor_converges_process_json_and_model_failures(
    monkeypatch: pytest.MonkeyPatch, stdout: bytes, returncode: int
) -> None:
    install_process(monkeypatch, FakeProcess(stdout, returncode=returncode))
    result = run_supervisor()
    assert result["outcome"] == "failed"
    assert result["puzzle"] is None


def test_worker_main_maps_internal_exception_without_leaking_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdin = SimpleNamespace(buffer=io.BytesIO(b"valid bytes"))
    output = io.BytesIO()
    stdout = SimpleNamespace(buffer=output)
    monkeypatch.setattr(worker.sys, "stdin", stdin)
    monkeypatch.setattr(worker.sys, "stdout", stdout)
    monkeypatch.setattr(
        worker,
        "_arguments",
        lambda: SimpleNamespace(
            solve_time_limit_seconds=3.0, solve_max_nodes=300_000
        ),
    )
    monkeypatch.setattr(
        worker,
        "decode_image",
        lambda raw: np.zeros((5, 5, 3), dtype=np.uint8),
    )

    def fail(*args, **kwargs):
        raise RuntimeError("secret pixels in /private/path")

    monkeypatch.setattr(worker, "recognize_image", fail)
    worker.main()

    raw_output = output.getvalue()
    result = json.loads(raw_output)
    assert result["outcome"] == "failed"
    assert b"secret" not in raw_output
    assert b"/private/path" not in raw_output
    assert raw_output.count(b"{") == 1


def test_worker_main_rejects_more_than_twelve_mib_before_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdin = SimpleNamespace(buffer=io.BytesIO(b"x" * (worker.MAX_IMAGE_BYTES + 1)))
    output = io.BytesIO()
    monkeypatch.setattr(worker.sys, "stdin", stdin)
    monkeypatch.setattr(worker.sys, "stdout", SimpleNamespace(buffer=output))
    monkeypatch.setattr(
        worker,
        "_arguments",
        lambda: SimpleNamespace(
            solve_time_limit_seconds=3.0, solve_max_nodes=300_000
        ),
    )
    monkeypatch.setattr(
        worker,
        "decode_image",
        lambda raw: pytest.fail("oversized input must be rejected before decode"),
    )
    worker.main()
    assert json.loads(output.getvalue())["outcome"] == "invalid_image"


def test_real_worker_boundary_returns_invalid_image() -> None:
    result = recognize_circuit_job(b"not an image", 10.0, 3.0, 300_000)
    assert result["outcome"] == "invalid_image"
