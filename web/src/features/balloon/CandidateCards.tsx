import { useState } from "react";
import type { CatalogCandidate } from "../../api";
import { useAppTranslation, useMessages } from "../../i18n";
import { puzzleFromCandidate, type BalloonPuzzle } from "../../puzzle";
import { Button } from "../../ui/Button/Button";
import { ArrowRightIcon } from "../../ui/icons";
import { BalloonBoard } from "./BalloonBoard";
import { InventoryEditor } from "./InventoryEditor";
import { draftFromPuzzle } from "./draft";
import s from "./balloon.module.css";

const letterOf = (index: number) => String.fromCharCode(65 + index);

/**
 * Several recorded puzzles for one question code, side by side as "Puzzle A,
 * B…": board, inventory and how often each was seen. The one matching this
 * screenshot (if any) is marked and preselected.
 */
export function CandidateCards({ code, candidates, matchedFingerprint, disabled, onSolve }: {
  code: string;
  candidates: CatalogCandidate[];
  matchedFingerprint?: string | null;
  disabled: boolean;
  /** Called with the checked puzzle and its letter (A, B…). */
  onSolve: (puzzle: BalloonPuzzle, letter: string) => void;
}) {
  const { t } = useAppTranslation("balloon");
  const [selected, setSelected] = useState(matchedFingerprint ?? candidates[0]?.fingerprint ?? "");
  const { tm } = useMessages();
  const [invalid, setInvalid] = useState("");
  const choose = () => {
    const index = Math.max(0, candidates.findIndex((item) => item.fingerprint === selected));
    const checked = puzzleFromCandidate(candidates[index]);
    if (!checked.puzzle) { setInvalid(checked.error); return; }
    setInvalid("");
    onSolve(checked.puzzle, letterOf(index));
  };
  return <fieldset className={s.candidates}>
    <legend className={s.legend}>{t("candidates.legendCode", { code })}</legend>
    <div className={s.candidateGrid}>
      {candidates.map((candidate, index) => {
        const draft = draftFromPuzzle(candidate.puzzle, candidate.target_total_lift ?? null);
        return <label key={candidate.fingerprint} className={s.candidate} data-selected={selected === candidate.fingerprint}>
          <span className={s.candidateHead}>
            <input type="radio" name={`balloon-candidate-${code}`} value={candidate.fingerprint}
              checked={selected === candidate.fingerprint} onChange={() => { setSelected(candidate.fingerprint); setInvalid(""); }} />
            <strong>{t("workbench.puzzleLetter", { letter: letterOf(index) })}</strong>
            <span className={s.seen}>{t("workbench.seenTimes", { count: candidate.observations ?? 1 })}</span>
            {candidate.fingerprint === matchedFingerprint && <em className={s.tag}>{t("candidates.matchedTag")}</em>}
          </span>
          <BalloonBoard draft={draft} mode="view" size="sm" />
          <InventoryEditor draft={draft} editable={false} />
        </label>;
      })}
    </div>
    {invalid && <p className={s.error} role="alert">{tm(invalid, "error")}</p>}
    <div className={s.actions}>
      <Button variant="accent" icon={<ArrowRightIcon />} disabled={disabled || !selected} onClick={choose}>{t("candidates.action")}</Button>
    </div>
  </fieldset>;
}
