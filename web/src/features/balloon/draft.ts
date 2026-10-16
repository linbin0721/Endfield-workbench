import type { RecognitionResult } from "../../api";
import type { BalloonPuzzle } from "../../puzzle";

export type CellKind = "usable" | "blocked" | null;
export type StockDraft = { lift: number | null; count: number | null };

/** Editable balloon puzzle; nulls are values the recognizer could not read. */
export type BalloonDraft = {
  rows: number;
  columns: number;
  cells: CellKind[];
  inventory: StockDraft[];
  /** Target total lift printed above the board, when it was read. */
  target: number | null;
};

/**
 * Validation problems, each pointing at what to fix. The rules are the ones
 * the page enforced before (puzzle.ts and the recognition checks).
 */
export type DraftProblem =
  | { kind: "cellUnknown"; index: number }
  | { kind: "liftMissing" | "countMissing" | "liftInvalid" | "countInvalid" | "liftDuplicate"; row: number }
  | { kind: "noUsable" | "noInventory" | "tooManyKinds" }
  | { kind: "tooManyBalloons"; total: number; max: number }
  | { kind: "notEnoughCells"; total: number; usable: number }
  | { kind: "targetMismatch"; sum: number; target: number };

/** Clicking a cell in the editor: unknown and blocked become usable, usable becomes blocked. */
export const nextKind = (kind: CellKind): CellKind => kind === "usable" ? "blocked" : "usable";

export const MAX_KINDS = 8;
export const MAX_BALLOONS = 18;
export const MAX_LIFT = 100;

/** Draft of a recognition result, or null when the board itself was not read. */
export function draftFromRecognition(result: RecognitionResult): BalloonDraft | null {
  const { rows, columns, cells } = result;
  if (result.outcome !== "draft" || rows == null || columns == null || !Number.isInteger(rows) || !Number.isInteger(columns) ||
      rows < 2 || rows > 6 || columns < 2 || columns > 6 || !cells || cells.length !== rows * columns) {
    return null;
  }
  return {
    rows,
    columns,
    cells: cells.map((cell) => cell === "usable" || cell === "blocked" ? cell : null),
    inventory: (result.inventory ?? []).map((item) => ({ lift: item.lift ?? null, count: item.count ?? null })),
    target: result.target_total_lift ?? null,
  };
}

/** Read-only draft of a complete puzzle (catalog or a solved submission). */
export function draftFromPuzzle(puzzle: BalloonPuzzle, target: number | null = null): BalloonDraft {
  const usable = new Set(puzzle.usable_cells.map((cell) => `${cell.row},${cell.column}`));
  return {
    rows: puzzle.rows,
    columns: puzzle.columns,
    cells: Array.from({ length: puzzle.rows * puzzle.columns }, (_, index) =>
      usable.has(`${Math.floor(index / puzzle.columns)},${index % puzzle.columns}`) ? "usable" : "blocked"),
    inventory: puzzle.inventory.map((item) => ({ lift: item.lift, count: item.count })),
    target,
  };
}

const isWhole = (value: number | null): value is number => value !== null && Number.isInteger(value);

export function inventorySum(draft: BalloonDraft): { balloons: number; lift: number } {
  let balloons = 0, lift = 0;
  for (const item of draft.inventory) {
    if (isWhole(item.count)) balloons += item.count;
    if (isWhole(item.lift) && isWhole(item.count)) lift += item.lift * item.count;
  }
  return { balloons, lift };
}

/** Problems of the draft; an empty list means `toPuzzle` will succeed. */
export function draftProblems(draft: BalloonDraft): DraftProblem[] {
  const problems: DraftProblem[] = [];
  draft.cells.forEach((cell, index) => { if (cell === null) problems.push({ kind: "cellUnknown", index }); });
  const usable = draft.cells.filter((cell) => cell === "usable").length;
  if (usable === 0 && !problems.length) problems.push({ kind: "noUsable" });
  if (!draft.inventory.length) problems.push({ kind: "noInventory" });
  if (draft.inventory.length > MAX_KINDS) problems.push({ kind: "tooManyKinds" });
  const seen = new Map<number, number>();
  draft.inventory.forEach((item, row) => {
    if (item.lift === null) problems.push({ kind: "liftMissing", row });
    else if (!isWhole(item.lift) || item.lift < 1 || item.lift > MAX_LIFT) problems.push({ kind: "liftInvalid", row });
    else if (seen.has(item.lift)) problems.push({ kind: "liftDuplicate", row });
    else seen.set(item.lift, row);
    if (item.count === null) problems.push({ kind: "countMissing", row });
    else if (!isWhole(item.count) || item.count < 1 || item.count > MAX_BALLOONS) problems.push({ kind: "countInvalid", row });
  });
  const { balloons, lift } = inventorySum(draft);
  const complete = draft.inventory.every((item) => item.lift !== null && item.count !== null);
  if (balloons > MAX_BALLOONS) problems.push({ kind: "tooManyBalloons", total: balloons, max: MAX_BALLOONS });
  else if (usable > 0 && balloons > usable) problems.push({ kind: "notEnoughCells", total: balloons, usable });
  if (complete && draft.target !== null && lift !== draft.target) problems.push({ kind: "targetMismatch", sum: lift, target: draft.target });
  return problems;
}

/** The solvable puzzle, or null while the draft has problems. */
export function toPuzzle(draft: BalloonDraft): BalloonPuzzle | null {
  if (draftProblems(draft).length) return null;
  return {
    rule_version: "center-torque-v1",
    rows: draft.rows,
    columns: draft.columns,
    usable_cells: draft.cells.flatMap((cell, index) => cell === "usable"
      ? [{ row: Math.floor(index / draft.columns), column: index % draft.columns }] : []),
    inventory: draft.inventory.map((item) => ({ lift: item.lift!, count: item.count! })),
  };
}

/** Order-independent identity of a puzzle (cells and inventory as sets). */
function puzzleKey(puzzle: BalloonPuzzle): string {
  const cells = puzzle.usable_cells.map((cell) => `${cell.row},${cell.column}`).sort();
  const inventory = puzzle.inventory.map((item) => `${item.lift}x${item.count}`).sort();
  return `${puzzle.rows}x${puzzle.columns}|${cells.join(";")}|${inventory.join(";")}`;
}

export function samePuzzle(a: BalloonPuzzle | null, b: BalloonPuzzle | null): boolean {
  return a !== null && b !== null && puzzleKey(a) === puzzleKey(b);
}
