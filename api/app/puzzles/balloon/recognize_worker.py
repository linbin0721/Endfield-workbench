"""Disposable, resource-bounded OCR process. Input is image bytes on stdin."""

import io
import json
import re
import sys

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError
from rapidocr_onnxruntime import RapidOCR

from app.catalog.rules import MIN_CODE_CONFIDENCE, normalize_code
from app.puzzles.balloon.derive import derive_missing_entry, lift_from_lift_text
from app.puzzles.balloon.recognize import BalloonRecognitionResult, InventoryDraft


MAX_PIXELS = 20_000_000
WORKING_PIXELS = 4_000_000
MAX_SIDE = 3200
# Question-number search areas, relative to the detected board box.
CODE_REGIONS = (
    (-1.80, -0.35, -0.85, 0.45),
    (-2.30, -0.80, -0.02, 0.80),
)
CODE_FULL_FRAME_MAX_SIDE = 1600


def _rectangles(image: np.ndarray, threshold: int = 130) -> list[tuple[float, float, float]]:
    height, width = image.shape[:2]
    minimum = min(height, width)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    found: list[tuple[float, float, float]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if not (.035 * minimum <= w <= .17 * minimum and .035 * minimum <= h <= .17 * minimum):
            continue
        if not .83 <= w / h <= 1.17:
            continue
        size = (w + h) / 2
        cx, cy = x + w / 2, y + h / 2
        if not any(abs(cx - px) < .16 * size and abs(cy - py) < .16 * size and abs(size - ps) < .2 * size
                   for px, py, ps in found):
            found.append((cx, cy, size))
    return found


def _axis_positions(values: list[float], tolerance: float) -> list[float]:
    groups: list[list[float]] = []
    for value in sorted(values):
        if groups and value - np.mean(groups[-1]) < tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [float(np.mean(group)) for group in groups]


def _axis_runs(values: list[float], step: float) -> list[list[float]]:
    """Split axis positions into maximal runs whose gaps repeat the column step.

    A same-size contour elsewhere on the page (for example a panel overlay below
    the board) can share a board column and join the related rectangles. Treating
    that lone position as another row rejects an otherwise regular grid, so each
    candidate keeps only consecutive positions that are spaced like its columns.
    """
    runs: list[list[float]] = []
    for value in values:
        if runs and .85 * step <= value - runs[-1][-1] <= 1.15 * step:
            runs[-1].append(value)
        else:
            runs.append([value])
    return [run for run in runs if len(run) >= 2]


def _board(image: np.ndarray) -> tuple[int, int, list[str | None], tuple[float, float, float, float], float] | None:
    # Dark, filled tiles establish the full grid even when the usable white outlines
    # occupy only one row. A dark contour alone is not proof that a cell is blocked.
    rects = _rectangles(image, threshold=45)
    outlined = _rectangles(image)
    best = None
    best_score = (0, 0)
    for cx, cy, size in rects:
        row = sorted((r for r in rects if abs(r[1] - cy) < .18 * size and abs(r[2] - size) < .16 * size), key=lambda r: r[0])
        for start in range(len(row)):
            run = [row[start]]
            for item in row[start + 1:]:
                gap = item[0] - run[-1][0]
                if .98 * size <= gap <= 1.38 * size:
                    run.append(item)
                elif gap > 1.38 * size:
                    break
            if len(run) < 3 or len(run) > 6:
                continue
            xs = [r[0] for r in run]
            step = float(np.median(np.diff(xs)))
            related = [r for r in rects if abs(r[2] - size) < .16 * size and
                       any(abs(r[0] - x) < .2 * size for x in xs)]
            row_positions = _axis_positions([r[1] for r in related], .2 * size)
            for ys in _axis_runs(row_positions, step):
                if len(ys) > 6:
                    continue
                aligned = sum(any(abs(r[0] - x) < .2 * size and abs(r[1] - y) < .2 * size for r in related)
                              for y in ys for x in xs)
                score = (aligned, len(run) * len(ys))
                if score > best_score:
                    best_score = score
                    best = (xs, ys, related, size)
    if best is None or best_score[0] < 6:
        return None
    xs, ys, related, size = best
    cells = ["usable" if any(abs(r[0] - x) < .2 * size and abs(r[1] - y) < .2 * size for r in outlined)
             else None for y in ys for x in xs]
    return len(ys), len(xs), cells, (xs[0] - size / 2, ys[0] - size / 2,
                                      xs[-1] + size / 2, ys[-1] + size / 2), size


def _crop(image: np.ndarray, x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
    h, w = image.shape[:2]
    return image[max(0, int(y1)):min(h, int(y2)), max(0, int(x1)):min(w, int(x2))]


def _digit(ocr: RapidOCR, image: np.ndarray, maximum: int, minimum_confidence: float) -> tuple[int | None, float]:
    if image.size == 0:
        return None, 0.0
    result, _ = ocr.text_rec([image])
    if not result:
        return None, 0.0
    text, confidence = result[0]
    text = text.strip()
    if re.fullmatch(r"\d{1,3}", text) and 0 < int(text) <= maximum and confidence >= minimum_confidence:
        return int(text), float(confidence)
    return None, float(confidence)


def _badge_digit(ocr: RapidOCR, image: np.ndarray) -> tuple[int | None, float]:
    if image.size == 0:
        return None, 0.0
    enlarged = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    results, _ = ocr(enlarged)
    digits = [(int(value), float(confidence)) for _, value, confidence in results or []
              if re.fullmatch(r"\d{1,2}", value) and 1 <= int(value) <= 18]
    if not digits:
        return None, 0.0
    value, confidence = max(digits, key=lambda item: item[1])
    return (value if confidence >= .985 else None), confidence


def extract_question_code(results: list | None) -> tuple[str | None, float | None, bool]:
    """Return (code, confidence, saw_code_like_text) from OCR text boxes."""
    best: tuple[str, float] | None = None
    code_like = False
    for _, value, confidence in results or []:
        code = normalize_code(value)
        if code is None:
            continue
        code_like = True
        if float(confidence) >= MIN_CODE_CONFIDENCE and (best is None or float(confidence) > best[1]):
            best = (code, float(confidence))
    if best is None:
        return None, None, code_like
    return best[0], best[1], True


def _question_code(ocr: RapidOCR, image: np.ndarray,
                   box: tuple[float, float, float, float]) -> tuple[str | None, float | None, bool]:
    """Read the optional ``WL-A####`` question number near the board.

    The number sits in the left panel of the game screen, so the first two
    attempts stay proportional to the detected board; a downscaled full frame is
    the fallback for screens whose panels do not scale with the board.
    """
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    frame_height, frame_width = image.shape[:2]
    low_confidence = False
    regions = [(left + x1 * width, top + y1 * height, left + x2 * width, top + y2 * height)
               for x1, y1, x2, y2 in CODE_REGIONS]
    for x1, y1, x2, y2 in regions:
        crop = _crop(image, x1, y1, x2, y2)
        if crop.size == 0:
            continue
        results, _ = ocr(crop)
        code, confidence, code_like = extract_question_code(results)
        if code is not None:
            return code, confidence, True
        low_confidence = low_confidence or code_like
    scale = min(1.0, CODE_FULL_FRAME_MAX_SIDE / max(frame_width, frame_height))
    frame = image if scale == 1 else cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    code, confidence, code_like = extract_question_code(ocr(frame)[0])
    if code is not None:
        return code, confidence, True
    return None, None, low_confidence or code_like


def _recognize(image: np.ndarray) -> BalloonRecognitionResult:
    board = _board(image)
    if board is None:
        height, width = image.shape[:2]
        progress_region = _crop(image, .25 * width, .12 * height, .75 * width, .40 * height)
        if progress_region.size:
            progress, _ = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)(progress_region)
            for _, value, confidence in progress or []:
                match = re.fullmatch(r"\s*(\d{1,4})\s*/\s*(\d{1,4})\s*", value)
                if match and confidence > .85 and int(match.group(1)) > 0:
                    return BalloonRecognitionResult(outcome="no_board", issues=["画面显示已有气球摆放，请在游戏中重置题目后重新截图。"])
        return BalloonRecognitionResult(outcome="no_board", issues=["未能从图片中定位规则棋盘，请上传清晰、完整且未摆放的截图，或手动输入题面。"])
    rows, columns, cells, (left, top, right, bottom), size = board
    issues: list[str] = []
    if any(cell is None for cell in cells):
        issues.append("未检测到外框的地块仍待确认，请逐格核对禁用格与可放置格。")
    ocr = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
    question_code, code_confidence, code_seen = _question_code(ocr, image, (left, top, right, bottom))
    if question_code is None and code_seen:
        issues.append("画面中的题号文字置信度不足 0.95，本次未用于目录；如需按题号复用请换一张更清晰的截图。")
    board_width, board_height = right - left, bottom - top
    header = _crop(image, left + .2 * board_width, top - .3 * board_height,
                   right - .2 * board_width, top)
    current = target = None
    target_confidence: float | None = None
    if header.size:
        text, _ = ocr(header)
        for item in text or []:
            match = re.search(r"(\d{1,3})\s*/\s*(\d{1,4})", item[1])
            if match:
                current, target = int(match.group(1)), int(match.group(2))
                target_confidence = float(item[2])
                break
    if current is not None and current != 0:
        return BalloonRecognitionResult(outcome="no_board", issues=["画面显示已有气球摆放，请在游戏中重置题目后重新截图。"])
    if current is None:
        issues.append("无法确认画面是否已重置；请检查棋盘上没有已摆放气球。")

    stock_left = right + .30 * board_width
    # Keep the lift number at the far right of the text row in frame. On
    # 2560x1440 captures, 1.55 board widths clipped it while the visible
    # inventory itself was complete.
    stock_right = right + 1.70 * board_width
    stock_top = top - .06 * board_height
    stock_bottom = bottom + .18 * board_height
    stock = _crop(image, stock_left, stock_top, stock_right, stock_bottom)
    if stock.size == 0 or stock.shape[1] < .4 * board_width:
        issues.append("图片中未找到完整库存区域，请手动填写升力和数量。")
        return BalloonRecognitionResult(outcome="draft", rows=rows, columns=columns, cells=cells,
                                        target_total_lift=target, question_code=question_code,
                                        question_code_confidence=code_confidence, issues=issues)
    text, _ = ocr(stock)
    labels: list[tuple[float, int, float]] = []
    details: list[tuple[float, float, int | None]] = []
    for box, value, confidence in text or []:
        x = float(np.mean([point[0] for point in box]))
        y = float(np.mean([point[1] for point in box]))
        match = re.match(r"\s*([1-9])\D", value)
        if x > .43 * stock.shape[1] and match and confidence > .8:
            labels.append((y + max(0, stock_top), int(match.group(1)),
                           min(point[0] for point in box) + max(0, stock_left)))
        if "升力" in value and re.search(r"\d", value) and confidence >= .8:
            details.append((y + max(0, stock_top), max(point[0] for point in box) + max(0, stock_left),
                            lift_from_lift_text(value)))
    labels.sort()
    labels = [label for index, label in enumerate(labels) if index == 0 or label[0] - labels[index - 1][0] > .6 * size]
    if not labels:
        issues.append("未能可靠定位库存行，请手动填写升力和数量。")
        return BalloonRecognitionResult(outcome="draft", rows=rows, columns=columns, cells=cells,
                                        target_total_lift=target, question_code=question_code,
                                        question_code_confidence=code_confidence, issues=issues)
    stock_rects = [r for r in _rectangles(image) if stock_left < r[0] < stock_left + .5 * board_width and
                   stock_top < r[1] < stock_bottom and abs(r[2] - size) < .2 * size]
    if stock_rects:
        circle_x = float(np.median([r[0] for r in stock_rects]))
    else:
        # Circular inventory art has no square contour. Its center is stable
        # relative to the left edge of the adjacent "N级回收气球" label.
        circle_x = float(np.median([label_left for _, _, label_left in labels])) - 1.05 * size
        issues.append("库存图标位置不清晰，识别的升力和数量需要逐项核对。")
    inventory: list[InventoryDraft] = []
    count_confidences: list[float] = []
    for row, (label_y, _, _) in enumerate(labels[:8], start=1):
        circle_y = label_y + .14 * size
        lift, _ = _digit(ocr, _crop(image, circle_x - .27 * size, circle_y - .27 * size,
                                   circle_x + .27 * size, circle_y + .27 * size), 100, .8)
        count, confidence = _badge_digit(ocr, _crop(image, circle_x + .30 * size, circle_y + .20 * size,
                                                    circle_x + .90 * size, circle_y + .90 * size))
        detail = next(((y, right_x, text_lift) for y, right_x, text_lift in details
                       if abs(y - (label_y + .50 * size)) < .25 * size), None)
        detail_lift = text_lift = None
        if detail is not None:
            detail_y, detail_right, text_lift = detail
            detail_lift, _ = _digit(ocr, _crop(image, detail_right - .515 * size, detail_y - .24 * size,
                                              detail_right - .223 * size, detail_y + .24 * size), 100, .85)
        conflict = False
        if lift is not None and detail_lift is not None and lift != detail_lift:
            lift = None
            conflict = True
            issues.append(f"第 {row} 行库存图标与升力文字不一致；冲突的升力已留空，请手动核对。")
        elif lift is None and detail_lift is not None:
            tight_lift, _ = _digit(ocr, _crop(image, circle_x - .24 * size, circle_y - .19 * size,
                                             circle_x + .14 * size, circle_y + .19 * size), 100, .8)
            if tight_lift == detail_lift:
                lift = detail_lift
        # The "升力 N" text is independent evidence: it fills a lift that the
        # icon crops could not read, but it never overrides the icon silently.
        if text_lift is not None and not conflict:
            if lift is None and (detail_lift is None or detail_lift == text_lift):
                lift = text_lift
            elif lift is not None and lift != text_lift:
                lift = None
                issues.append(f"第 {row} 行库存升力文字与图标不一致；冲突的升力已留空，请手动核对。")
        inventory.append(InventoryDraft(lift=lift, count=count))
        count_confidences.append(confidence)
    conflict_index = None
    if target is not None and inventory and all(item.lift is not None and item.count is not None for item in inventory):
        if sum(item.lift * item.count for item in inventory) != target:
            least = min(range(len(inventory)), key=lambda i: count_confidences[i])
            inventory[least].count = None
            conflict_index = least
            issues.append("库存数量与画面目标总升力不符；置信度最低的数量已留空，请核对所有库存。")
    derived = derive_missing_entry([(item.lift, item.count) for item in inventory], target,
                                   sum(cell == "usable" for cell in cells),
                                   target_confidence=target_confidence, conflict_index=conflict_index)
    if derived is not None:
        inventory[derived.index] = InventoryDraft(lift=derived.lift, count=derived.count)
        issues.append(derived.message)
    if any(item.lift is None or item.count is None for item in inventory):
        issues.append("部分库存数字或徽标不清晰，空白字段需手动确认；目标总升力不足以唯一确定这些字段。")
    if not inventory:
        issues.append("图片中未识别到库存，请手动填写。")
    return BalloonRecognitionResult(outcome="draft", rows=rows, columns=columns, cells=cells,
                                    inventory=inventory, target_total_lift=target,
                                    question_code=question_code, question_code_confidence=code_confidence,
                                    issues=issues)


def main() -> None:
    cv2.setNumThreads(1)
    raw = sys.stdin.buffer.read(12 * 1024 * 1024 + 1)
    if len(raw) > 12 * 1024 * 1024:
        result = BalloonRecognitionResult(outcome="invalid_image", issues=["图片不能超过 12 MB。"])
    else:
        try:
            with Image.open(io.BytesIO(raw)) as pil:
                if pil.format not in ("PNG", "JPEG", "WEBP") or pil.width * pil.height > MAX_PIXELS:
                    raise ValueError("unsupported image or pixel count")
                scale = min(1.0, (WORKING_PIXELS / (pil.width * pil.height)) ** .5,
                            MAX_SIDE / max(pil.width, pil.height))
                if scale < 1:
                    pil = pil.resize((max(1, int(pil.width * scale)), max(1, int(pil.height * scale))))
                image = cv2.cvtColor(np.asarray(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, cv2.error):
            result = BalloonRecognitionResult(outcome="invalid_image", issues=["图片无法解码、格式不支持或超过 2000 万像素，请换一张图片。"])
        else:
            try:
                result = _recognize(image)
            except Exception:
                result = BalloonRecognitionResult(outcome="failed", issues=["识别服务处理失败，请稍后重试或手动输入题面。"])
    sys.stdout.buffer.write(json.dumps(result.model_dump(), ensure_ascii=True).encode("utf-8"))


if __name__ == "__main__":
    main()
