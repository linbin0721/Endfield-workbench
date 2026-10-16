import { useId } from "react";
import type { CircuitPuzzle, CircuitSolveResult } from "./api";
import { msg, useAppTranslation, useMessages, type MessageText } from "./i18n";
import { deriveCircuitAnswer } from "./circuit";
import {
  circuitPieceBoundarySegments,
  circuitPieceFill,
  resolveCircuitDisplayPalette,
} from "./circuitDisplay";
import { circuitColorLabel } from "./CircuitPuzzlePreview";
import { circuitColorOnSurface } from "./features/puzzles/circuitTheme";
import s from "./features/puzzles/puzzles.module.css";
import { useChangeCount } from "./features/puzzles/useChangeCount";
import { Notice } from "./ui/Notice/Notice";
import { SuccessGlow, SuccessReveal } from "./ui/SuccessReveal/SuccessReveal";
import { useSurface } from "./ui/surface";

type Props = {
  puzzle: CircuitPuzzle | unknown;
  displayPalette?: unknown;
  result: CircuitSolveResult;
};

export default function CircuitResult({ puzzle, displayPalette, result }: Props) {
  const { t } = useAppTranslation("circuit");
  const { t: tc } = useAppTranslation("common");
  const { tm } = useMessages();
  const surface = useSurface();
  const playKey = useChangeCount(result);
  const svgId = useId().replace(/:/g, "");
  const invalidResult = (message: MessageText) => <Notice tone="danger" role="alert" title={t("result.invalidTitle")}>
    {tm(message, "error")}
  </Notice>;
  if (result === null || typeof result !== "object" || Array.isArray(result)) {
    return invalidResult(t("result.structureUnknown"));
  }
  const value = result as Partial<CircuitSolveResult>;
  if (value.rule_version !== "line-count-v1") return invalidResult(t("result.ruleMismatch"));
  if (value.outcome === "unsatisfiable") {
    if (value.solution != null || value.limit_reason != null) return invalidResult(t("result.unsatisfiableInvalid"));
    return <Notice tone="warning" role="status" title={t("result.unsatisfiable")} />;
  }
  if (value.outcome === "timeout") {
    if (value.solution != null || (value.limit_reason !== "time" && value.limit_reason !== "work")) {
      return invalidResult(t("result.timeoutInvalid"));
    }
    return <Notice tone="warning" role="status"
      title={t("result.timeout", { limit: t(value.limit_reason === "time" ? "result.limitTime" : "result.limitWork") })} />;
  }
  if (value.outcome !== "solved") return invalidResult(t("result.outcomeUnknown"));
  const checked = deriveCircuitAnswer(puzzle, value);
  if (!checked.answer) return invalidResult(msg("result.notDrawn", { message: checked.error }, "circuit"));
  const { puzzle: normalized, cells, placements } = checked.answer;
  const palette = resolveCircuitDisplayPalette(normalized, displayPalette);
  if (palette.colors.length !== normalized.channels.length) {
    return invalidResult(t("result.paletteMismatch"));
  }
  const colors = palette.colors.map((color) => circuitColorOnSurface(color, surface));
  const obstaclePatternId = `${svgId}-obstacle`;
  const placementDrawings = placements.map((placement) => ({
    placement,
    fill: circuitPieceFill(placement.cells),
    boundary: circuitPieceBoundarySegments(placement.cells),
  }));

  return <div className={s.answer} data-solution="circuit">
    <SuccessReveal key={playKey} title={tc("puzzle.solved")} />
    <p className={s.note}>{t("result.success")}</p>
    <SuccessGlow playKey={playKey}>
    <svg className={s.circuitAnswer} data-answer-board="circuit" viewBox={`0 0 ${normalized.columns} ${normalized.rows}`}
      role="img" aria-label={t("result.boardAria")} preserveAspectRatio="xMidYMid meet">
      <defs>
        <pattern id={obstaclePatternId} width="0.24" height="0.24" patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)">
          <rect width="0.24" height="0.24" className={s.svgObstacleBase} />
          <rect width="0.08" height="0.24" className={s.svgObstacleStripe} />
        </pattern>
        {colors.map((color) => <linearGradient key={color.channel}
          id={`${svgId}-color-${color.channel}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={color.highlight} />
          <stop offset="0.24" stopColor={color.fill} />
          <stop offset="1" stopColor={color.softFill} />
        </linearGradient>)}
        {placementDrawings.map(({ placement, fill }) => {
          const color = colors[placement.channel];
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

      <rect className={s.svgFrame} x="0" y="0" width={normalized.columns} height={normalized.rows} />
      {cells.map((cell) => <rect key={`base-${cell.row}-${cell.column}`}
        className={s.svgCell} x={cell.column + 0.045} y={cell.row + 0.045}
        width="0.91" height="0.91" rx="0.08" />)}

      {cells.filter((cell) => cell.kind === "blocked").map((cell) => <g
        key={`blocked-${cell.row}-${cell.column}`} aria-label={t("preview.blocked")}>
        <rect x={cell.column + 0.08} y={cell.row + 0.08} width="0.84" height="0.84" rx="0.09"
          fill={`url(#${obstaclePatternId})`} className={s.svgObstacle} />
        <path d={`M${cell.column + 0.28} ${cell.row + 0.28}L${cell.column + 0.72} ${cell.row + 0.72}M${cell.column + 0.72} ${cell.row + 0.28}L${cell.column + 0.28} ${cell.row + 0.72}`}
          className={s.svgObstacleCross} aria-hidden="true" />
      </g>)}

      {cells.filter((cell) => cell.kind === "fixed").map((cell) => {
        const color = colors[cell.channel!];
        const centerX = cell.column + 0.5, centerY = cell.row + 0.5;
        return <g key={`fixed-${cell.row}-${cell.column}`}
          aria-label={t("preview.fixed", { color: circuitColorLabel(t, color.name) })}>
          <rect x={cell.column + 0.12} y={cell.row + 0.12} width="0.76" height="0.76" rx="0.13"
            fill={`url(#${svgId}-color-${color.channel})`} stroke={color.edge} strokeWidth="0.07" />
          <path d={`M${centerX} ${centerY - 0.22}L${centerX + 0.22} ${centerY}L${centerX} ${centerY + 0.22}L${centerX - 0.22} ${centerY}Z`}
            fill="none" stroke={color.highlight} strokeWidth="0.075" aria-hidden="true" />
          <circle cx={centerX} cy={centerY} r="0.07" fill={color.edge} aria-hidden="true" />
        </g>;
      })}

      {placementDrawings.map(({ placement, fill, boundary }) => {
        const color = colors[placement.channel];
        const outline = boundary.map((segment) =>
          `M${segment.x1} ${segment.y1}L${segment.x2} ${segment.y2}`).join("");
        return <g key={placement.pieceIndex}
          data-circuit-placement={placement.pieceIndex}
          aria-label={t("preview.pieceAria", { color: circuitColorLabel(t, color.name), cells: placement.cells.length })}>
          <path d={fill.pathData} fill={`url(#${svgId}-piece-${placement.pieceIndex})`}
            data-circuit-piece-fill="" aria-hidden="true" />
          <path d={outline} fill="none" stroke={color.edge} strokeWidth="0.095"
            strokeLinejoin="round" strokeLinecap="round" aria-hidden="true" />
          <path d={outline} fill="none" stroke={color.highlight} strokeWidth="0.025"
            strokeLinejoin="round" strokeLinecap="round" opacity="0.72" aria-hidden="true" />
        </g>;
      })}
      <rect className={s.svgBorder} x="0.025" y="0.025"
        width={normalized.columns - 0.05} height={normalized.rows - 0.05} rx="0.08" />
    </svg>
    </SuccessGlow>
  </div>;
}
