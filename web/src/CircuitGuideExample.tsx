import { circuitColorStyle, circuitFallbackDisplayColor } from "./circuitDisplay";
import { CircuitPieceShape } from "./CircuitPuzzlePreview";

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

export default function CircuitGuideExample({ mode }: Props) {
  const titleId = `circuit-guide-${mode}-title`;
  const screenshot = mode === "screenshot";
  return <section className="panel" aria-labelledby={titleId}>
    <div className="section-heading"><div><span className="eyebrow">00 / 示例</span>
      <h2 id={titleId}>{screenshot ? "截图范围示例" : "题号位置示例"}</h2></div>
      <span className="badge">自制示意图</span>
    </div>
    <p className="muted">{screenshot
      ? "截图必须包含完整棋盘、上方和左侧的全部约束，以及右侧全部库存形状；左侧题号可选。"
      : "题号位于棋盘左侧。按题号查询无需上传截图，只需输入题号。"}</p>
    <figure className="circuit-guide" aria-label="未解题源石电路示意画面">
      <div className="circuit-guide-stage">
        <div className="circuit-guide-code-region">
          <code>△-V40020</code>
        </div>
        <div className="circuit-guide-board-region">
          <div className="circuit-guide-column-targets">
            <span style={circuitColorStyle(GUIDE_COLORS[0])}>
              <i className="circuit-guide-swatch" aria-hidden="true" />3·0·1·0
            </span>
            <span style={circuitColorStyle(GUIDE_COLORS[1])}>
              <i className="circuit-guide-swatch" aria-hidden="true" />1·2·0·1
            </span>
          </div>
          <div className="circuit-guide-board-row">
            <div className="circuit-guide-row-targets">
              <span style={circuitColorStyle(GUIDE_COLORS[0])}><i aria-hidden="true" />3<br />0<br />1<br />0</span>
              <span style={circuitColorStyle(GUIDE_COLORS[1])}><i aria-hidden="true" />0<br />1<br />2<br />1</span>
            </div>
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
        </div>
        <div className="circuit-guide-inventory">
          {GUIDE_PIECES.map((piece, index) => <div className="circuit-guide-piece" key={index}>
            <CircuitPieceShape cells={piece.cells} color={GUIDE_COLORS[piece.channel]} />
          </div>)}
        </div>
      </div>
    </figure>
  </section>;
}
