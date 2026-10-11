import { useAppTranslation } from "./i18n";
import type { BalloonPuzzle, BalloonSolveResult } from "./puzzle";

type Props = { puzzle: BalloonPuzzle; result: BalloonSolveResult };

export default function Result({ puzzle, result }: Props) {
  const { t } = useAppTranslation("balloon");
  if (result.outcome === "unsatisfiable") return <div className="notice warning" role="status">
    <strong>{t("result.unsatisfiableTitle")}</strong> {t("result.unsatisfiableBody")}
  </div>;
  if (result.outcome === "timeout") return <div className="notice warning" role="status">
    <strong>{t("result.timeoutTitle", { limit: t(result.limit_reason === "time" ? "result.limitTime" : "result.limitWork") })}</strong> {t("result.timeoutBody")}
  </div>;
  const solution = result.solution;
  if (!solution) return <div className="notice warning">{t("result.noSolution")}</div>;
  const usable = new Set(puzzle.usable_cells.map((cell) => `${cell.row},${cell.column}`));
  const placed = new Map(solution.placements.map((item) => [`${item.row},${item.column}`, item.lift]));
  return <div className="solution">
    <p className="success-line">{t("result.found")}</p>
    <div className="board result-board" style={{ gridTemplateColumns: `repeat(${puzzle.columns}, minmax(0, 1fr))` }}>
      {Array.from({ length: puzzle.rows * puzzle.columns }, (_, index) => {
        const row = Math.floor(index / puzzle.columns), column = index % puzzle.columns;
        const key = `${row},${column}`, lift = placed.get(key);
        const state = !usable.has(key) ? t("result.cellBlocked")
          : lift ? t("result.cellFilled", { lift }) : t("result.cellEmpty");
        return <div key={key} className={`cell ${!usable.has(key) ? "blocked" : lift ? "filled" : "empty"}`}
          aria-label={t("result.cellAria", { row, column, state })}>
          {lift != null && <strong>{lift}</strong>}
        </div>;
      })}
    </div>
    <div className="summary">
      <span>{t("result.summaryUsed", { count: solution.used_count })}</span>
      <span>{t("result.summaryLift", { value: solution.total_lift })}</span>
      <span>{t("result.summaryRowMoment", { value: solution.row_moment })}</span>
      <span>{t("result.summaryColumnMoment", { value: solution.column_moment })}</span>
    </div>
    <p className="muted small">{t("result.rule", { version: result.rule_version })}</p>
  </div>;
}
