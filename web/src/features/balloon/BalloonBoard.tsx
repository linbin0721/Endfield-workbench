import type { CSSProperties } from "react";
import { useAppTranslation } from "../../i18n";
import type { BalloonDraft } from "./draft";
import s from "./balloon.module.css";

type BoardProps = {
  draft: BalloonDraft;
  /** view: read-only; edit: cells toggle; answer: lifts drawn on the placed cells. */
  mode: "view" | "edit" | "answer";
  /** Lift per cell ("row,column") for the answer. */
  lifts?: ReadonlyMap<string, number>;
  onToggle?: (index: number) => void;
  size?: "md" | "sm";
};

/** The balloon board in the game's layout; unknown cells are marked until set. */
export function BalloonBoard({ draft, mode, lifts, onToggle, size = "md" }: BoardProps) {
  const { t } = useAppTranslation("balloon");
  return <div className={s.board} data-size={size} data-answer-board={mode === "answer" ? "balloon" : undefined}
    style={{ gridTemplateColumns: `repeat(${draft.columns}, minmax(0, 1fr))` }}>
    {draft.cells.map((kind, index) => {
      const row = Math.floor(index / draft.columns), column = index % draft.columns;
      const lift = lifts?.get(`${row},${column}`);
      const cell = kind === null ? "unknown" : kind === "blocked" ? "blocked" : lift != null ? "filled" : "empty";
      const state = kind === null ? t("editor.cellUnknown") : kind === "blocked" ? t("result.cellBlocked")
        : lift != null ? t("result.cellFilled", { lift }) : mode === "answer" ? t("result.cellEmpty") : t("editor.cellUsable");
      const label = t("result.cellAria", { row: row + 1, column: column + 1, state });
      if (mode === "edit") {
        return <button key={index} type="button" className={s.cell} data-cell={cell} aria-label={`${label} · ${t("editor.toggleHint")}`}
          onClick={() => onToggle?.(index)}>
          {kind === null && <span className={s.unknown} aria-hidden="true">?</span>}
        </button>;
      }
      return <div key={index} className={s.cell} data-cell={cell} role="img" aria-label={label}
        style={lift != null ? { "--i": index } as CSSProperties : undefined}>
        {lift != null && <strong className={s.lift}>{lift}</strong>}
        {kind === null && <span className={s.unknown} aria-hidden="true">?</span>}
      </div>;
    })}
  </div>;
}
