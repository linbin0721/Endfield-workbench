import { useId } from "react";
import type { CircuitPuzzle, CircuitSolveResult } from "../../api";
import { deriveCircuitAnswer } from "../../circuit";
import { circuitPieceBoundarySegments, circuitPieceFill } from "../../circuitDisplay";
import { msg, useAppTranslation, useMessages, type MessageText } from "../../i18n";
import { Notice } from "../../ui/Notice/Notice";
import { SuccessGlow, SuccessReveal } from "../../ui/SuccessReveal/SuccessReveal";
import { useChangeCount } from "../../ui/useChangeCount";
import { colorName, useCircuitColors } from "./colors";
import c from "./circuit.module.css";

export type Solved = {
  puzzle: CircuitPuzzle;
  palette: unknown;
  result: CircuitSolveResult;
  source: MessageText;
  /** Stable source id for diagnostics (data-answer-source on the answer panel). */
  sourceKey: "screenshot" | "edited" | "code" | "candidate";
  /** Solved from the puzzle shown in the editor, so later edits make it stale. */
  fromDraft: boolean;
};

/**
 * The solved board, drawn only after deriveCircuitAnswer has rebuilt and
 * checked every placement against the puzzle. A stale answer is dimmed.
 */
export function CircuitAnswer({ solved, stale }: { solved: Solved; stale: boolean }) {
  const { t } = useAppTranslation("circuit");
  const { t: tc } = useAppTranslation("common");
  const { render, tm } = useMessages();
  const playKey = useChangeCount(solved.result);
  const svgId = useId().replace(/:/g, "");
  const { colors } = useCircuitColors(solved.puzzle.channels.length, solved.palette);
  const source = <p className={c.answerSource}>{t("workbench.answerSource", { source: render(solved.source) })}</p>;
  const invalid = (message: MessageText) => <Notice tone="danger" role="alert" title={t("result.invalidTitle")}>{tm(message, "error")}</Notice>;
  const value = solved.result;
  if (value === null || typeof value !== "object" || Array.isArray(value)) return invalid(t("result.structureUnknown"));
  if (value.rule_version !== "line-count-v1") return invalid(t("result.ruleMismatch"));
  if (value.outcome === "unsatisfiable") {
    if (value.solution != null || value.limit_reason != null) return invalid(t("result.unsatisfiableInvalid"));
    return <div className={c.answer}><Notice tone="warning" role="status" title={t("result.unsatisfiable")} />{source}</div>;
  }
  if (value.outcome === "timeout") {
    if (value.solution != null || (value.limit_reason !== "time" && value.limit_reason !== "work")) return invalid(t("result.timeoutInvalid"));
    return <div className={c.answer}>
      <Notice tone="warning" role="status" title={t("result.timeout", { limit: t(value.limit_reason === "time" ? "result.limitTime" : "result.limitWork") })} />
      {source}
    </div>;
  }
  if (value.outcome !== "solved") return invalid(t("result.outcomeUnknown"));
  const checked = deriveCircuitAnswer(solved.puzzle, value);
  if (!checked.answer) return invalid(msg("result.notDrawn", { message: checked.error }, "circuit"));
  const { puzzle, cells, placements } = checked.answer;
  if (colors.length !== puzzle.channels.length) return invalid(t("result.paletteMismatch"));
  const obstacleId = `${svgId}-obstacle`;
  const drawings = placements.map((placement) => ({
    placement,
    fill: circuitPieceFill(placement.cells),
    boundary: circuitPieceBoundarySegments(placement.cells),
  }));

  return <div className={c.answer} data-solution="circuit" data-stale={stale || undefined}>
    {stale
      ? <Notice tone="warning" role="status">{t("workbench.staleAnswer")}</Notice>
      : <SuccessReveal key={playKey} title={tc("puzzle.solved")} />}
    {source}
    <SuccessGlow playKey={stale ? 0 : playKey}>
      <svg key={playKey} className={c.answerSvg} data-answer-board="circuit" viewBox={`-0.1 -0.1 ${puzzle.columns + 0.2} ${puzzle.rows + 0.2}`}
        role="img" aria-label={t("result.boardAria")} preserveAspectRatio="xMidYMid meet">
        <defs>
          <pattern id={obstacleId} width="0.24" height="0.24" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="0.24" height="0.24" className={c.svgObstacleBase} />
            <rect width="0.08" height="0.24" className={c.svgObstacleStripe} />
          </pattern>
          {colors.map((color) => <linearGradient key={color.channel} id={`${svgId}-color-${color.channel}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={color.highlight} />
            <stop offset="0.24" stopColor={color.fill} />
            <stop offset="1" stopColor={color.softFill} />
          </linearGradient>)}
          {drawings.map(({ placement, fill }) => {
            const color = colors[placement.channel];
            return <linearGradient key={placement.pieceIndex} id={`${svgId}-piece-${placement.pieceIndex}`} gradientUnits="userSpaceOnUse"
              x1={fill.bounds.x1} y1={fill.bounds.y1} x2={fill.bounds.x2} y2={fill.bounds.y2}>
              <stop offset="0" stopColor={color.highlight} />
              <stop offset="0.24" stopColor={color.fill} />
              <stop offset="1" stopColor={color.softFill} />
            </linearGradient>;
          })}
        </defs>
        <rect className={c.svgFrame} x="0" y="0" width={puzzle.columns} height={puzzle.rows} />
        {cells.map((cell) => <rect key={`base-${cell.row}-${cell.column}`} className={c.svgCell}
          x={cell.column + 0.045} y={cell.row + 0.045} width="0.91" height="0.91" rx="0.08" />)}
        {cells.filter((cell) => cell.kind === "blocked").map((cell) => <g key={`blocked-${cell.row}-${cell.column}`} aria-label={t("preview.blocked")}>
          <rect x={cell.column + 0.08} y={cell.row + 0.08} width="0.84" height="0.84" rx="0.09" fill={`url(#${obstacleId})`} className={c.svgObstacle} />
          <path d={`M${cell.column + 0.28} ${cell.row + 0.28}L${cell.column + 0.72} ${cell.row + 0.72}M${cell.column + 0.72} ${cell.row + 0.28}L${cell.column + 0.28} ${cell.row + 0.72}`}
            className={c.svgObstacleCross} aria-hidden="true" />
        </g>)}
        {cells.filter((cell) => cell.kind === "fixed").map((cell) => {
          const color = colors[cell.channel!];
          const x = cell.column + 0.5, y = cell.row + 0.5;
          return <g key={`fixed-${cell.row}-${cell.column}`} aria-label={t("preview.fixed", { color: colorName(t, color) })}>
            <rect x={cell.column + 0.12} y={cell.row + 0.12} width="0.76" height="0.76" rx="0.13"
              fill={`url(#${svgId}-color-${color.channel})`} stroke={color.edge} strokeWidth="0.07" />
            <path d={`M${x} ${y - 0.22}L${x + 0.22} ${y}L${x} ${y + 0.22}L${x - 0.22} ${y}Z`} fill="none" stroke={color.highlight} strokeWidth="0.075" aria-hidden="true" />
            <circle cx={x} cy={y} r="0.07" fill={color.edge} aria-hidden="true" />
          </g>;
        })}
        {drawings.map(({ placement, fill, boundary }, order) => {
          const color = colors[placement.channel];
          const outline = boundary.map((segment) => `M${segment.x1} ${segment.y1}L${segment.x2} ${segment.y2}`).join("");
          return <g key={placement.pieceIndex} className={c.placed} style={{ animationDelay: `${order * 70}ms` }}
            data-circuit-placement={placement.pieceIndex}
            aria-label={t("preview.pieceAria", { color: colorName(t, color), cells: placement.cells.length })}>
            <path d={fill.pathData} fill={`url(#${svgId}-piece-${placement.pieceIndex})`} data-circuit-piece-fill="" aria-hidden="true" />
            <path d={outline} fill="none" stroke={color.edge} strokeWidth="0.095" strokeLinejoin="round" strokeLinecap="round" aria-hidden="true" />
            <path d={outline} fill="none" stroke={color.highlight} strokeWidth="0.025" strokeLinejoin="round" strokeLinecap="round" opacity="0.72" aria-hidden="true" />
          </g>;
        })}
        <rect className={c.svgBorder} x="0.025" y="0.025" width={puzzle.columns - 0.05} height={puzzle.rows - 0.05} rx="0.08" />
      </svg>
    </SuccessGlow>
    <p className={c.answerNote}>{t("result.success")}</p>
  </div>;
}
