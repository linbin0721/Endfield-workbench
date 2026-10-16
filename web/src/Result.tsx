import { useChangeCount } from "./features/puzzles/useChangeCount";
import s from "./features/puzzles/puzzles.module.css";
import { useAppTranslation } from "./i18n";
import type { BalloonPuzzle, BalloonSolveResult } from "./puzzle";
import { Notice } from "./ui/Notice/Notice";
import { SuccessGlow, SuccessReveal } from "./ui/SuccessReveal/SuccessReveal";

type Props = { puzzle: BalloonPuzzle; result: BalloonSolveResult };

export default function Result({ puzzle, result }: Props) {
  const { t } = useAppTranslation("balloon");
  const { t: tc } = useAppTranslation("common");
  const playKey = useChangeCount(result);
  if (result.outcome === "unsatisfiable") return <Notice tone="warning" role="status" title={t("result.unsatisfiableTitle")}>
    {t("result.unsatisfiableBody")}
  </Notice>;
  if (result.outcome === "timeout") return <Notice tone="warning" role="status"
    title={t("result.timeoutTitle", { limit: t(result.limit_reason === "time" ? "result.limitTime" : "result.limitWork") })}>
    {t("result.timeoutBody")}
  </Notice>;
  const solution = result.solution;
  if (!solution) return <Notice tone="warning">{t("result.noSolution")}</Notice>;
  const usable = new Set(puzzle.usable_cells.map((cell) => `${cell.row},${cell.column}`));
  const placed = new Map(solution.placements.map((item) => [`${item.row},${item.column}`, item.lift]));
  return <div className={s.answer} data-solution="balloon">
    <SuccessReveal key={playKey} title={tc("puzzle.solved")} />
    <p className={s.note}>{t("result.found")}</p>
    <SuccessGlow playKey={playKey}>
      <div className={s.board} data-answer-board="balloon" style={{ gridTemplateColumns: `repeat(${puzzle.columns}, minmax(0, 1fr))` }}>
        {Array.from({ length: puzzle.rows * puzzle.columns }, (_, index) => {
          const row = Math.floor(index / puzzle.columns), column = index % puzzle.columns;
          const key = `${row},${column}`, lift = placed.get(key);
          const kind = !usable.has(key) ? "blocked" : lift ? "filled" : "empty";
          const state = kind === "blocked" ? t("result.cellBlocked")
            : lift ? t("result.cellFilled", { lift }) : t("result.cellEmpty");
          return <div key={key} className={s.cell} data-cell={kind} aria-label={t("result.cellAria", { row, column, state })}>
            {lift != null && <strong className={s.lift}>{lift}</strong>}
          </div>;
        })}
      </div>
    </SuccessGlow>
    <div className={s.summary}>
      <span className={s.summaryItem}>{t("result.summaryUsed", { count: solution.used_count })}</span>
      <span className={s.summaryItem}>{t("result.summaryLift", { value: solution.total_lift })}</span>
      <span className={s.summaryItem}>{t("result.summaryRowMoment", { value: solution.row_moment })}</span>
      <span className={s.summaryItem}>{t("result.summaryColumnMoment", { value: solution.column_moment })}</span>
    </div>
    <p className={`${s.answerSource}`}>{t("result.rule", { version: result.rule_version })}</p>
  </div>;
}
