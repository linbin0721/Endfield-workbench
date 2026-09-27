import type { components } from "./generated/api";
import type { CatalogCandidate, RecognitionResult } from "./api";

export type BalloonPuzzle = components["schemas"]["BalloonPuzzle"];
export type BalloonSolveResult = components["schemas"]["BalloonSolveResult"];

export type RecognitionPuzzle =
  | { puzzle: BalloonPuzzle; error?: never }
  | { puzzle?: never; error: string };

function validatePuzzle(candidate: BalloonPuzzle): RecognitionPuzzle {
  const { rows, columns, usable_cells, inventory } = candidate;
  if (!Number.isInteger(rows) || !Number.isInteger(columns) || rows < 2 || rows > 6 || columns < 2 || columns > 6 ||
      !Array.isArray(usable_cells) || !usable_cells.length || !Array.isArray(inventory) || !inventory.length) {
    return { error: "目录中的题面结构不完整，无法用于求解。" };
  }
  if (usable_cells.some((cell) => !Number.isInteger(cell.row) || !Number.isInteger(cell.column) ||
      cell.row < 0 || cell.row >= rows || cell.column < 0 || cell.column >= columns) ||
      inventory.some((item) => !Number.isInteger(item.lift) || !Number.isInteger(item.count) ||
      item.lift < 1 || item.count < 1)) {
    return { error: "目录中的题面数值无效，无法用于求解。" };
  }
  const totalCount = inventory.reduce((sum, item) => sum + item.count, 0);
  if (new Set(inventory.map((item) => item.lift)).size !== inventory.length ||
      totalCount > 18 || totalCount > usable_cells.length) {
    return { error: "目录中的题面与棋盘或气球上限不一致，无法用于求解。" };
  }
  return { puzzle: candidate };
}

/** A catalog candidate is already a complete puzzle; only shape-check it before solving. */
export function puzzleFromCandidate(candidate: CatalogCandidate): RecognitionPuzzle {
  return validatePuzzle(candidate.puzzle);
}

export function puzzleFromRecognition(result: RecognitionResult): RecognitionPuzzle {
  const { rows, columns, cells } = result;
  if (result.outcome !== "draft" || !Number.isInteger(rows) || !Number.isInteger(columns) ||
      rows == null || columns == null || rows < 2 || rows > 6 || columns < 2 || columns > 6 ||
      !cells || cells.length !== rows * columns) {
    return { error: "未能可靠识别完整棋盘，请上传包含完整棋盘和右侧所有气球库存的清晰截图重试。" };
  }
  const usable_cells = cells.flatMap((cell, index) => cell === "usable"
    ? [{ row: Math.floor(index / columns), column: index % columns }] : []);
  if (!usable_cells.length) {
    return { error: "未能识别可放置格，请上传包含完整棋盘和右侧所有气球库存的清晰截图重试。" };
  }
  const stock = result.inventory ?? [];
  if (!stock.length || stock.length > 8 || stock.some((item) =>
    !Number.isInteger(item.lift) || !Number.isInteger(item.count) ||
    item.lift == null || item.count == null || item.lift < 1 || item.lift > 100 || item.count < 1 || item.count > 18)) {
    return { error: "气球库存数字识别不完整，请上传包含完整棋盘和右侧所有气球库存的清晰截图重试。" };
  }
  const inventory = stock.map((item) => ({ lift: item.lift!, count: item.count! }));
  if (result.target_total_lift != null &&
      inventory.reduce((sum, item) => sum + item.lift * item.count, 0) !== result.target_total_lift) {
    return { error: "识别出的库存与棋盘或目标总升力不一致，请换一张清晰完整的截图重试。" };
  }
  const checked = validatePuzzle({ rule_version: "center-torque-v1", rows, columns, usable_cells, inventory });
  if (!checked.puzzle) return { error: "识别出的库存与棋盘或目标总升力不一致，请换一张清晰完整的截图重试。" };
  return checked;
}
