import { useState } from "react";
import type { TFunction } from "i18next";
import type { CatalogCandidate } from "./api";
import { msg, useAppTranslation, useMessages, type LocalizedText, type MessageText } from "./i18n";
import type { BalloonPuzzle } from "./puzzle";
import { puzzleFromCandidate } from "./puzzle";

type Props = {
  candidates: CatalogCandidate[];
  matchedFingerprint?: string | null;
  code?: string;
  disabled?: boolean;
  actionLabel?: string;
  onSolve: (puzzle: BalloonPuzzle, label: string) => void;
};

const statusKeys: Record<string, string> = {
  provisional: "candidates.statusProvisional",
  verified: "candidates.statusVerified",
  disputed: "candidates.statusDisputed",
};

/** Catalog status label for the active language; raw status codes never leak. */
export function catalogStatusText(t: TFunction, status?: string | null): string {
  if (!status) return t("candidates.statusNone");
  const key = statusKeys[status];
  return key ? t(key) : t("candidates.statusUnknown");
}

/** Same label as a stored reference, so a notice keeps re-translating after a switch. */
export function catalogStatusRef(status?: string | null): LocalizedText {
  if (!status) return msg("candidates.statusNone", undefined, "balloon");
  const key = statusKeys[status];
  return msg(key ?? "candidates.statusUnknown", undefined, "balloon");
}

function summarize(candidate: CatalogCandidate, t: TFunction): string {
  const puzzle = candidate.puzzle;
  const inventory = puzzle.inventory.map((item) => `${item.lift}×${item.count}`).join(t("candidates.inventorySeparator"));
  return t("candidates.summary", {
    rows: puzzle.rows,
    columns: puzzle.columns,
    cells: puzzle.usable_cells.length,
    inventory,
    target: candidate.target_total_lift != null ? t("candidates.target", { value: candidate.target_total_lift }) : "",
    count: candidate.observations,
  });
}

/** Candidate list for disputed catalog records and for incomplete screenshots that hit one record. */
export default function CatalogCandidates({ candidates, matchedFingerprint, code, disabled,
                                          actionLabel, onSolve }: Props) {
  const { t } = useAppTranslation("balloon");
  const { tm } = useMessages();
  const [selected, setSelected] = useState(matchedFingerprint ?? candidates[0]?.fingerprint ?? "");
  const [error, setError] = useState<MessageText>("");
  if (!candidates.length) return null;
  const solve = () => {
    const candidate = candidates.find((item) => item.fingerprint === selected) ?? candidates[0];
    const checked = puzzleFromCandidate(candidate);
    if (!checked.puzzle) { setError(checked.error); return; }
    setError("");
    onSolve(checked.puzzle, code ? t("answer.sourceCode", { code }) : t("answer.sourceCatalogPuzzle"));
  };
  return <div className="catalog-candidates">
    <fieldset>
      <legend>{code ? t("candidates.legendCode", { code }) : t("candidates.legendGeneric")}</legend>
      {candidates.map((candidate) => <label key={candidate.fingerprint}
        className={`candidate ${selected === candidate.fingerprint ? "selected" : ""}`}>
        <input type="radio" name="catalog-candidate" value={candidate.fingerprint}
          checked={selected === candidate.fingerprint}
          onChange={() => { setSelected(candidate.fingerprint); setError(""); }} />
        <span>
          <strong>{summarize(candidate, t)}</strong>
          {candidate.fingerprint === matchedFingerprint && <em className="candidate-tag">{t("candidates.matchedTag")}</em>}
        </span>
      </label>)}
    </fieldset>
    {error && <p className="error-text" role="alert">{tm(error, "error")}</p>}
    <div className="row-actions">
      <button type="button" className="button primary" disabled={disabled || !selected} onClick={solve}>
        {actionLabel ?? t("candidates.action")}</button>
    </div>
  </div>;
}
