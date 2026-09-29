import type {
  CircuitCatalogCandidate,
  CircuitPuzzle,
  CircuitRecognitionResult,
  CircuitSolveResult,
} from "./api";

type Point = { row: number; column: number };
type RecordValue = Record<string, unknown>;

export type CircuitPuzzleCheck =
  | { puzzle: CircuitPuzzle; error?: never }
  | { puzzle?: never; error: string };

export type CircuitBoardCell = Point & {
  kind: "empty" | "blocked" | "fixed" | "placed";
  channel?: number;
  pieceIndex?: number;
};

export type CircuitPlacementSummary = {
  pieceIndex: number;
  channel: number;
  row: number;
  column: number;
  rotation: 0 | 90 | 180 | 270;
  cells: Point[];
};

export type CircuitDerivedAnswer = {
  puzzle: CircuitPuzzle;
  cells: CircuitBoardCell[];
  placements: CircuitPlacementSummary[];
};

export type CircuitAnswerCheck =
  | { answer: CircuitDerivedAnswer; error?: never }
  | { answer?: never; error: string };

const ROTATIONS = new Set([0, 90, 180, 270]);
const pointKey = (row: number, column: number) => `${row},${column}`;
const isInteger = (value: unknown): value is number => Number.isInteger(value);
const asRecord = (value: unknown): RecordValue | null =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : null;

function puzzleError(message: string): CircuitPuzzleCheck {
  return { error: `题面数据无效：${message}，无法用于求解。` };
}

function readPoint(value: unknown): Point | null {
  const item = asRecord(value);
  if (!item || !isInteger(item.row) || !isInteger(item.column)) return null;
  return { row: item.row, column: item.column };
}

/**
 * Validate data crossing the HTTP/catalog boundary before it is rendered or
 * submitted. This mirrors the backend CircuitPuzzle invariants instead of
 * trusting generated TypeScript types at runtime.
 */
