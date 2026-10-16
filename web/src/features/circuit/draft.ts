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

/** Machine-readable reasons of a recognition draft (EW-031 contract); display hints only. */
export const DRAFT_REASONS = ["row_targets", "column_targets", "rejected", "unsatisfiable", "solver_limit", "validation_failed"] as const;
export type DraftReason = (typeof DRAFT_REASONS)[number];

type RecordValue = Record<string, unknown>;
const asRecord = (value: unknown): RecordValue | null =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : null;
const isTarget = (value: unknown, limit: number): value is number | null =>
  value === null || (Number.isInteger(value) && (value as number) >= 0 && (value as number) <= limit);

/**
 * Editable draft of an incomplete recognition, or null when the result has
 * none or it does not hold together (then the page asks for a new
 * screenshot, as before). The data is untrusted: sizes, channel indices,
 * cells and pieces are checked here; the full puzzle check runs on solve.
 */
export function draftFromRecognition(result: unknown): { draft: CircuitDraft; reasons: DraftReason[] } | null {
  const value = asRecord(asRecord(result)?.draft);
  if (!value || value.rule_version !== "line-count-v1") return null;
  const { rows, columns } = value;
  if (!Number.isInteger(rows) || !Number.isInteger(columns) || (rows as number) < 2 || (rows as number) > 10 ||
      (columns as number) < 2 || (columns as number) > 10) return null;
  const r = rows as number, c = columns as number;
  if (!Array.isArray(value.channels) || value.channels.length < 1 || value.channels.length > 4) return null;
  const channels: DraftChannel[] = [];
  for (const [position, raw] of value.channels.entries()) {
    const channel = asRecord(raw);
    if (!channel || channel.index !== position || !Array.isArray(channel.row_targets) || !Array.isArray(channel.column_targets) ||
        channel.row_targets.length !== r || channel.column_targets.length !== c ||
        !channel.row_targets.every((target) => isTarget(target, c)) || !channel.column_targets.every((target) => isTarget(target, r))) return null;
    channels.push({ index: position, row_targets: [...channel.row_targets] as (number | null)[], column_targets: [...channel.column_targets] as (number | null)[] });
  }
  if (!Array.isArray(value.cells) || value.cells.length !== r * c) return null;
  const cells: DraftCell[] = [];
  for (const raw of value.cells) {
    const cell = asRecord(raw);
    if (!cell || !(cell.kind === "empty" || cell.kind === "blocked" || cell.kind === "fixed")) return null;
    if (cell.kind === "fixed" ? !(Number.isInteger(cell.channel) && (cell.channel as number) < channels.length && (cell.channel as number) >= 0)
      : cell.channel !== null && cell.channel !== undefined) return null;
    cells.push({ kind: cell.kind, channel: cell.kind === "fixed" ? cell.channel as number : null });
  }
  if (!Array.isArray(value.pieces) || value.pieces.length < 1 || value.pieces.length > 32) return null;
  const pieces: DraftPiece[] = [];
  for (const raw of value.pieces) {
    const piece = asRecord(raw);
    if (!piece || !Number.isInteger(piece.channel) || (piece.channel as number) < 0 || (piece.channel as number) >= channels.length ||
        !Array.isArray(piece.cells) || piece.cells.length < 1) return null;
    const shape = piece.cells.map(asRecord);
    if (shape.some((cell) => !cell || !Number.isInteger(cell.row) || !Number.isInteger(cell.column) || (cell.row as number) < 0 || (cell.column as number) < 0)) return null;
    pieces.push({ channel: piece.channel as number, cells: shape.map((cell) => ({ row: cell!.row as number, column: cell!.column as number })) });
  }
  const reasons = Array.isArray(value.missing)
    ? value.missing.filter((reason): reason is DraftReason => (DRAFT_REASONS as readonly unknown[]).includes(reason)) : [];
  return { draft: { rows: r, columns: c, channels, cells, pieces, palette: value.palette }, reasons };
}
