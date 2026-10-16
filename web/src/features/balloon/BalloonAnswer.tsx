import { useAppTranslation, useMessages, type MessageText } from "../../i18n";
import type { BalloonPuzzle, BalloonSolveResult } from "../../puzzle";
import { Notice } from "../../ui/Notice/Notice";
import { SuccessGlow, SuccessReveal } from "../../ui/SuccessReveal/SuccessReveal";
import { useChangeCount } from "../puzzles/useChangeCount";
import { BalloonBoard } from "./BalloonBoard";
import { draftFromPuzzle } from "./draft";
import s from "./balloon.module.css";

export type Solved = {
  puzzle: BalloonPuzzle;
  result: BalloonSolveResult;
  source: MessageText;
  /** Stable source id for diagnostics (data-answer-source on the answer panel). */
  sourceKey: "screenshot" | "edited" | "code" | "candidate";
  /** Solved from the puzzle shown in the editor, so later edits make it stale. */
  fromDraft: boolean;
};

/** The answer board with its banner and balance figures; a stale answer is dimmed. */
export function BalloonAnswer({ solved, stale }: { solved: Solved; stale: boolean }) {
  const { t } = useAppTranslation("balloon");
  const { t: tc } = useAppTranslation("common");
  const { render } = useMessages();
  const playKey = useChangeCount(solved.result);
  const { result, puzzle } = solved;
  const source = <p className={s.answerSource}>{t("answer.source", { source: render(solved.source) })}</p>;
  if (result.outcome === "unsatisfiable") return <div className={s.answer}>
    <Notice tone="warning" role="status" title={t("result.unsatisfiableTitle")}>{t("result.unsatisfiableBody")}</Notice>{source}
  </div>;
  if (result.outcome === "timeout") return <div className={s.answer}>
    <Notice tone="warning" role="status" title={t("result.timeoutTitle", { limit: t(result.limit_reason === "time" ? "result.limitTime" : "result.limitWork") })}>
      {t("result.timeoutBody")}
    </Notice>{source}
  </div>;
  const solution = result.solution;
  if (!solution) return <Notice tone="warning">{t("result.noSolution")}</Notice>;
  const lifts = new Map(solution.placements.map((item) => [`${item.row},${item.column}`, item.lift]));
  const balanced = solution.row_moment === 0 && solution.column_moment === 0;
  return <div className={s.answer} data-solution="balloon" data-stale={stale || undefined}>
    {stale
      ? <Notice tone="warning" role="status">{t("workbench.staleAnswer")}</Notice>
      : <SuccessReveal key={playKey} title={tc("puzzle.solved")} />}
    {source}
    <SuccessGlow playKey={stale ? 0 : playKey}>
      <div className={s.answerBoard} key={playKey}>
        <BalloonBoard draft={draftFromPuzzle(puzzle)} mode="answer" lifts={lifts} />
      </div>
    </SuccessGlow>
    <p className={s.answerNote}>{t("result.found")}</p>
    <dl className={s.stats}>
      <div><dt>{t("workbench.statUsed")}</dt><dd>{solution.used_count}</dd></div>
      <div><dt>{t("workbench.statLift")}</dt><dd>{solution.total_lift}</dd></div>
      <div data-balanced={solution.row_moment === 0 || undefined}><dt>{t("workbench.statRowMoment")}</dt><dd>{solution.row_moment}</dd></div>
      <div data-balanced={solution.column_moment === 0 || undefined}><dt>{t("workbench.statColumnMoment")}</dt><dd>{solution.column_moment}</dd></div>
    </dl>
    {balanced && <p className={s.answerSource}>{t("result.rule", { version: result.rule_version })}</p>}
  </div>;
}
