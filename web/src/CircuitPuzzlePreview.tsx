import type { CircuitPuzzle } from "./api";
import { validateCircuitPuzzle } from "./circuit";
import {
  circuitColorStyle,
  resolveCircuitDisplayPalette,
  type CircuitDisplayColor,
} from "./circuitDisplay";

type Props = {
  puzzle: CircuitPuzzle | unknown;
  displayPalette?: unknown;
  compact?: boolean;
};

type PieceShapeProps = {
  cells: Array<{ row: number; column: number }>;
  color: CircuitDisplayColor;
};

export function CircuitColorToken({ color }: { color: CircuitDisplayColor }) {
  return <span className="circuit-color-token" style={circuitColorStyle(color)}>
    <i data-circuit-pattern={color.channel} aria-hidden="true" />
    {color.name}
  </span>;
}

export function CircuitPieceShape({ cells, color }: PieceShapeProps) {
  const rows = Math.max(...cells.map((cell) => cell.row)) + 1;
  const columns = Math.max(...cells.map((cell) => cell.column)) + 1;
  const occupied = new Set(cells.map((cell) => `${cell.row},${cell.column}`));
  return <span className="circuit-piece-shape"
    style={{ ...circuitColorStyle(color), gridTemplateColumns: `repeat(${columns}, 0.72rem)` }}
    aria-hidden="true">
    {Array.from({ length: rows * columns }, (_, index) => {
      const row = Math.floor(index / columns), column = index % columns;
      return <i key={`${row},${column}`} data-circuit-pattern={color.channel}
        className={occupied.has(`${row},${column}`) ? "filled" : "empty"} />;
    })}
  </span>;
}

export default function CircuitPuzzlePreview({ puzzle: value, displayPalette, compact = false }: Props) {
  const checked = validateCircuitPuzzle(value);
  if (!checked.puzzle) return <p className="error-text circuit-preview-error" role="alert">{checked.error}</p>;
  const puzzle = checked.puzzle;
  const palette = resolveCircuitDisplayPalette(puzzle, displayPalette);
  const blocked = new Set((puzzle.blocked_cells ?? []).map((cell) => `${cell.row},${cell.column}`));
  const fixed = new Map((puzzle.fixed_cells ?? []).map((cell) => [`${cell.row},${cell.column}`, cell.channel]));
  return <div className={`circuit-preview${compact ? " compact" : ""}`}>
    <div className="circuit-targets" aria-label="各颜色行列约束">
      {puzzle.channels.map((channel) => {
        const color = palette.colors[channel.index];
        return <div className="circuit-target" key={channel.index}>
          <CircuitColorToken color={color} />
          <span><b>行</b> {channel.row_targets.join(" · ")}</span>
          <span><b>列</b> {channel.column_targets.join(" · ")}</span>
        </div>;
      })}
    </div>
    <div className="circuit-preview-body">
      <div>
        <p className="circuit-preview-label">{puzzle.rows}×{puzzle.columns} 棋盘</p>
        <div className="circuit-board" style={{ gridTemplateColumns: `repeat(${puzzle.columns}, minmax(0, 1fr))` }}>
          {Array.from({ length: puzzle.rows * puzzle.columns }, (_, index) => {
            const row = Math.floor(index / puzzle.columns), column = index % puzzle.columns;
            const key = `${row},${column}`, channel = fixed.get(key);
            const kind = blocked.has(key) ? "blocked" : channel != null ? "fixed" : "empty";
            const color = channel != null ? palette.colors[channel] : null;
            const label = kind === "blocked" ? "障碍格" : color ? `${color.name}固定格` : "空格";
            return <span key={key} className={`circuit-cell ${kind}`}
              style={color ? circuitColorStyle(color) : undefined}
              data-circuit-pattern={color?.channel}
              aria-label={label}>
              {kind === "blocked" ? <i className="circuit-obstacle-mark" aria-hidden="true" />
                : color ? <i className="circuit-fixed-mark" aria-hidden="true" /> : null}
            </span>;
          })}
        </div>
      </div>
      <div className="circuit-pieces">
        <p className="circuit-preview-label">库存形状（{puzzle.pieces.length} 组）</p>
        <div className="circuit-piece-list">
          {puzzle.pieces.map((piece, index) => {
            const color = palette.colors[piece.channel];
            return <div className="circuit-piece" key={index}
              aria-label={`${color.name}，${piece.cells.length} 格库存形状`}>
              <CircuitPieceShape cells={piece.cells} color={color} />
              <CircuitColorToken color={color} />
              <small>{piece.cells.length} 格</small>
            </div>;
          })}
        </div>
      </div>
    </div>
    <div className="circuit-legend" aria-label="棋盘图例">
      <span className="circuit-legend-item blocked">斜纹 = 障碍</span>
      <span className="circuit-legend-item fixed">菱形 = 固定格</span>
      {palette.usedFallback && <span className="muted">未保存原始颜色，当前使用高对比示意色</span>}
    </div>
  </div>;
}
