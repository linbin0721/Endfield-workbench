import { useEffect, useId, useMemo, useState } from "react";
import type { CircuitCatalogCandidate, CircuitPuzzle } from "./api";
import { puzzleFromCircuitCandidate } from "./circuit";
import CircuitPuzzlePreview from "./CircuitPuzzlePreview";

type Props = {
  candidates: CircuitCatalogCandidate[];
  matchedFingerprint?: string | null;
  code?: string;
  disabled?: boolean;
  actionLabel?: string;
  onSolve: (puzzle: CircuitPuzzle, displayPalette: unknown, label: string) => void;
};

const statusText = {
  provisional: "待确认",
  verified: "已确认",
} as const;

export default function CircuitCatalogCandidates({ candidates, matchedFingerprint, code, disabled,
  actionLabel = "用所选变体求解", onSolve }: Props) {
  const radioName = useId();
  const identity = useMemo(() => candidates.map((candidate) => candidate.fingerprint).join("|"), [candidates]);
  const initialSelection = matchedFingerprint && candidates.some((item) => item.fingerprint === matchedFingerprint)
    ? matchedFingerprint : candidates[0]?.fingerprint ?? "";
  const [selected, setSelected] = useState(initialSelection);
  const [error, setError] = useState("");

  useEffect(() => {
    setSelected(initialSelection);
    setError("");
  }, [identity, initialSelection]);

  if (!candidates.length) return null;
  const solve = () => {
    const candidate = candidates.find((item) => item.fingerprint === selected);
    if (!candidate) {
      setError("请选择一个题面变体后再求解。");
      return;
    }
    const checked = puzzleFromCircuitCandidate(candidate);
    if (!checked.puzzle) {
      setError(checked.error);
      return;
    }
    setError("");
    onSolve(checked.puzzle, candidate.display_palette,
      code ? `题号 ${code} 的目录变体` : "目录题面变体");
  };

  return <div className="circuit-candidates">
    <fieldset>
      <legend>{code ? `题号 ${code} 的题面变体` : "目录题面变体"}</legend>
      {candidates.length > 1 && <p className="muted small">同一题号可能对应多个正常变体，请核对约束、棋盘和库存后选择。</p>}
      {candidates.map((candidate, index) => <label key={candidate.fingerprint}
        className={`circuit-candidate${selected === candidate.fingerprint ? " selected" : ""}`}>
        <span className="circuit-candidate-heading">
          <input type="radio" name={radioName} value={candidate.fingerprint}
            checked={selected === candidate.fingerprint}
            onChange={() => { setSelected(candidate.fingerprint); setError(""); }} />
          <strong>变体 {index + 1}</strong>
          <span className={`circuit-candidate-status ${candidate.status}`}>{statusText[candidate.status]}</span>
          <span className="muted small">观察 {candidate.observations} 次</span>
          {candidate.fingerprint === matchedFingerprint && <em className="candidate-tag">本次截图匹配</em>}
        </span>
        <CircuitPuzzlePreview puzzle={candidate.puzzle} displayPalette={candidate.display_palette} compact />
      </label>)}
    </fieldset>
    {error && <p className="error-text" role="alert">{error}</p>}
    <div className="row-actions">
      <button type="button" className="button primary" disabled={disabled || !selected} onClick={solve}>
        {candidates.length === 1 ? "使用此题面求解" : actionLabel}
      </button>
    </div>
  </div>;
}
