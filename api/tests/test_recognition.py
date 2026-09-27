import asyncio
import io
import os
from pathlib import Path
import time

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import psutil
import pytest

from app.config import Settings
from app.main import create_app
from app.puzzles.balloon.recognize import recognize_balloon_job
from app.upload_limit import LimitedRecognitionUpload, MAX_IMAGE_BYTES, MAX_MULTIPART_BYTES


SAMPLES = Path(os.environ.get("BALLOON_TEST_SAMPLES_DIR", Path(__file__).resolve().parents[2] / "samples" / "private"))
GUIDE = Path(os.environ.get("BALLOON_GUIDE_IMAGE",
                            Path(__file__).resolve().parents[2] / "web" / "public" / "balloon-screenshot-guide.png"))


def _sample(name: str) -> bytes:
    path = SAMPLES / name
    if not path.is_file():
        pytest.skip(f"private recognition sample unavailable: {path}")
    return path.read_bytes()


def _boxes(*items: tuple[str, float]) -> list:
    return [([[0, 0], [10, 0], [10, 5], [0, 5]], text, confidence) for text, confidence in items]


def test_extract_question_code_accepts_only_confident_normalized_codes() -> None:
    from app.puzzles.balloon.recognize_worker import extract_question_code

    assert extract_question_code(_boxes(("WL-A2014", .994))) == ("WL-A2014", .994, True)
    assert extract_question_code(_boxes(("wl - a 2014", .99)))[0] == "WL-A2014"
    assert extract_question_code(_boxes(("WL-A2014", .94))) == (None, None, True)
    assert extract_question_code(_boxes(("WL-A2014", .9), ("WL-A2015", .99))) == ("WL-A2015", .99, True)
    assert extract_question_code(_boxes(("回收需使用全部气球", .99), ("WL-A201", .99))) == (None, None, False)
    assert extract_question_code([]) == (None, None, False)


def test_public_guide_image_reports_its_question_code() -> None:
    if not GUIDE.is_file():
        pytest.skip(f"public guide image unavailable: {GUIDE}")
    result = recognize_balloon_job(GUIDE.read_bytes(), 25)
    assert result["outcome"] == "draft"
    assert result["question_code"] == "WL-A1001"
    assert result["question_code_confidence"] >= .95
    assert (result["rows"], result["columns"]) == (5, 5)
    assert result["target_total_lift"] == 11
    # The catalog is filled by the API process, never by the OCR worker.
    assert result["catalog"] is None


