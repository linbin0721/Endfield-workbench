import type { CSSProperties } from "react";
import type { CircuitPuzzle } from "./api";
import { validateCircuitPuzzle } from "./circuit";

type RecordValue = Record<string, unknown>;
export type CircuitDisplayPoint = { row: number; column: number };
export type CircuitBoundarySegment = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};
export type CircuitPieceFill = {
  pathData: string;
  bounds: {
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  };
};

export type CircuitDisplayColor = {
  channel: number;
  hueDegrees: number;
  name: string;
  fill: string;
  softFill: string;
  edge: string;
  highlight: string;
};

export type CircuitDisplayPalette = {
  colors: CircuitDisplayColor[];
  usedFallback: boolean;
};

const FALLBACK_HUES = [174, 77, 278, 218] as const;
const asRecord = (value: unknown): RecordValue | null =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : null;

export function circuitHueName(hueDegrees: number): string {
  if (!Number.isFinite(hueDegrees) || hueDegrees < 0 || hueDegrees >= 360) return "未知颜色";
  if (hueDegrees < 15 || hueDegrees >= 345) return "红色";
  if (hueDegrees < 45) return "橙色";
  if (hueDegrees < 70) return "黄色";
  if (hueDegrees < 160) return "绿色";
  if (hueDegrees < 200) return "青色";
  if (hueDegrees < 255) return "蓝色";
  if (hueDegrees < 290) return "紫色";
  return "品红色";
}

function displayColor(channel: number, hueDegrees: number): CircuitDisplayColor {
  const hue = hueDegrees;
  return {
    channel,
    hueDegrees: hue,
    name: circuitHueName(hue),
    fill: `hsl(${hue} 72% 55%)`,
    softFill: `hsl(${hue} 50% 24%)`,
    edge: `hsl(${hue} 70% 15%)`,
    highlight: `hsl(${hue} 92% 86%)`,
  };
}

function fallbackPalette(channelCount: number): CircuitDisplayPalette {
  return {
    colors: Array.from({ length: channelCount }, (_, channel) =>
      displayColor(channel, FALLBACK_HUES[channel])),
    usedFallback: true,
  };
}

export function circuitFallbackDisplayColor(channel: number): CircuitDisplayColor {
  if (!Number.isInteger(channel) || channel < 0 || channel >= FALLBACK_HUES.length) {
    throw new Error("invalid fallback circuit channel");
  }
  return displayColor(channel, FALLBACK_HUES[channel]);
}

/**
 * Resolve untrusted API color data as one atomic palette. A single missing,
 * reordered or invalid entry discards the whole input and uses fixed colors.
 */
export function resolveCircuitDisplayPalette(
  puzzleValue: CircuitPuzzle | unknown,
  paletteValue: unknown,
): CircuitDisplayPalette {
  const checked = validateCircuitPuzzle(puzzleValue);
  if (!checked.puzzle) return { colors: [], usedFallback: true };
  const channelCount = checked.puzzle.channels.length;
  if (!Array.isArray(paletteValue) || paletteValue.length !== channelCount) {
    return fallbackPalette(channelCount);
  }
  const hues: number[] = [];
  for (let channel = 0; channel < channelCount; channel++) {
    const item = asRecord(paletteValue[channel]);
    if (!item || item.channel !== channel || typeof item.hue_degrees !== "number" ||
        !Number.isFinite(item.hue_degrees) || item.hue_degrees < 0 || item.hue_degrees >= 360) {
      return fallbackPalette(channelCount);
    }
    hues.push(item.hue_degrees);
  }
  return {
    colors: hues.map((hue, channel) => displayColor(channel, hue)),
    usedFallback: false,
  };
}

export function circuitColorStyle(color: CircuitDisplayColor): CSSProperties {
  return {
    "--circuit-color": color.fill,
    "--circuit-color-soft": color.softFill,
    "--circuit-color-edge": color.edge,
    "--circuit-color-highlight": color.highlight,
  } as CSSProperties;
}

function validatedCircuitDisplayCells(cells: readonly CircuitDisplayPoint[]): {
  cells: readonly CircuitDisplayPoint[];
  occupied: Set<string>;
} {
  if (!Array.isArray(cells) || cells.length === 0) {
    throw new Error("empty circuit display cells");
  }
  const occupied = new Set<string>();
  for (const cell of cells) {
    if (cell === null || typeof cell !== "object" ||
        !Number.isInteger(cell.row) || !Number.isInteger(cell.column) ||
        cell.row < 0 || cell.column < 0) {
      throw new Error("invalid circuit display cell");
    }
    const key = `${cell.row},${cell.column}`;
    if (occupied.has(key)) throw new Error("duplicate circuit display cell");
    occupied.add(key);
  }
  return { cells, occupied };
}

/**
 * Build one compound SVG fill path and its user-space gradient bounds.
 * Every unit square is a subpath of the same fill element, so the browser
 * rasterizes one placement with one continuous gradient and no cell strokes.
 */
export function circuitPieceFill(cells: readonly CircuitDisplayPoint[]): CircuitPieceFill {
  const validated = validatedCircuitDisplayCells(cells);
  let x1 = Number.POSITIVE_INFINITY, y1 = Number.POSITIVE_INFINITY;
  let x2 = Number.NEGATIVE_INFINITY, y2 = Number.NEGATIVE_INFINITY;
  const pathData = validated.cells.map((cell) => {
    x1 = Math.min(x1, cell.column);
    y1 = Math.min(y1, cell.row);
    x2 = Math.max(x2, cell.column + 1);
    y2 = Math.max(y2, cell.row + 1);
    return `M${cell.column} ${cell.row}h1v1h-1Z`;
  }).join("");
  return { pathData, bounds: { x1, y1, x2, y2 } };
}

/** Return only the exposed unit edges of one validated placement. */
export function circuitPieceBoundarySegments(
  cells: readonly CircuitDisplayPoint[],
): CircuitBoundarySegment[] {
  const validated = validatedCircuitDisplayCells(cells);
  const { occupied } = validated;
  const segments: CircuitBoundarySegment[] = [];
  for (const cell of validated.cells) {
    const { row, column } = cell;
    if (!occupied.has(`${row - 1},${column}`)) {
      segments.push({ x1: column, y1: row, x2: column + 1, y2: row });
    }
    if (!occupied.has(`${row},${column + 1}`)) {
      segments.push({ x1: column + 1, y1: row, x2: column + 1, y2: row + 1 });
    }
    if (!occupied.has(`${row + 1},${column}`)) {
      segments.push({ x1: column + 1, y1: row + 1, x2: column, y2: row + 1 });
    }
    if (!occupied.has(`${row},${column - 1}`)) {
      segments.push({ x1: column, y1: row + 1, x2: column, y2: row });
    }
  }
  return segments.sort((first, second) =>
    first.y1 - second.y1 || first.x1 - second.x1 || first.y2 - second.y2 || first.x2 - second.x2);
}
