import { useId } from "react";
import { circuitPieceBoundarySegments, circuitPieceFill, type CircuitDisplayColor, type CircuitDisplayPoint } from "../../circuitDisplay";
import { useAppTranslation } from "../../i18n";
import { colorName } from "./colors";
import type { DraftPiece } from "./draft";
import c from "./circuit.module.css";

/** One inventory shape drawn like the placed pieces: one gradient fill and its outer outline. */
export function PieceShape({ cells, color }: { cells: readonly CircuitDisplayPoint[]; color: CircuitDisplayColor }) {
  const id = useId().replace(/:/g, "");
  const fill = circuitPieceFill(cells);
  const outline = circuitPieceBoundarySegments(cells).map((segment) =>
    `M${segment.x1} ${segment.y1}L${segment.x2} ${segment.y2}`).join("");
  const pad = 0.14;
  const width = fill.bounds.x2 - fill.bounds.x1, height = fill.bounds.y2 - fill.bounds.y1;
  return <svg className={c.pieceSvg} style={{ width: `${(width + pad * 2) * 1.05}rem` }}
    viewBox={`${fill.bounds.x1 - pad} ${fill.bounds.y1 - pad} ${width + pad * 2} ${height + pad * 2}`} aria-hidden="true">
    <defs>
      <linearGradient id={`${id}-fill`} gradientUnits="userSpaceOnUse"
        x1={fill.bounds.x1} y1={fill.bounds.y1} x2={fill.bounds.x2} y2={fill.bounds.y2}>
        <stop offset="0" stopColor={color.highlight} />
        <stop offset="0.24" stopColor={color.fill} />
        <stop offset="1" stopColor={color.softFill} />
      </linearGradient>
    </defs>
    <path d={fill.pathData} fill={`url(#${id}-fill)`} />
    <path d={outline} fill="none" stroke={color.edge} strokeWidth="0.095" strokeLinejoin="round" strokeLinecap="round" />
    <path d={outline} fill="none" stroke={color.highlight} strokeWidth="0.025" strokeLinejoin="round" strokeLinecap="round" opacity="0.72" />
  </svg>;
}

/** The inventory pieces; they are recognized as a whole and never edited. */
export function CircuitPieces({ pieces, colors, compact = false }: {
  pieces: readonly DraftPiece[];
  colors: CircuitDisplayColor[];
  compact?: boolean;
}) {
  const { t } = useAppTranslation("circuit");
  return <ul className={c.pieces} data-compact={compact || undefined} aria-label={t("preview.piecesLabel", { count: pieces.length })}>
    {pieces.map((piece, index) => {
      const color = colors[piece.channel];
      if (!color) return null;
      return <li key={index} className={c.piece} aria-label={t("preview.pieceAria", { color: colorName(t, color), cells: piece.cells.length })}>
        <PieceShape cells={piece.cells} color={color} />
        {!compact && <small>{t("preview.cellCount", { cells: piece.cells.length })}</small>}
      </li>;
    })}
  </ul>;
}