def _synthetic_board_image(outliers: tuple[tuple[int, int], ...] = (),
                           usable: tuple[tuple[int, int], ...] = ((0, 4), (2, 0))) -> np.ndarray:
    """Build a screenshot-like grid without any private material.

    Every cell is a mid-dark tile on a near-black page, so the threshold-45 pass
    sees the whole geometry; ``usable`` cells additionally carry the bright
    outline that only the bright pass sees. ``outliers`` are extra same-size
    tiles at absolute centers outside the board, the way a page overlay can
    repeat a tile size far from the grid.
    """
    import cv2

    tile, step, left, top = 60, 70, 100, 250
    image = np.full((1000, 1000, 3), 5, dtype=np.uint8)
    for row in range(5):
        for column in range(5):
            x, y = left + column * step, top + row * step
            cv2.rectangle(image, (x, y), (x + tile, y + tile), (55, 55, 55), -1)
            if (row, column) in usable:
                cv2.rectangle(image, (x + 1, y + 1), (x + tile - 1, y + tile - 1), (240, 240, 240), 4)
    for cx, cy in outliers:
        cv2.rectangle(image, (cx - tile // 2, cy - tile // 2), (cx + tile // 2, cy + tile // 2), (55, 55, 55), -1)
    return image


@pytest.mark.parametrize("outliers", [
    pytest.param((), id="no_outlier"),
    pytest.param(((130, 800),), id="one_distant_below"),
    pytest.param(((130, 800), (270, 800)), id="two_distant_below"),
    pytest.param(((130, 40),), id="one_distant_above"),
])
def test_regular_rows_ignore_distant_same_size_outliers(outliers: tuple[tuple[int, int], ...]) -> None:
    """A far contour that shares a column must not become a sixth row."""
    from app.puzzles.balloon.recognize_worker import _board

    board = _board(_synthetic_board_image(outliers))
    assert board is not None
    rows, columns, cells, box, _ = board
    assert (rows, columns) == (5, 5)
    # Usable cells still come only from the bright outlines; plain tiles stay unknown.
    assert [index for index, cell in enumerate(cells) if cell == "usable"] == [4, 10]
    assert box == pytest.approx((100, 250, 440, 590), abs=3)


def _variant(original: bytes, kind: str) -> bytes:
    with Image.open(io.BytesIO(original)) as image:
        if kind == "scaled":
            image = image.resize((image.width * 3 // 4, image.height * 3 // 4))
        elif kind == "board_only":
            # The supplied original has the board centered in this proportional region.
            image = image.crop((round(image.width * .383), round(image.height * .219),
                                round(image.width * .612), round(image.height * .719)))
        else:
            raise ValueError(kind)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=95)
        return output.getvalue()


def _done(client: TestClient, task_id: str) -> dict:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        task = client.get(f"/api/v1/tasks/{task_id}").json()
        if task["status"] in ("succeeded", "failed", "cancelled"):
            return task
        time.sleep(.05)
    raise AssertionError("recognition task did not finish")


def test_real_images_and_http_contract() -> None:
    original = _sample("balloon-empty.jpg")
    with TestClient(create_app(Settings(max_workers=1))) as client:
        for name, image in (("balloon-empty.jpg", original),
                            ("balloon-empty-scaled.jpg", _variant(original, "scaled"))):
            response = client.post("/api/v1/puzzles/balloon/recognize",
                                   files={"image": (name, image, "image/jpeg")})
            assert response.status_code == 202
            task = _done(client, response.json()["id"])
            assert task["status"] == "succeeded", task
            result = task["result"]
            assert result["outcome"] == "draft"
            assert (result["rows"], result["columns"]) == (5, 5)
            assert sum(cell == "usable" for cell in result["cells"]) == 16
            assert sum(cell is None for cell in result["cells"]) == 9
            assert [item["lift"] for item in result["inventory"][:3]] == [6, 3, 2]
            assert [item["count"] for item in result["inventory"][:3]] == [3, 3, 3]
            # The fourth row kept both values blank, so the strict derivation
            # completes it as 1x3 (residual 3, lift 3 already used).
            assert (result["inventory"][-1]["lift"], result["inventory"][-1]["count"]) == (1, 3)
            assert any("推导" in issue for issue in result["issues"])
            assert result["target_total_lift"] == 36


def test_board_only_crop() -> None:
    board = recognize_balloon_job(_variant(_sample("balloon-empty.jpg"), "board_only"), 25)
    assert board["outcome"] == "draft"
    assert (board["rows"], board["columns"]) == (5, 5)
    assert sum(cell == "usable" for cell in board["cells"]) == 16
    assert sum(cell is None for cell in board["cells"]) == 9
    assert board["inventory"] == []


def test_completed_board() -> None:
    solved = recognize_balloon_job(_sample("balloon-solved.jpg"), 25)
    assert solved["outcome"] == "no_board"
    assert any("已" in issue and "摆放" in issue for issue in solved["issues"])


@pytest.mark.parametrize(("name", "usable", "inventory", "target"), [
    ("balloon-mobile-1.jpg", {(1, 3), (2, 1), (2, 2), (2, 3), (3, 3)}, [(3, 1), (1, 4)], 7),
    ("balloon-mobile-3.jpg", {(2, column) for column in range(5)}, [(2, 1), (1, 1)], 3),
])
def test_sparse_mobile_boards(name: str, usable: set[tuple[int, int]],
                              inventory: list[tuple[int, int]], target: int) -> None:
    result = recognize_balloon_job(_sample(name), 25)
    assert result["outcome"] == "draft"
    assert (result["rows"], result["columns"]) == (5, 5)
    assert {(index // 5, index % 5) for index, cell in enumerate(result["cells"]) if cell == "usable"} == usable
    assert all(cell is None for cell in result["cells"] if cell != "usable")
    assert [(item["lift"], item["count"]) for item in result["inventory"]] == inventory
    assert result["target_total_lift"] == target


def test_bad_image_and_blank_board() -> None:
    with TestClient(create_app(Settings(max_workers=1))) as client:
        bad = client.post("/api/v1/puzzles/balloon/recognize", files={"image": ("x.png", b"bad", "image/png")})
        assert bad.status_code == 202
        assert _done(client, bad.json()["id"])["result"]["outcome"] == "invalid_image"
        blank = io.BytesIO()
        Image.new("RGB", (600, 600), "black").save(blank, format="PNG")
        response = client.post("/api/v1/puzzles/balloon/recognize",
                               files={"image": ("blank.png", blank.getvalue(), "image/png")})
        assert response.status_code == 202
        assert _done(client, response.json()["id"])["result"]["outcome"] == "no_board"


def test_upload_and_pixel_limits() -> None:
    with TestClient(create_app(Settings(max_workers=1))) as client:
        too_large = client.post("/api/v1/puzzles/balloon/recognize",
                                files={"image": ("x.jpg", b"x" * (MAX_IMAGE_BYTES + 1), "image/jpeg")})
        assert too_large.status_code == 413
        assert too_large.json()["error"]["code"] == "UPLOAD_TOO_LARGE"
        over_body = client.post("/api/v1/puzzles/balloon/recognize", content=b"x" * (MAX_MULTIPART_BYTES + 1),
                                headers={"Content-Type": "multipart/form-data; boundary=abc",
                                         "Origin": "http://localhost:5173"})
        assert over_body.status_code == 413
        assert over_body.headers["access-control-allow-origin"] == "http://localhost:5173"
        oversized_pixels = io.BytesIO()
        Image.new("RGB", (5000, 4200), "black").save(oversized_pixels, format="PNG")
        pixels = client.post("/api/v1/puzzles/balloon/recognize",
                             files={"image": ("large.png", oversized_pixels.getvalue(), "image/png")})
        assert pixels.status_code == 202
        assert _done(client, pixels.json()["id"])["result"]["outcome"] == "invalid_image"


def test_recognition_timeout_releases_worker_slot() -> None:
    with TestClient(create_app(Settings(max_workers=1, max_queued=0, recognize_time_limit_seconds=.01))) as client:
        first = client.post("/api/v1/puzzles/balloon/recognize", files={
            "image": ("x.png", b"bad", "image/png")
        })
        assert first.status_code == 202
        finished = _done(client, first.json()["id"])
        assert finished["status"] == "succeeded"
        assert finished["result"]["outcome"] == "timeout"
        for worker in client.app.state.tasks._pool._processes.values():
            assert psutil.Process(worker.pid).children(recursive=True) == []
        second = client.post("/api/v1/puzzles/balloon/recognize", files={"image": ("x.png", b"bad", "image/png")})
        assert second.status_code == 202
        assert _done(client, second.json()["id"])["result"]["outcome"] == "timeout"


def test_slow_upload_has_bounded_slot_and_deadline(monkeypatch) -> None:
    async def exercise() -> None:
        async def inner(_, receive, send):
            await receive()
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        gate = LimitedRecognitionUpload(inner, max_uploads=1)
        scope = {"type": "http", "method": "POST", "path": "/api/v1/puzzles/balloon/recognize"}
        waiting = asyncio.Event()
        first_messages = []

        async def first_send(message):
            first_messages.append(message)

        async def slow_receive():
            await waiting.wait()
            return {"type": "http.request", "body": b"a", "more_body": False}

        first = asyncio.create_task(gate(scope, slow_receive, first_send))
        await asyncio.sleep(.01)
        busy_messages = []

        async def busy_send(message):
            busy_messages.append(message)

        await gate(scope, slow_receive, busy_send)
        assert busy_messages[0]["status"] == 429
        assert (b"retry-after", b"5") in busy_messages[0]["headers"]
        waiting.set()
        await first
        assert first_messages[0]["status"] == 204

        monkeypatch.setattr("app.upload_limit.MAX_UPLOAD_SECONDS", .01)
        timed_messages = []

        async def timed_send(message):
            timed_messages.append(message)

        await gate(scope, asyncio.Event().wait, timed_send)
        assert timed_messages[0]["status"] == 408

    asyncio.run(exercise())
