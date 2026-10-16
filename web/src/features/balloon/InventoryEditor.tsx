import { useAppTranslation } from "../../i18n";
import { IconButton } from "../../ui/IconButton/IconButton";
import { Button } from "../../ui/Button/Button";
import { CloseIcon, PlusIcon } from "../../ui/icons";
import { MAX_KINDS, inventorySum, type BalloonDraft, type DraftProblem, type StockDraft } from "./draft";
import s from "./balloon.module.css";

const parse = (text: string): number | null => text.trim() === "" ? null : Number(text);

/** Rows with problems, for marking the matching inputs. */
function rowProblems(problems: DraftProblem[]) {
  const lift = new Set<number>(), count = new Set<number>();
  for (const problem of problems) {
    if ("row" in problem) {
      if (problem.kind.startsWith("lift")) lift.add(problem.row); else count.add(problem.row);
    }
  }
  return { lift, count };
}

/** Balloon inventory: editable rows of lift × count, or read-only chips. */
export function InventoryEditor({ draft, editable, problems = [], onChange, onTargetChange }: {
  draft: BalloonDraft;
  editable: boolean;
  problems?: DraftProblem[];
  onChange?: (inventory: StockDraft[]) => void;
  /** The target only checks the inventory; clearing it skips the check. */
  onTargetChange?: (target: number | null) => void;
}) {
  const { t } = useAppTranslation("balloon");
  const { balloons, lift } = inventorySum(draft);
  const marked = rowProblems(problems);
  const complete = draft.inventory.every((item) => item.lift !== null && item.count !== null);
  const targetState = draft.target === null || !complete ? null : lift === draft.target ? "ok" : "mismatch";
  const update = (row: number, patch: Partial<StockDraft>) =>
    onChange?.(draft.inventory.map((item, index) => index === row ? { ...item, ...patch } : item));

  const verdict = targetState === "ok" ? t("editor.targetOk") : targetState === "mismatch" ? t("editor.targetMismatch") : "";
  const summary = <p className={s.summary}>
    <span>{t("editor.summary", { balloons, lift })}</span>
    {!editable && draft.target !== null && <span className={s.target} data-state={targetState ?? undefined}>
      {t("editor.target", { target: draft.target })}{verdict && ` · ${verdict}`}
    </span>}
  </p>;

  if (!editable) {
    return <div className={s.inventory}>
      <ul className={s.chips}>
        {draft.inventory.map((item, row) => <li key={row} className={s.chip}>
          <span className={s.chipLift}>{t("editor.liftValue", { lift: item.lift ?? "?" })}</span>
          <span className={s.chipCount}>× {item.count ?? "?"}</span>
        </li>)}
      </ul>
      {summary}
    </div>;
  }

  return <div className={s.inventory}>
    <div className={s.stockHead} aria-hidden="true"><span>{t("editor.lift")}</span><span /><span>{t("editor.count")}</span><span /></div>
    <ul className={s.stockList}>
      {draft.inventory.map((item, row) => <li key={row} className={s.stockRow}>
        <input className={s.input} type="number" inputMode="numeric" min={1} max={100}
          aria-label={t("editor.liftAria", { row: row + 1 })} aria-invalid={marked.lift.has(row) || undefined}
          value={item.lift ?? ""} onChange={(event) => update(row, { lift: parse(event.target.value) })} />
        <span className={s.times} aria-hidden="true">×</span>
        <input className={s.input} type="number" inputMode="numeric" min={1} max={18}
          aria-label={t("editor.countAria", { row: row + 1 })} aria-invalid={marked.count.has(row) || undefined}
          value={item.count ?? ""} onChange={(event) => update(row, { count: parse(event.target.value) })} />
        <IconButton label={t("editor.removeStock", { row: row + 1 })} icon={<CloseIcon />}
          onClick={() => onChange?.(draft.inventory.filter((_, index) => index !== row))} />
      </li>)}
    </ul>
    <Button variant="secondary" size="sm" icon={<PlusIcon />} disabled={draft.inventory.length >= MAX_KINDS}
      onClick={() => onChange?.([...draft.inventory, { lift: null, count: null }])}>{t("editor.addStock")}</Button>
    {summary}
    <label className={s.targetRow}>
      <span>{t("editor.targetLabel")}</span>
      <input className={s.input} type="number" inputMode="numeric" min={1}
        aria-invalid={targetState === "mismatch" || undefined} value={draft.target ?? ""}
        onChange={(event) => onTargetChange?.(parse(event.target.value))} />
      {verdict && <span className={s.target} data-state={targetState ?? undefined}>{verdict}</span>}
    </label>
    <p className={s.note}>{t("editor.targetNote")}</p>
  </div>;
}
