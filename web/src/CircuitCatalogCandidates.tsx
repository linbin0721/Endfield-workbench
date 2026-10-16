import { useEffect, useId, useMemo, useState } from "react";
import type { TFunction } from "i18next";
import type { CircuitCatalogCandidate, CircuitPuzzle } from "./api";
import { useAppTranslation, useMessages, type MessageText } from "./i18n";
import { puzzleFromCircuitCandidate } from "./circuit";
import CircuitPuzzlePreview from "./CircuitPuzzlePreview";
import s from "./features/puzzles/puzzles.module.css";
import { Button } from "./ui/Button/Button";

type Props = {
  candidates: CircuitCatalogCandidate[];
  matchedFingerprint?: string | null;
  code?: string;
  disabled?: boolean;
  actionLabel?: string;
  onSolve: (puzzle: CircuitPuzzle, displayPalette: unknown, label: string) => void;
};

const statusKeys: Record<string, string> = {
  provisional: "candidates.statusProvisional",
  verified: "candidates.statusVerified",
};

function candidateStatusText(t: TFunction, status: string): string {
  const key = statusKeys[status];
  return key ? t(key) : t("candidates.statusUnknown");
}

export default function CircuitCatalogCandidates({ candidates, matchedFingerprint, code, disabled,
  actionLabel, onSolve }: Props) {
  const { t } = useAppTranslation("circuit");
  const { tm } = useMessages();
  const radioName = useId();
  const identity = useMemo(() => candidates.map((candidate) => candidate.fingerprint).join("|"), [candidates]);
  const initialSelection = matchedFingerprint && candidates.some((item) => item.fingerprint === matchedFingerprint)
    ? matchedFingerprint : candidates[0]?.fingerprint ?? "";
  const [selected, setSelected] = useState(initialSelection);
  const [error, setError] = useState<MessageText>("");

  useEffect(() => {
    setSelected(initialSelection);
    setError("");
  }, [identity, initialSelection]);

  if (!candidates.length) return null;
  const solve = () => {
    const candidate = candidates.find((item) => item.fingerprint === selected);
    if (!candidate) {
      setError(t("candidates.selectFirst"));
      return;
    }
    const checked = puzzleFromCircuitCandidate(candidate);
    if (!checked.puzzle) {
      setError(checked.error);
      return;
    }
    setError("");
    onSolve(checked.puzzle, candidate.display_palette,
      code ? t("answer.sourceCatalogVariant", { code }) : t("answer.sourceCatalogVariantGeneric"));
  };

  return <div className={s.candidates}>
    <fieldset className={s.fieldset}>
      <legend className={s.legend}>{code ? t("candidates.legendCode", { code }) : t("candidates.legendGeneric")}</legend>
      {candidates.length > 1 && <p className={`${s.text} ${s.small}`}>{t("candidates.note")}</p>}
      <div className={s.candidates}>
        {candidates.map((candidate, index) => <label key={candidate.fingerprint} className={s.candidate}
          data-selected={selected === candidate.fingerprint}>
          <input type="radio" name={radioName} value={candidate.fingerprint}
            checked={selected === candidate.fingerprint}
            onChange={() => { setSelected(candidate.fingerprint); setError(""); }} />
          <span className={s.candidateBody}>
            <span className={s.candidateHeading}>
              <strong>{t("candidates.variant", { index: index + 1 })}</strong>
              <span className={s.status} data-status={candidate.status}>{candidateStatusText(t, candidate.status)}</span>
              <span className={s.small}>{t("candidates.observations", { count: candidate.observations })}</span>
              {candidate.fingerprint === matchedFingerprint && <em className={s.tag}>{t("candidates.matchedTag")}</em>}
            </span>
            <CircuitPuzzlePreview puzzle={candidate.puzzle} displayPalette={candidate.display_palette} compact />
          </span>
        </label>)}
      </div>
    </fieldset>
    {error && <p className={s.errorText} role="alert">{tm(error, "error")}</p>}
    <div className={s.actions}>
      <Button variant="accent" disabled={disabled || !selected} onClick={solve}>
        {candidates.length === 1 ? t("candidates.actionSingle") : actionLabel ?? t("candidates.action")}
      </Button>
    </div>
  </div>;
}
