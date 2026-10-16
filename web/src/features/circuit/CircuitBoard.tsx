import type { CSSProperties } from "react";
import type { TFunction } from "i18next";
import { useAppTranslation } from "../../i18n";
import type { CircuitDisplayColor } from "../../circuitDisplay";
import { colorName } from "./colors";
import type { CircuitDraft, DraftCell } from "./draft";
import c from "./circuit.module.css";

type Axis = "row" | "column";
type BoardProps = {
  draft: CircuitDraft;
  colors: CircuitDisplayColor[];
  mode: "view" | "edit";
  /** Channel whose targets are edited and which new fixed cells take (edit mode). */
  activeChannel?: number;
  size?: "md" | "sm";
  onCell?: (index: number) => void;
  onTarget?: (channel: number, axis: Axis, index: number, value: number | null) => void;
};

const chipStyle = (color: CircuitDisplayColor) => ({ "--chip-bg": color.fill, "--chip-fg": color.edge }) as CSSProperties;
const parse = (text: string): number | null => text.trim() === "" ? null : Number(text);

function cellLabel(cell: DraftCell, colors: CircuitDisplayColor[], t: TFunction) {
  if (cell.kind === null) return t("editor.cellUnknown");
  if (cell.kind === "blocked") return t("preview.blocked");
  if (cell.kind === "fixed") {
    const color = cell.channel !== null ? colors[cell.channel] : undefined;
    return color ? t("preview.fixed", { color: colorName(t, color) }) : t("editor.fixedNoChannel");
  }
  return t("preview.empty");
}

/**
 * The board as in the game: column targets above, row targets on the left,
 * one colour per channel. In edit mode only the active channel's targets are
 * shown, as inputs, and cells are buttons.
 */
export function CircuitBoard({ draft, colors, mode, activeChannel = 0, size = "md", onCell, onTarget }: BoardProps) {
  const { t } = useAppTranslation("circuit");
  const editing = mode === "edit";
  const shown = editing ? draft.channels.filter((channel) => channel.index === activeChannel) : draft.channels;
  const target = (channel: (typeof shown)[number], axis: Axis, index: number) => {
    const color = colors[channel.index];
    const value = (axis === "row" ? channel.row_targets : channel.column_targets)[index];
    const label = t(axis === "row" ? "editor.rowTarget" : "editor.columnTarget", { color: color ? colorName(t, color) : "", index: index + 1 });
    if (editing) {
      const limit = axis === "row" ? draft.columns : draft.rows;
      const invalid = value === null || !Number.isInteger(value) || value < 0 || value > limit;
      return <input key={channel.index} className={c.targetInput} type="number" inputMode="numeric" min={0} max={limit}
        aria-label={label} aria-invalid={invalid || undefined} value={value ?? ""} style={color ? chipStyle(color) : undefined}
        onChange={(event) => onTarget?.(channel.index, axis, index, parse(event.target.value))} />;
    }
    return <span key={channel.index} className={c.target} data-missing={value === null || undefined}
      style={color ? chipStyle(color) : undefined} aria-label={`${label} ${value ?? "?"}`}>{value ?? "?"}</span>;
  };
  return <div className={c.board} data-size={size} data-mode={mode}
    style={{ gridTemplateColumns: `auto repeat(${draft.columns}, minmax(0, 1fr))` }}>
    <span className={c.corner} aria-hidden="true" />
    {Array.from({ length: draft.columns }, (_, column) => <div key={`c${column}`} className={c.columnHead}>
      {shown.map((channel) => target(channel, "column", column))}
    </div>)}
    {Array.from({ length: draft.rows }, (_, row) => [
      <div key={`r${row}`} className={c.rowHead}>{shown.map((channel) => target(channel, "row", row))}</div>,
      ...Array.from({ length: draft.columns }, (_, column) => {
        const index = row * draft.columns + column;
        const cell = draft.cells[index];
        const color = cell.kind === "fixed" && cell.channel !== null ? colors[cell.channel] : undefined;
        const state = cell.kind === null ? "unknown" : cell.kind === "fixed" && !color ? "fixedUnknown" : cell.kind;
        const label = t("editor.cellAria", { row: row + 1, column: column + 1, state: cellLabel(cell, colors, t) });
        const mark = <span className={c.mark} aria-hidden="true">{state === "unknown" || state === "fixedUnknown" ? "?" : null}</span>;
        const style = color ? { "--cell-color": color.fill, "--cell-edge": color.edge, "--cell-light": color.highlight } as CSSProperties : undefined;
        return editing
          ? <button key={index} type="button" className={c.cell} data-cell={state} style={style}
            aria-label={`${label} · ${t("editor.cellHint")}`} onClick={() => onCell?.(index)}>{mark}</button>
          : <span key={index} className={c.cell} data-cell={state} style={style} role="img" aria-label={label}>{mark}</span>;
      }),
    ])}
  </div>;
}
