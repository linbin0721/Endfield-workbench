import { useId } from "react";
import {
  circuitColorStyle,
  circuitFallbackDisplayColor,
  circuitPieceBoundarySegments,
  circuitPieceFill,
  type CircuitDisplayColor,
  type CircuitDisplayPoint,
} from "./circuitDisplay";

type Props = { mode: "screenshot" | "code" };

const GUIDE_CELLS = [
  -1, 0, null, null,
  1, null, null, null,
  null, null, 0, null,
  null, null, null, null,
] as const;

const GUIDE_PIECES = [
  { channel: 0, cells: [{ row: 0, column: 0 }, { row: 1, column: 0 }] },
  { channel: 1, cells: [{ row: 0, column: 0 }, { row: 1, column: 0 }, { row: 1, column: 1 }] },
  { channel: 1, cells: [{ row: 0, column: 0 }] },
];
const GUIDE_COLORS = [circuitFallbackDisplayColor(0), circuitFallbackDisplayColor(1)];

function CircuitGuidePiece({ cells, color }: {
  cells: readonly CircuitDisplayPoint[];
  color: CircuitDisplayColor;
}) {
  const id = useId().replace(/:/g, "");
  const fill = circuitPieceFill(cells);
  const outline = circuitPieceBoundarySegments(cells).map((segment) =>
    `M${segment.x1} ${segment.y1}L${segment.x2} ${segment.y2}`).join("");
  const padding = 0.14;
  return <svg className="circuit-guide-piece-svg"
    viewBox={`${fill.bounds.x1 - padding} ${fill.bounds.y1 - padding} ${fill.bounds.x2 - fill.bounds.x1 + padding * 2} ${fill.bounds.y2 - fill.bounds.y1 + padding * 2}`}
    aria-hidden="true">
    <defs>
      <linearGradient id={`${id}-fill`} gradientUnits="userSpaceOnUse"
        x1={fill.bounds.x1} y1={fill.bounds.y1} x2={fill.bounds.x2} y2={fill.bounds.y2}>
        <stop offset="0" stopColor={color.highlight} />
        <stop offset="0.24" stopColor={color.fill} />
        <stop offset="1" stopColor={color.softFill} />
      </linearGradient>
    </defs>
    <path d={fill.pathData} fill={`url(#${id}-fill)`} data-circuit-guide-piece-fill="" />
    <path d={outline} fill="none" stroke={color.edge} strokeWidth="0.095"
      strokeLinejoin="round" strokeLinecap="round" />
    <path d={outline} fill="none" stroke={color.highlight} strokeWidth="0.025"
      strokeLinejoin="round" strokeLinecap="round" opacity="0.72" />
  </svg>;
}

export default function CircuitGuideExample({ mode }: Props) {
  const titleId = `circuit-guide-${mode}-title`;
  const screenshot = mode === "screenshot";
  return <section className="panel" aria-labelledby={titleId}>
    <div className="section-heading"><div><span className="eyebrow">00 / 示例</span>
      <h2 id={titleId}>{screenshot ? "截图范围示例" : "题号位置示例"}</h2></div>
      <span className="badge">自制示意图</span>
    </div>
    <p className="muted">{screenshot
      ? "截图需完整包含 1 号棋盘和 2 号全部库存；3 号题号可选。"
      : "1 号是棋盘，2 号是库存，3 号是棋盘左侧题号；按题号查询只需输入 3 号，无需上传截图。"}</p>
    <figure className="circuit-guide" aria-label="未解题源石电路示意画面">
      <div className="circuit-guide-stage">
        <div className="circuit-guide-code-region circuit-guide-region guide-code">
          <b className="guide-marker" aria-hidden="true">3</b>
          <code>△-V40020</code>
        </div>
        <div className="circuit-guide-board-region circuit-guide-region guide-board">
          <b className="guide-marker" aria-hidden="true">1</b>
          <div className="circuit-guide-board">
            {GUIDE_CELLS.map((channel, index) => {
              const color = channel != null && channel >= 0 ? GUIDE_COLORS[channel] : null;
              return <span key={index} className={`circuit-cell ${channel === -1 ? "blocked" : color ? "fixed" : "empty"}`}
                style={color ? circuitColorStyle(color) : undefined} data-circuit-pattern={color?.channel}>
                {channel === -1 ? <i className="circuit-obstacle-mark" aria-hidden="true" />
                  : color ? <i className="circuit-fixed-mark" aria-hidden="true" /> : null}
              </span>;
            })}
          </div>
        </div>
        <div className="circuit-guide-inventory circuit-guide-region guide-inventory">
          <b className="guide-marker" aria-hidden="true">2</b>
          {GUIDE_PIECES.map((piece, index) => <div className="circuit-guide-piece" key={index}>
            <CircuitGuidePiece cells={piece.cells} color={GUIDE_COLORS[piece.channel]} />
          </div>)}
        </div>
      </div>
    </figure>
  </section>;
}
