import type { CircuitPuzzle } from "./api";
import { validateCircuitPuzzle } from "./circuit";

type Props = {
  puzzle: CircuitPuzzle | unknown;
  compact?: boolean;
};

type PieceShapeProps = {
  cells: Array<{ row: number; column: number }>;
  channel: number;
};

export function CircuitChannelToken({ channel }: { channel: number }) {
  return <span className={`circuit-channel-token circuit-channel-${channel}`}>C{channel + 1}</span>;
}

export function CircuitPieceShape({ cells, channel }: PieceShapeProps) {
  const rows = Math.max(...cells.map((cell) => cell.row)) + 1;
  const columns = Math.max(...cells.map((cell) => cell.column)) + 1;
  const occupied = new Set(cells.map((cell) => `${cell.row},${cell.column}`));
  return <span className="circuit-piece-shape" style={{ gridTemplateColumns: `repeat(${columns}, 0.72rem)` }}
    aria-hidden="true">
    {Array.from({ length: rows * columns }, (_, index) => {
      const row = Math.floor(index / columns), column = index % columns;
      return <i key={`${row},${column}`} className={occupied.has(`${row},${column}`)
        ? `filled circuit-channel-${channel}` : "empty"} />;
    })}
  </span>;
}

export default function CircuitPuzzlePreview({ puzzle: value, compact = false }: Props) {
  const checked = validateCircuitPuzzle(value);
  if (!checked.puzzle) return <p className="error-text circuit-preview-error" role="alert">{checked.error}</p>;
  const puzzle = checked.puzzle;
  const blocked = new Set((puzzle.blocked_cells ?? []).map((cell) => `${cell.row},${cell.column}`));
  const fixed = new Map((puzzle.fixed_cells ?? []).map((cell) => [`${cell.row},${cell.column}`, cell.channel]));
  return <div className={`circuit-preview${compact ? " compact" : ""}`}>
    <div className="circuit-targets" aria-label="各通道行列约束">
      {puzzle.channels.map((channel) => <div className="circuit-target" key={channel.index}>
        <CircuitChannelToken channel={channel.index} />
        <span><b>行</b> {channel.row_targets.join(" · ")}</span>
        <span><b>列</b> {channel.column_targets.join(" · ")}</span>
      </div>)}
    </div>
    <div className="circuit-preview-body">
      <div>
        <p className="circuit-preview-label">{puzzle.rows}×{puzzle.columns} 棋盘</p>
        <div className="circuit-board" style={{ gridTemplateColumns: `repeat(${puzzle.columns}, minmax(0, 1fr))` }}>
          {Array.from({ length: puzzle.rows * puzzle.columns }, (_, index) => {
            const row = Math.floor(index / puzzle.columns), column = index % puzzle.columns;
            const key = `${row},${column}`, channel = fixed.get(key);
            const kind = blocked.has(key) ? "blocked" : channel != null ? "fixed" : "empty";
            const label = kind === "blocked" ? "障碍格" : kind === "fixed" ? `固定格 C${channel! + 1}` : "空格";
            return <span key={key} className={`circuit-cell ${kind}${channel != null ? ` circuit-channel-${channel}` : ""}`}
              aria-label={`第 ${row + 1} 行第 ${column + 1} 列，${label}`}>
              {kind === "blocked" ? "×" : channel != null ? `C${channel + 1}` : ""}
            </span>;
          })}
        </div>
      </div>
      <div className="circuit-pieces">
        <p className="circuit-preview-label">库存拼块（{puzzle.pieces.length}）</p>
        <div className="circuit-piece-list">
          {puzzle.pieces.map((piece, index) => <div className="circuit-piece" key={index}>
            <CircuitPieceShape cells={piece.cells} channel={piece.channel} />
            <span>拼块 {index + 1}</span><CircuitChannelToken channel={piece.channel} />
            <small>{piece.cells.length} 格</small>
          </div>)}
        </div>
      </div>
    </div>
    <div className="circuit-legend" aria-label="棋盘图例">
      {puzzle.channels.map((channel) => <CircuitChannelToken key={channel.index} channel={channel.index} />)}
      <span className="circuit-legend-item blocked">× 障碍</span>
      <span className="circuit-legend-item fixed">文字通道 = 固定格</span>
    </div>
  </div>;
}