export function validateCircuitPuzzle(value: unknown): CircuitPuzzleCheck {
  const source = asRecord(value);
  if (!source || source.rule_version !== "line-count-v1" ||
      !isInteger(source.rows) || !isInteger(source.columns) ||
      source.rows < 2 || source.rows > 10 || source.columns < 2 || source.columns > 10 ||
      source.rows * source.columns > 100) {
    return puzzleError("规则版本或棋盘尺寸不正确");
  }
  const rows = source.rows;
  const columns = source.columns;
  if (!Array.isArray(source.channels) || source.channels.length < 1 || source.channels.length > 4) {
    return puzzleError("通道数量不正确");
  }

  const channels: CircuitPuzzle["channels"] = [];
  for (const rawChannel of source.channels) {
    const channel = asRecord(rawChannel);
    if (!channel || !isInteger(channel.index) || !Array.isArray(channel.row_targets) ||
        !Array.isArray(channel.column_targets) || channel.row_targets.length !== rows ||
        channel.column_targets.length !== columns ||
        channel.row_targets.some((target) => !isInteger(target) || target < 0 || target > columns) ||
        channel.column_targets.some((target) => !isInteger(target) || target < 0 || target > rows)) {
      return puzzleError("行列约束不完整或超出棋盘范围");
    }
    channels.push({
      index: channel.index,
      row_targets: [...channel.row_targets] as number[],
      column_targets: [...channel.column_targets] as number[],
    });
  }
  const channelIndices = channels.map((channel) => channel.index).sort((a, b) => a - b);
  if (channelIndices.some((index, position) => index !== position)) {
    return puzzleError("颜色通道编号必须从零开始连续排列");
  }
  const knownChannels = new Set(channelIndices);

  const rawBlocked = source.blocked_cells ?? [];
  if (!Array.isArray(rawBlocked) || rawBlocked.length > 100) return puzzleError("障碍格列表不正确");
  const blockedCells: NonNullable<CircuitPuzzle["blocked_cells"]> = [];
  const blocked = new Set<string>();
  for (const rawCell of rawBlocked) {
    const cell = readPoint(rawCell);
    if (!cell || cell.row < 0 || cell.row >= rows || cell.column < 0 || cell.column >= columns ||
        blocked.has(pointKey(cell.row, cell.column))) {
      return puzzleError("障碍格重复或越界");
    }
    blocked.add(pointKey(cell.row, cell.column));
    blockedCells.push(cell);
  }

  const rawFixed = source.fixed_cells ?? [];
  if (!Array.isArray(rawFixed) || rawFixed.length > 100) return puzzleError("固定格列表不正确");
  const fixedCells: NonNullable<CircuitPuzzle["fixed_cells"]> = [];
  const fixed = new Set<string>();
  const fixedRowCounts = channels.map(() => Array<number>(rows).fill(0));
  const fixedColumnCounts = channels.map(() => Array<number>(columns).fill(0));
  for (const rawCell of rawFixed) {
    const item = asRecord(rawCell);
    const cell = readPoint(rawCell);
    if (!item || !cell || !isInteger(item.channel) || !knownChannels.has(item.channel) ||
        cell.row < 0 || cell.row >= rows || cell.column < 0 || cell.column >= columns) {
      return puzzleError("固定格的坐标或通道不正确");
    }
    const key = pointKey(cell.row, cell.column);
    if (blocked.has(key) || fixed.has(key)) return puzzleError("固定格重复或覆盖障碍格");
    fixed.add(key);
    fixedCells.push({ ...cell, channel: item.channel });
    fixedRowCounts[item.channel][cell.row]++;
    fixedColumnCounts[item.channel][cell.column]++;
  }
  for (const channel of channels) {
    if (channel.row_targets.some((target, row) => fixedRowCounts[channel.index][row] > target) ||
        channel.column_targets.some((target, column) => fixedColumnCounts[channel.index][column] > target)) {
      return puzzleError("固定格已经超过对应行列约束");
    }
  }

  if (!Array.isArray(source.pieces) || source.pieces.length < 1 || source.pieces.length > 32) {
    return puzzleError("拼块数量不正确");
  }
  const pieces: CircuitPuzzle["pieces"] = [];
  const pieceArea = channels.map(() => 0);
  for (const rawPiece of source.pieces) {
    const piece = asRecord(rawPiece);
    if (!piece || !isInteger(piece.channel) || !knownChannels.has(piece.channel) ||
        !Array.isArray(piece.cells) || piece.cells.length < 1 || piece.cells.length > 100) {
      return puzzleError("拼块通道或格子列表不正确");
    }
    const cells: Point[] = [];
    const coordinates = new Set<string>();
    for (const rawCell of piece.cells) {
      const cell = readPoint(rawCell);
      if (!cell || cell.row < 0 || cell.column < 0 || coordinates.has(pointKey(cell.row, cell.column))) {
        return puzzleError("拼块含有负坐标或重复格子");
      }
      coordinates.add(pointKey(cell.row, cell.column));
      cells.push(cell);
    }
    if (Math.min(...cells.map((cell) => cell.row)) !== 0 ||
        Math.min(...cells.map((cell) => cell.column)) !== 0) {
      return puzzleError("拼块局部坐标没有归一化");
    }
    const pending = [cells[0]];
    const visited = new Set([pointKey(cells[0].row, cells[0].column)]);
    while (pending.length) {
      const current = pending.pop()!;
      for (const [row, column] of [
        [current.row + 1, current.column], [current.row - 1, current.column],
        [current.row, current.column + 1], [current.row, current.column - 1],
      ]) {
        const key = pointKey(row, column);
        if (coordinates.has(key) && !visited.has(key)) {
          visited.add(key);
          pending.push({ row, column });
        }
      }
    }
    if (visited.size !== cells.length) return puzzleError("拼块不是四连通形状");
    const height = Math.max(...cells.map((cell) => cell.row)) + 1;
    const width = Math.max(...cells.map((cell) => cell.column)) + 1;
    if (!((height <= rows && width <= columns) || (width <= rows && height <= columns))) {
      return puzzleError("拼块无法以任何旋转放入棋盘");
    }
    pieceArea[piece.channel] += cells.length;
    pieces.push({ channel: piece.channel, cells });
  }

  const fixedCounts = channels.map(() => 0);
  for (const cell of fixedCells) fixedCounts[cell.channel]++;
  for (const channel of channels) {
    const rowTotal = channel.row_targets.reduce((sum, value) => sum + value, 0);
    const columnTotal = channel.column_targets.reduce((sum, value) => sum + value, 0);
    if (rowTotal !== columnTotal || rowTotal !== fixedCounts[channel.index] + pieceArea[channel.index]) {
      return puzzleError("通道行列总数与固定格及拼块面积不一致");
    }
  }
  for (let row = 0; row < rows; row++) {
    const blockedCount = blockedCells.filter((cell) => cell.row === row).length;
    if (channels.reduce((sum, channel) => sum + channel.row_targets[row], 0) > columns - blockedCount) {
      return puzzleError("某行约束超过非障碍格容量");
    }
  }
  for (let column = 0; column < columns; column++) {
    const blockedCount = blockedCells.filter((cell) => cell.column === column).length;
    if (channels.reduce((sum, channel) => sum + channel.column_targets[column], 0) > rows - blockedCount) {
      return puzzleError("某列约束超过非障碍格容量");
    }
  }

  return { puzzle: {
    rule_version: "line-count-v1",
    rows,
    columns,
    channels,
    blocked_cells: blockedCells,
    fixed_cells: fixedCells,
    pieces,
  } };
}

