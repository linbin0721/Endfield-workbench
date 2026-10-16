import { useState } from "react";
import type { CircuitCatalogCandidate, CircuitPuzzle } from "../../api";
import { puzzleFromCircuitCandidate } from "../../circuit";
import { useAppTranslation, useMessages } from "../../i18n";
import { Button } from "../../ui/Button/Button";
import { ArrowRightIcon } from "../../ui/icons";
import { CircuitBoard } from "./CircuitBoard";
import { CircuitPieces } from "./CircuitPieces";
import { useCircuitColors } from "./colors";
import { draftFromPuzzle } from "./draft";
import c from "./circuit.module.css";

const letterOf = (index: number) => String.fromCharCode(65 + index);
const STATUS_KEYS: Record<string, string> = {
  provisional: "candidates.statusProvisional",
  verified: "candidates.statusVerified",
};

function Card({ candidate, index, selected, matched, name, onSelect }: {
  candidate: CircuitCatalogCandidate;
  index: number;
  selected: boolean;
  matched: boolean;
  name: string;
  onSelect: () => void;
}) {
  const { t } = useAppTranslation("circuit");
  const checked = puzzleFromCircuitCandidate(candidate);
  const draft = checked.puzzle ? draftFromPuzzle(checked.puzzle, candidate.display_palette) : null;
  const { colors } = useCircuitColors(draft?.channels.length ?? 0, candidate.display_palette);
  return <label className={c.candidate} data-selected={selected}>
    <span className={c.candidateHead}>
      <input type="radio" name={name} value={candidate.fingerprint} checked={selected} onChange={onSelect} />
      <strong>{t("workbench.puzzleLetter", { letter: letterOf(index) })}</strong>
      <span className={c.status} data-status={candidate.status}>{t(STATUS_KEYS[candidate.status] ?? "candidates.statusUnknown")}</span>
      <span className={c.seen}>{t("candidates.observations", { count: candidate.observations })}</span>
      {matched && <em className={c.tag}>{t("candidates.matchedTag")}</em>}
    </span>
    {draft && colors.length === draft.channels.length
      ? <>
        <CircuitBoard draft={draft} colors={colors} mode="view" size="sm" />
        <CircuitPieces pieces={draft.pieces} colors={colors} compact />
      </>
      : null}
  </label>;
}

/**
 * Recorded puzzles of one code side by side as "Puzzle A, B…", each with its
 * board, targets and pieces. The one matching this screenshot is marked and
 * preselected.
 */
export function CircuitCandidates({ code, candidates, matchedFingerprint, disabled, onSolve }: {
  code: string;
  candidates: CircuitCatalogCandidate[];
  matchedFingerprint?: string | null;
  disabled: boolean;
  onSolve: (puzzle: CircuitPuzzle, palette: unknown, letter: string) => void;
}) {
  const { t } = useAppTranslation("circuit");
  const { tm } = useMessages();
  const initial = matchedFingerprint && candidates.some((item) => item.fingerprint === matchedFingerprint)
    ? matchedFingerprint : candidates[0]?.fingerprint ?? "";
  const [selected, setSelected] = useState(initial);
  const [error, setError] = useState("");
  const solve = () => {
    const index = candidates.findIndex((item) => item.fingerprint === selected);
    if (index < 0) { setError(t("candidates.selectFirst")); return; }
    const checked = puzzleFromCircuitCandidate(candidates[index]);
    if (!checked.puzzle) { setError(checked.error); return; }
    setError("");
    onSolve(checked.puzzle, candidates[index].display_palette, letterOf(index));
  };
  return <fieldset className={c.candidates}>
    <legend className={c.legend}>{t("candidates.legendCode", { code })}</legend>
    <div className={c.candidateGrid}>
      {candidates.map((candidate, index) => <Card key={candidate.fingerprint} candidate={candidate} index={index}
        selected={selected === candidate.fingerprint} matched={candidate.fingerprint === matchedFingerprint}
        name={`circuit-candidate-${code}`} onSelect={() => { setSelected(candidate.fingerprint); setError(""); }} />)}
    </div>
    {error && <p className={c.error} role="alert">{tm(error, "error")}</p>}
    <div className={c.actions}>
      <Button variant="accent" icon={<ArrowRightIcon />} disabled={disabled || !selected} onClick={solve}>
        {candidates.length === 1 ? t("candidates.actionSingle") : t("workbench.solveSelected")}
      </Button>
    </div>
  </fieldset>;
}
