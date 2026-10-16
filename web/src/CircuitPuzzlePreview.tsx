import type { TFunction } from "i18next";
import type { CircuitPuzzle } from "./api";
import { useAppTranslation, useMessages } from "./i18n";
import { validateCircuitPuzzle } from "./circuit";
import { circuitColorOnSurface } from "./features/puzzles/circuitTheme";
import { cx } from "./features/puzzles/PuzzleParts";
import s from "./features/puzzles/puzzles.module.css";
import { useSurface } from "./ui/surface";
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

/**
 * Circuit color names come from circuitDisplay.ts as canonical Chinese strings.
 * They are normalized here, at the display boundary, so the calculation palette
 * and its channel mapping stay untouched.
 */
const colorKeys: Record<string, string> = {
  "红色": "colors.red",
  "橙色": "colors.orange",
  "黄色": "colors.yellow",
  "绿色": "colors.green",
  "青色": "colors.cyan",
  "蓝色": "colors.blue",
  "紫色": "colors.purple",
  "品红色": "colors.magenta",
  "未知颜色": "colors.unknown",
};

export function circuitColorLabel(t: TFunction, name: string): string {
  const key = colorKeys[name];
  return t(key ?? "colors.unknown");
}

export function CircuitColorToken({ color }: { color: CircuitDisplayColor }) {
  const { t } = useAppTranslation("circuit");
  return <span className={s.colorToken} style={circuitColorStyle(color)}>
    <i className={cx(s.swatch, s.pattern)} data-circuit-pattern={color.channel} aria-hidden="true" />
    {circuitColorLabel(t, color.name)}
  </span>;
}

export function CircuitPieceShape({ cells, color }: PieceShapeProps) {
  const rows = Math.max(...cells.map((cell) => cell.row)) + 1;
  const columns = Math.max(...cells.map((cell) => cell.column)) + 1;
  const occupied = new Set(cells.map((cell) => `${cell.row},${cell.column}`));
  return <span className={s.pieceShape}
    style={{ ...circuitColorStyle(color), gridTemplateColumns: `repeat(${columns}, 0.72rem)` }}
    aria-hidden="true">
    {Array.from({ length: rows * columns }, (_, index) => {
      const row = Math.floor(index / columns), column = index % columns;
      const filled = occupied.has(`${row},${column}`);
      return <i key={`${row},${column}`} className={filled ? s.pattern : undefined}
        data-circuit-pattern={filled ? color.channel : undefined} data-filled={filled} />;
    })}
  </span>;
}

export default function CircuitPuzzlePreview({ puzzle: value, displayPalette, compact = false }: Props) {
  const { t } = useAppTranslation("circuit");
  const { tm } = useMessages();
  const surface = useSurface();
  const checked = validateCircuitPuzzle(value);
  if (!checked.puzzle) return <p className={s.errorText} role="alert">{tm(checked.error, "error")}</p>;
  const puzzle = checked.puzzle;
  const palette = resolveCircuitDisplayPalette(puzzle, displayPalette);
  const colors = palette.colors.map((color) => circuitColorOnSurface(color, surface));
  const blocked = new Set((puzzle.blocked_cells ?? []).map((cell) => `${cell.row},${cell.column}`));
  const fixed = new Map((puzzle.fixed_cells ?? []).map((cell) => [`${cell.row},${cell.column}`, cell.channel]));
  return <div className={cx(s.circuitPreview, compact && s.compact)}>
    <div className={s.targets} aria-label={t("preview.targetsLabel")}>
      {puzzle.channels.map((channel) => {
        const color = colors[channel.index];
        return <div className={s.target} key={channel.index}>
          <CircuitColorToken color={color} />
          <span><b>{t("preview.row")}</b> {channel.row_targets.join(" · ")}</span>
          <span><b>{t("preview.column")}</b> {channel.column_targets.join(" · ")}</span>
        </div>;
      })}
    </div>
    <div className={s.previewBody}>
      <div>
        <p className={s.previewLabel}>{t("preview.boardSize", { rows: puzzle.rows, columns: puzzle.columns })}</p>
        <div className={s.circuitBoard} style={{ gridTemplateColumns: `repeat(${puzzle.columns}, minmax(0, 1fr))` }}>
          {Array.from({ length: puzzle.rows * puzzle.columns }, (_, index) => {
            const row = Math.floor(index / puzzle.columns), column = index % puzzle.columns;
            const key = `${row},${column}`, channel = fixed.get(key);
            const kind = blocked.has(key) ? "blocked" : channel != null ? "fixed" : "empty";
            const color = channel != null ? colors[channel] : null;
            const label = kind === "blocked" ? t("preview.blocked")
              : color ? t("preview.fixed", { color: circuitColorLabel(t, color.name) }) : t("preview.empty");
            return <span key={key} className={cx(s.circuitCell, color && s.pattern)} data-cell={kind}
              style={color ? circuitColorStyle(color) : undefined}
              data-circuit-pattern={color?.channel}
              aria-label={label}>
              {kind === "blocked" ? <i className={s.obstacleMark} aria-hidden="true" />
                : color ? <i className={s.fixedMark} aria-hidden="true" /> : null}
            </span>;
          })}
        </div>
      </div>
      <div>
        <p className={s.previewLabel}>{t("preview.piecesLabel", { count: puzzle.pieces.length })}</p>
        <div className={s.pieceList}>
          {puzzle.pieces.map((piece, index) => {
            const color = colors[piece.channel];
            return <div className={s.piece} key={index}
              aria-label={t("preview.pieceAria", { color: circuitColorLabel(t, color.name), cells: piece.cells.length })}>
              <CircuitPieceShape cells={piece.cells} color={color} />
              <CircuitColorToken color={color} />
              <small className={s.pieceCount}>{t("preview.cellCount", { cells: piece.cells.length })}</small>
            </div>;
          })}
        </div>
      </div>
    </div>
    <div className={s.colorLegend} aria-label={t("preview.legendLabel")}>
      <span className={cx(s.legendItem, s.legendBlocked)}>{t("preview.legendBlocked")}</span>
      <span className={s.legendItem}>{t("preview.legendFixed")}</span>
      {palette.usedFallback && <span>{t("preview.fallbackColors")}</span>}
    </div>
  </div>;
}
