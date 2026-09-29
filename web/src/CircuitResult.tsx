import { useId } from "react";
import type { CircuitPuzzle, CircuitSolveResult } from "./api";
import { deriveCircuitAnswer } from "./circuit";
import {
  circuitPieceBoundarySegments,
  circuitPieceFill,
  resolveCircuitDisplayPalette,
} from "./circuitDisplay";

type Props = {
  puzzle: CircuitPuzzle | unknown;
  displayPalette?: unknown;
  result: CircuitSolveResult;
};

const invalidResult = (message: string) => <div className="notice warning" role="alert">
  <strong>服务返回的答案无效。</strong> {message}
</div>;

export default function CircuitResult({ puzzle, displayPalette, result }: Props) {
  const svgId = useId().replace(/:/g, "");
  if (result === null || typeof result !== "object" || Array.isArray(result)) {
    return invalidResult("响应结构无法识别，未绘制答案。");
  }
  const value = result as Partial<CircuitSolveResult>;
  if (value.rule_version !== "line-count-v1") return invalidResult("规则版本与当前页面不一致，未绘制答案。");
  if (value.outcome === "unsatisfiable") {
    if (value.solution != null || value.limit_reason != null) return invalidResult("无解响应包含了不应出现的摆放或限额信息。");
    return <div className="notice warning" role="status">
      <strong>按这个题面没有解。</strong> 求解器已经穷尽当前规则下的全部合法摆放。
    </div>;
  }
  if (value.outcome === "timeout") {
    if (value.solution != null || (value.limit_reason !== "time" && value.limit_reason !== "work")) {
      return invalidResult("计算限额响应结构不完整。");
    }
    return <div className="notice warning" role="status">
      <strong>计算达到{value.limit_reason === "time" ? "时间" : "工作量"}上限。</strong> 搜索尚未穷尽，目前不能判断题面是否有解。
    </div>;
  }
  if (value.outcome !== "solved") return invalidResult("结果状态无法识别。");
  const checked = deriveCircuitAnswer(puzzle, value);
  if (!checked.answer) return invalidResult(`${checked.error} 未绘制答案。`);
  const { puzzle: normalized, cells, placements } = checked.answer;
  const palette = resolveCircuitDisplayPalette(normalized, displayPalette);
  if (palette.colors.length !== normalized.channels.length) {
    return invalidResult("显示颜色无法与题面对应，未绘制答案。");
  }
  const obstaclePatternId = `${svgId}-obstacle`;
  const placementDrawings = placements.map((placement) => ({
    placement,
    fill: circuitPieceFill(placement.cells),
    boundary: circuitPieceBoundarySegments(placement.cells),
  }));

  return <div className="circuit-solution">
    <p className="success-line">答案已校验。连续色块代表一个库存形状；菱形是固定格，斜纹是障碍。</p>
    <svg className="circuit-answer-svg" viewBox={`0 0 ${normalized.columns} ${normalized.rows}`}
      role="img" aria-label="源石电路完成棋盘" preserveAspectRatio="xMidYMid meet">
      <defs>
        <pattern id={obstaclePatternId} width="0.24" height="0.24" patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)">
          <rect width="0.24" height="0.24" fill="#29343d" />
          <rect width="0.08" height="0.24" fill="#66737d" />
        </pattern>
        {palette.colors.map((color) => <linearGradient key={color.channel}
          id={`${svgId}-color-${color.channel}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={color.highlight} />
          <stop offset="0.24" stopColor={color.fill} />
          <stop offset="1" stopColor={color.softFill} />
        </linearGradient>)}
        {placementDrawings.map(({ placement, fill }) => {
          const color = palette.colors[placement.channel];
          return <linearGradient key={placement.pieceIndex}
            id={`${svgId}-piece-${placement.pieceIndex}`}
            gradientUnits="userSpaceOnUse"
            x1={fill.bounds.x1} y1={fill.bounds.y1}
            x2={fill.bounds.x2} y2={fill.bounds.y2}>
            <stop offset="0" stopColor={color.highlight} />
            <stop offset="0.24" stopColor={color.fill} />
            <stop offset="1" stopColor={color.softFill} />
          </linearGradient>;
        })}
      </defs>

      <rect className="circuit-svg-frame" x="0" y="0" width={normalized.columns} height={normalized.rows} />
      {cells.map((cell) => <rect key={`base-${cell.row}-${cell.column}`}
        className="circuit-svg-cell" x={cell.column + 0.045} y={cell.row + 0.045}
        width="0.91" height="0.91" rx="0.08" />)}

      {cells.filter((cell) => cell.kind === "blocked").map((cell) => <g
        key={`blocked-${cell.row}-${cell.column}`} aria-label="障碍格">
        <rect x={cell.column + 0.08} y={cell.row + 0.08} width="0.84" height="0.84" rx="0.09"
          fill={`url(#${obstaclePatternId})`} className="circuit-svg-obstacle" />
        <path d={`M${cell.column + 0.28} ${cell.row + 0.28}L${cell.column + 0.72} ${cell.row + 0.72}M${cell.column + 0.72} ${cell.row + 0.28}L${cell.column + 0.28} ${cell.row + 0.72}`}
          className="circuit-svg-obstacle-cross" aria-hidden="true" />
      </g>)}

      {cells.filter((cell) => cell.kind === "fixed").map((cell) => {
        const color = palette.colors[cell.channel!];
        const centerX = cell.column + 0.5, centerY = cell.row + 0.5;
        return <g key={`fixed-${cell.row}-${cell.column}`}
          aria-label={`${color.name}固定格`}>
          <rect x={cell.column + 0.12} y={cell.row + 0.12} width="0.76" height="0.76" rx="0.13"
            fill={`url(#${svgId}-color-${color.channel})`} stroke={color.edge} strokeWidth="0.07" />
          <path d={`M${centerX} ${centerY - 0.22}L${centerX + 0.22} ${centerY}L${centerX} ${centerY + 0.22}L${centerX - 0.22} ${centerY}Z`}
            fill="none" stroke={color.highlight} strokeWidth="0.075" aria-hidden="true" />
          <circle cx={centerX} cy={centerY} r="0.07" fill={color.edge} aria-hidden="true" />
        </g>;
      })}

      {placementDrawings.map(({ placement, fill, boundary }) => {
        const color = palette.colors[placement.channel];
        const outline = boundary.map((segment) =>
          `M${segment.x1} ${segment.y1}L${segment.x2} ${segment.y2}`).join("");
        return <g key={placement.pieceIndex}
          data-circuit-placement={placement.pieceIndex}
          aria-label={`${color.name}，${placement.cells.length} 格库存形状`}>
          <path d={fill.pathData} fill={`url(#${svgId}-piece-${placement.pieceIndex})`}
            data-circuit-piece-fill="" aria-hidden="true" />
          <path d={outline} fill="none" stroke={color.edge} strokeWidth="0.095"
            strokeLinejoin="round" strokeLinecap="round" aria-hidden="true" />
          <path d={outline} fill="none" stroke={color.highlight} strokeWidth="0.025"
            strokeLinejoin="round" strokeLinecap="round" opacity="0.72" aria-hidden="true" />
        </g>;
      })}
      <rect className="circuit-svg-border" x="0.025" y="0.025"
        width={normalized.columns - 0.05} height={normalized.rows - 0.05} rx="0.08" />
    </svg>
  </div>;
}
