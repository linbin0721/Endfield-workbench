import type { CircuitPuzzle } from "../../api";
import { validateCircuitPuzzle } from "../../circuit";

export type CellKind = "empty" | "blocked" | "fixed";
/** kind=null: not classified; a fixed cell may still miss its channel. */
export type DraftCell = { kind: CellKind | null; channel: number | null };
export type DraftChannel = { index: number; row_targets: (number | null)[]; column_targets: (number | null)[] };
export type DraftPiece = CircuitPuzzle["pieces"][number];

/**
 * Editable circuit puzzle. Targets, obstacles and fixed cells can be changed;
 * the pieces (shapes and channels) are fixed. `palette` is the untrusted
 * display data passed through to the colour resolver unchanged.
 */
export type CircuitDraft = {
  rows: number;
  columns: number;
  channels: DraftChannel[];
  cells: DraftCell[];
  pieces: DraftPiece[];
  palette: unknown;
};

export type DraftProblem =
  | { kind: "targetMissing"; channel: number; axis: "row" | "column"; index: number }
  | { kind: "targetInvalid"; channel: number; axis: "row" | "column"; index: number }
  | { kind: "cellUnknown"; count: number }
  | { kind: "fixedChannel"; count: number }
  /** Raw canonical message from validateCircuitPuzzle; the message bridge translates it. */
  | { kind: "invalid"; message: string };

const key = (row: number, column: number) => `${row},${column}`;

export function draftFromPuzzle(puzzle: CircuitPuzzle, palette: unknown): CircuitDraft {
  const blocked = new Set((puzzle.blocked_cells ?? []).map((cell) => key(cell.row, cell.column)));
  const fixed = new Map((puzzle.fixed_cells ?? []).map((cell) => [key(cell.row, cell.column), cell.channel]));
  return {
    rows: puzzle.rows,
    columns: puzzle.columns,
    channels: puzzle.channels.map((channel) => ({
      index: channel.index,
      row_targets: [...channel.row_targets],
      column_targets: [...channel.column_targets],
    })).sort((a, b) => a.index - b.index),
    cells: Array.from({ length: puzzle.rows * puzzle.columns }, (_, index) => {
      const cellKey = key(Math.floor(index / puzzle.columns), index % puzzle.columns);
      if (blocked.has(cellKey)) return { kind: "blocked", channel: null };
      const channel = fixed.get(cellKey);
      return channel != null ? { kind: "fixed", channel } : { kind: "empty", channel: null };
    }),
    pieces: puzzle.pieces.map((piece) => ({ channel: piece.channel, cells: piece.cells.map((cell) => ({ ...cell })) })),
    palette,
  };
}

/** Clicking a cell in the editor: unknown → empty → blocked → fixed (active channel) → empty. */
export function nextCell(cell: DraftCell, activeChannel: number): DraftCell {
  if (cell.kind === null) return { kind: "empty", channel: null };
  if (cell.kind === "empty") return { kind: "blocked", channel: null };
  if (cell.kind === "blocked") return { kind: "fixed", channel: activeChannel };
  return cell.channel === activeChannel ? { kind: "empty", channel: null } : { kind: "fixed", channel: activeChannel };
}

function buildPuzzle(draft: CircuitDraft): CircuitPuzzle {
  return {
    rule_version: "line-count-v1",
    rows: draft.rows,
    columns: draft.columns,
    channels: draft.channels.map((channel) => ({
      index: channel.index,
      row_targets: channel.row_targets.map((value) => value ?? 0),
      column_targets: channel.column_targets.map((value) => value ?? 0),
    })),
    blocked_cells: draft.cells.flatMap((cell, index) => cell.kind === "blocked"
      ? [{ row: Math.floor(index / draft.columns), column: index % draft.columns }] : []),
    fixed_cells: draft.cells.flatMap((cell, index) => cell.kind === "fixed" && cell.channel !== null
      ? [{ row: Math.floor(index / draft.columns), column: index % draft.columns, channel: cell.channel }] : []),
    pieces: draft.pieces,
  };
}

/**
 * Problems in the order the user should fix them: missing or out-of-range
 * targets and unclassified cells first, then the full puzzle check shared
 * with catalog and recognition data. Empty means `toPuzzle` succeeds.
 */
export function draftProblems(draft: CircuitDraft): DraftProblem[] {
  const problems: DraftProblem[] = [];
  for (const channel of draft.channels) {
    for (const [axis, targets, limit] of [["row", channel.row_targets, draft.columns], ["column", channel.column_targets, draft.rows]] as const) {
      targets.forEach((value, index) => {
        if (value === null) problems.push({ kind: "targetMissing", channel: channel.index, axis, index });
        else if (!Number.isInteger(value) || value < 0 || value > limit) problems.push({ kind: "targetInvalid", channel: channel.index, axis, index });
      });
    }
  }
  const unknown = draft.cells.filter((cell) => cell.kind === null).length;
  if (unknown) problems.push({ kind: "cellUnknown", count: unknown });
  const noChannel = draft.cells.filter((cell) => cell.kind === "fixed" && cell.channel === null).length;
  if (noChannel) problems.push({ kind: "fixedChannel", count: noChannel });
  if (problems.length) return problems;
  const checked = validateCircuitPuzzle(buildPuzzle(draft));
  return checked.puzzle ? [] : [{ kind: "invalid", message: checked.error }];
}

export function toPuzzle(draft: CircuitDraft): CircuitPuzzle | null {
  if (draftProblems(draft).length) return null;
  return validateCircuitPuzzle(buildPuzzle(draft)).puzzle ?? null;
}

/** Order-independent identity of a puzzle, to tell whether the answer still belongs to the draft. */
export function puzzleKey(puzzle: CircuitPuzzle): string {
  const cells = (list: { row: number; column: number; channel?: number }[] | undefined) =>
    (list ?? []).map((cell) => `${cell.row},${cell.column},${cell.channel ?? ""}`).sort().join(";");
  const channels = [...puzzle.channels].sort((a, b) => a.index - b.index)
    .map((channel) => `${channel.index}:${channel.row_targets.join(",")}/${channel.column_targets.join(",")}`).join("|");
  return `${puzzle.rows}x${puzzle.columns}|${channels}|${cells(puzzle.blocked_cells)}|${cells(puzzle.fixed_cells)}|${puzzle.pieces.length}`;
}
