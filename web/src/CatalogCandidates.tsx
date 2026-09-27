import { useState } from "react";
import type { CatalogCandidate } from "./api";
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

const statusText: Record<string, string> = {
  provisional: "待确认（仅一张截图）",
  verified: "已确认（两张不同截图）",
  disputed: "存在争议（多个不同题面）",
};

function summarize(candidate: CatalogCandidate): string {
  const puzzle = candidate.puzzle;
  const inventory = puzzle.inventory.map((item) => `${item.lift}×${item.count}`).join("、");
  return `${puzzle.rows}×${puzzle.columns} · 可放置 ${puzzle.usable_cells.length} 格 · 库存 ${inventory}` +
    `${candidate.target_total_lift != null ? ` · 目标总升力 ${candidate.target_total_lift}` : ""}` +
    ` · 已观察 ${candidate.observations} 次`;
}

/** Candidate list for disputed catalog records and for incomplete screenshots that hit one record. */
export default function CatalogCandidates({ candidates, matchedFingerprint, code, disabled,
                                          actionLabel = "用所选题面求解", onSolve }: Props) {
  const [selected, setSelected] = useState(matchedFingerprint ?? candidates[0]?.fingerprint ?? "");
  const [error, setError] = useState("");
  if (!candidates.length) return null;
  const solve = () => {
    const candidate = candidates.find((item) => item.fingerprint === selected) ?? candidates[0];
    const checked = puzzleFromCandidate(candidate);
    if (!checked.puzzle) { setError(checked.error); return; }
    setError("");
    onSolve(checked.puzzle, code ? `题号 ${code}` : "目录题面");
  };
  return <div className="catalog-candidates">
    <fieldset>
      <legend>{code ? `题号 ${code} 的候选题面` : "目录候选题面"}</legend>
      {candidates.map((candidate) => <label key={candidate.fingerprint}
        className={`candidate ${selected === candidate.fingerprint ? "selected" : ""}`}>
        <input type="radio" name="catalog-candidate" value={candidate.fingerprint}
          checked={selected === candidate.fingerprint}
          onChange={() => { setSelected(candidate.fingerprint); setError(""); }} />
        <span>
          <strong>{summarize(candidate)}</strong>
          {candidate.fingerprint === matchedFingerprint && <em className="candidate-tag">本次截图识别</em>}
        </span>
      </label>)}
    </fieldset>
    {error && <p className="error-text" role="alert">{error}</p>}
    <div className="row-actions">
      <button type="button" className="button primary" disabled={disabled || !selected} onClick={solve}>{actionLabel}</button>
    </div>
  </div>;
}

export function catalogStatusText(status?: string | null): string {
  return status ? statusText[status] ?? status : "无记录";
}