/** Validate a complete puzzle carried by a recognition result. */
export function puzzleFromCircuitRecognition(value: CircuitRecognitionResult | unknown): CircuitPuzzleCheck {
  const result = asRecord(value);
  if (!result || result.outcome !== "recognized" || result.puzzle == null) {
    return { error: "识别结果没有完整题面，不能提交求解。" };
  }
  return validateCircuitPuzzle(result.puzzle);
}

/** Validate catalog metadata and its complete puzzle before rendering or solving. */
export function puzzleFromCircuitCandidate(value: CircuitCatalogCandidate | unknown): CircuitPuzzleCheck {
  const candidate = asRecord(value);
  if (!candidate || typeof candidate.fingerprint !== "string" ||
      !/^[0-9a-f]{64}$/.test(candidate.fingerprint) ||
      (candidate.status !== "provisional" && candidate.status !== "verified") ||
      !isInteger(candidate.observations) || candidate.observations < 1 ||
      candidate.status !== (candidate.observations >= 2 ? "verified" : "provisional")) {
    return { error: "目录候选的状态或观察记录无效，不能用于求解。" };
  }
  return validateCircuitPuzzle(candidate.puzzle);
}

/** Rotate local coordinates clockwise exactly like the backend verifier. */
export function rotateCircuitCells(cells: readonly Point[], rotation: number): Point[] {
  if (!ROTATIONS.has(rotation) || cells.length === 0 ||
      cells.some((cell) => !isInteger(cell.row) || !isInteger(cell.column))) {
    throw new Error("invalid circuit piece rotation");
  }
  let current = cells.map((cell) => ({ row: cell.row, column: cell.column }))
    .sort((a, b) => a.row - b.row || a.column - b.column);
  for (let turn = 0; turn < rotation / 90; turn++) {
    const rotated = current.map((cell) => ({ row: cell.column, column: -cell.row }));
    const minRow = Math.min(...rotated.map((cell) => cell.row));
    const minColumn = Math.min(...rotated.map((cell) => cell.column));
    current = rotated.map((cell) => ({ row: cell.row - minRow, column: cell.column - minColumn }))
      .sort((a, b) => a.row - b.row || a.column - b.column);
  }
  return current;
}

function answerError(message: string): CircuitAnswerCheck {
  return { error: `服务返回的答案无效：${message}。` };
}

/** Rebuild and independently validate the solved board before any answer is drawn. */
export function deriveCircuitAnswer(puzzleValue: CircuitPuzzle | unknown,
                                    resultValue: CircuitSolveResult | unknown): CircuitAnswerCheck {
  const checked = validateCircuitPuzzle(puzzleValue);
  if (!checked.puzzle) return { error: checked.error };
  const puzzle = checked.puzzle;
  const result = asRecord(resultValue);
  const solution = result ? asRecord(result.solution) : null;
  if (!result || result.outcome !== "solved" || result.rule_version !== "line-count-v1" ||
      result.limit_reason != null || !solution || !Array.isArray(solution.placements)) {
    return answerError("缺少完整的已求解摆放数据");
  }

  const placements: Array<{ piece_index: number; row: number; column: number; rotation: 0 | 90 | 180 | 270 }> = [];
  for (const rawPlacement of solution.placements) {
    const placement = asRecord(rawPlacement);
    if (!placement || !isInteger(placement.piece_index) || !isInteger(placement.row) ||
        !isInteger(placement.column) || !isInteger(placement.rotation) ||
        !ROTATIONS.has(placement.rotation) || placement.row < 0 || placement.column < 0) {
      return answerError("摆放坐标、拼块编号或旋转角度不正确");
    }
    placements.push({
      piece_index: placement.piece_index,
      row: placement.row,
      column: placement.column,
      rotation: placement.rotation as 0 | 90 | 180 | 270,
    });
  }
  const indices = placements.map((placement) => placement.piece_index).sort((a, b) => a - b);
  if (indices.length !== puzzle.pieces.length || indices.some((index, position) => index !== position)) {
    return answerError("每个库存拼块必须且只能摆放一次");
  }

  const blocked = new Set((puzzle.blocked_cells ?? []).map((cell) => pointKey(cell.row, cell.column)));
  const fixed = new Map((puzzle.fixed_cells ?? []).map((cell) => [pointKey(cell.row, cell.column), cell.channel]));
  const occupied = new Map<string, { channel: number; pieceIndex: number }>();
  const rowCounts = puzzle.channels.map(() => Array<number>(puzzle.rows).fill(0));
  const columnCounts = puzzle.channels.map(() => Array<number>(puzzle.columns).fill(0));
  for (const cell of puzzle.fixed_cells ?? []) {
    rowCounts[cell.channel][cell.row]++;
    columnCounts[cell.channel][cell.column]++;
  }

  const summaries: CircuitPlacementSummary[] = [];
  for (const placement of placements) {
    const piece = puzzle.pieces[placement.piece_index];
    const shape = rotateCircuitCells(piece.cells, placement.rotation);
    const boardCells: Point[] = [];
    for (const cell of shape) {
      const row = placement.row + cell.row;
      const column = placement.column + cell.column;
      const key = pointKey(row, column);
      if (row < 0 || row >= puzzle.rows || column < 0 || column >= puzzle.columns) {
        return answerError(`拼块 ${placement.piece_index + 1} 超出棋盘`);
      }
      if (blocked.has(key)) return answerError(`拼块 ${placement.piece_index + 1} 覆盖障碍格`);
      if (fixed.has(key)) return answerError(`拼块 ${placement.piece_index + 1} 覆盖固定格`);
      if (occupied.has(key)) return answerError("多个拼块互相重叠");
      occupied.set(key, { channel: piece.channel, pieceIndex: placement.piece_index });
      rowCounts[piece.channel][row]++;
      columnCounts[piece.channel][column]++;
      boardCells.push({ row, column });
    }
    summaries.push({
      pieceIndex: placement.piece_index,
      channel: piece.channel,
      row: placement.row,
      column: placement.column,
      rotation: placement.rotation,
      cells: boardCells,
    });
  }

  for (const channel of puzzle.channels) {
    if (rowCounts[channel.index].some((value, row) => value !== channel.row_targets[row]) ||
        columnCounts[channel.index].some((value, column) => value !== channel.column_targets[column])) {
      return answerError(`C${channel.index + 1} 的最终行列计数不符合题面`);
    }
  }

  const cells: CircuitBoardCell[] = [];
  for (let row = 0; row < puzzle.rows; row++) {
    for (let column = 0; column < puzzle.columns; column++) {
      const key = pointKey(row, column);
      const placed = occupied.get(key);
      if (blocked.has(key)) cells.push({ row, column, kind: "blocked" });
      else if (fixed.has(key)) cells.push({ row, column, kind: "fixed", channel: fixed.get(key) });
      else if (placed) cells.push({ row, column, kind: "placed", ...placed });
      else cells.push({ row, column, kind: "empty" });
    }
  }
  return { answer: { puzzle, cells, placements: summaries.sort((a, b) => a.pieceIndex - b.pieceIndex) } };
}
