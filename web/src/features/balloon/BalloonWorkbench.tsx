import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  getCatalogEntry,
  submitBalloon,
  submitRecognition,
  type CatalogCandidate,
  type CatalogMatch,
  type RecognitionResult,
  type Task,
} from "../../api";
import { msg, useAppTranslation, useMessages, type MessageText } from "../../i18n";
import { puzzleFromCandidate, type BalloonPuzzle, type BalloonSolveResult } from "../../puzzle";
import { Button } from "../../ui/Button/Button";
import { ArrowRightIcon, CloseIcon, SearchIcon } from "../../ui/icons";
import { Notice } from "../../ui/Notice/Notice";
import { Panel } from "../../ui/Panel/Panel";
import { SectionTitle } from "../../ui/SectionTitle/SectionTitle";
import { ImageImport } from "../workbench/ImageImport";
import { WaitingState, WorkbenchHeader, revealIfHidden } from "../workbench/WorkbenchParts";
import { useImageSource, type ImageSelection } from "../workbench/useImageSource";
import { useServiceCapabilities } from "../workbench/useServiceCapabilities";
import { useTaskRunner } from "../workbench/useTaskRunner";
import w from "../workbench/workbench.module.css";
import { BalloonAnswer, type Solved } from "./BalloonAnswer";
import { BalloonBoard } from "./BalloonBoard";
import { BalloonHelp } from "./BalloonHelp";
import { CandidateCards } from "./CandidateCards";
import { InventoryEditor } from "./InventoryEditor";
import {
  draftFromPuzzle,
  draftFromRecognition,
  draftProblems,
  nextKind,
  samePuzzle,
  toPuzzle,
  type BalloonDraft,
  type DraftProblem,
} from "./draft";
import s from "./balloon.module.css";

type Origin = { kind: "screenshot" } | { kind: "code"; code: string; status: string; count: number };
type Choice = { code: string; candidates: CatalogCandidate[]; matchedFingerprint: string | null };

const SOLVABLE = ["solved", "unsatisfiable", "timeout"];
const STATUS_KEYS: Record<string, string> = {
  provisional: "candidates.statusProvisional",
  verified: "candidates.statusVerified",
  disputed: "candidates.statusDisputed",
};
const statusKey = (status?: string | null) => status ? STATUS_KEYS[status] ?? "candidates.statusUnknown" : "candidates.statusNone";

function explain(error: unknown): MessageText {
  if (error instanceof ApiError) {
    if (error.code === "QUEUE_FULL" || error.code === "UPLOAD_BUSY") return msg("failure.busy", undefined, "balloon");
    if (error.code === "INVALID_REQUEST") return msg("failure.invalidRequest", undefined, "balloon");
    if (error.code === "NOT_FOUND") return msg("failure.expired", undefined, "balloon");
    return error.message;
  }
  return msg("failure.request", undefined, "balloon");
}

function explainQuery(error: unknown): MessageText {
  if (error instanceof ApiError) {
    if (error.code === "INVALID_CODE") return msg("query.errorInvalidCode", undefined, "balloon");
    if (error.code === "CATALOG_NOT_FOUND") return msg("query.errorNotFound", undefined, "balloon");
    if (error.code === "CATALOG_UNAVAILABLE") return msg("query.errorCatalogUnavailable", undefined, "balloon");
    return error.message;
  }
  return msg("query.errorFailed", undefined, "balloon");
}

function recognitionFailure(value: RecognitionResult): MessageText {
  if (value.outcome === "no_board") {
    // The placed-balloon guard reads the raw issue text; only its display is translated.
    const placed = value.issues?.find((issue) => issue.includes("已有气球摆放"));
    return placed || msg("failure.noBoard", undefined, "balloon");
  }
  if (value.outcome === "invalid_image") return msg("failure.invalidImage", undefined, "balloon");
  if (value.outcome === "timeout") return msg("failure.timeout", undefined, "balloon");
  return msg("failure.generic", undefined, "balloon");
}

function problemText(problem: DraftProblem, t: (key: string, options?: Record<string, unknown>) => string): string {
  switch (problem.kind) {
    case "liftMissing": case "countMissing": case "liftInvalid": case "countInvalid": case "liftDuplicate":
      return t(`problems.${problem.kind}`, { row: problem.row + 1 });
    case "tooManyBalloons": return t("problems.tooManyBalloons", { total: problem.total, max: problem.max });
    case "notEnoughCells": return t("problems.notEnoughCells", { total: problem.total, usable: problem.usable });
    case "targetMismatch": return t("problems.targetMismatch", { sum: problem.sum, target: problem.target });
    default: return t(`problems.${problem.kind}`);
  }
}

/**
 * Balloon workbench: import (screenshot or question code) → puzzle → answer.
 * A recognized puzzle solves itself when complete; missing or inconsistent
 * values stop at the puzzle step, marked for the user to complete. Screenshot
 * puzzles can be edited and solved again; catalog puzzles are read-only.
 */
export default function BalloonWorkbench() {
  const { t, locale } = useAppTranslation("balloon");
  const { t: tc } = useAppTranslation("common");
  const { render, tm } = useMessages();
  const runner = useTaskRunner();
  const service = useServiceCapabilities(explain);
  const [selection, setSelection] = useState<ImageSelection | null>(null);
  const [origin, setOrigin] = useState<Origin | null>(null);
  const [draft, setDraft] = useState<BalloonDraft | null>(null);
  const [recognized, setRecognized] = useState<BalloonDraft | null>(null);
  const [editing, setEditing] = useState(false);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [catalogMatch, setCatalogMatch] = useState<CatalogMatch | null>(null);
  const [solved, setSolved] = useState<Solved | null>(null);
  const [error, setError] = useState<MessageText>("");
  const [code, setCode] = useState("");
  const [lookingUp, setLookingUp] = useState(false);
  const lookup = useRef<AbortController | null>(null);
  const lookupVersion = useRef(0);
  const results = useRef<HTMLDivElement>(null);
  const stopRunner = runner.stop;

  useEffect(() => { document.title = t("title"); }, [t, locale]);
  useEffect(() => () => { lookupVersion.current += 1; lookup.current?.abort(); }, []);

  const capability = service.capabilities.find((item) => item.id === "balloon");
  const canSolve = service.state === "ready" && capability?.solving_available === true &&
    capability.supported_rule_versions.includes("center-torque-v1");
  const canRecognize = service.state === "ready" && capability?.recognition_available === true;
  const busy = runner.busy || lookingUp;

  /** Drops the current work (tasks, lookup, puzzle, answer, messages); the image stays. */
  const resetWork = useCallback(() => {
    stopRunner();
    lookupVersion.current += 1;
    lookup.current?.abort();
    lookup.current = null;
    setLookingUp(false);
    setOrigin(null); setDraft(null); setRecognized(null); setEditing(false); setChoice(null);
    setNotes([]); setCatalogMatch(null); setSolved(null); setError("");
  }, [stopRunner]);

  const source = useImageSource(useCallback((next: ImageSelection | null, isNew: boolean) => {
    if (isNew) resetWork();
    setSelection(next);
  }, [resetWork]));

  // Bring the puzzle and answer into view when they first appear below the fold (phones).
  const hasPuzzle = draft !== null || choice !== null;
  useEffect(() => { if (hasPuzzle) revealIfHidden(results.current); }, [hasPuzzle]);
  useEffect(() => { if (solved) revealIfHidden(results.current); }, [solved]);

  async function solve(puzzle: BalloonPuzzle, from: MessageText, sourceKey: Solved["sourceKey"]) {
    setError("");
    setSolved(null);
    try {
      const outcome = await runner.run("solve", () => submitBalloon(puzzle));
      if (!outcome.finished) return;
      const task = outcome.task;
      if (task.status === "succeeded") {
        const value = task.result as BalloonSolveResult | null;
        if (value && SOLVABLE.includes(value.outcome)) setSolved({ puzzle, result: value, source: from, sourceKey, fromDraft: sourceKey !== "candidate" });
        else setError(msg("failure.solveResultUnknown", undefined, "balloon"));
      } else if (task.status === "failed") setError(task.error?.message || msg("failure.taskFailed", undefined, "balloon"));
      else setError(msg("failure.taskCancelled", undefined, "balloon"));
    } catch (caught) {
      setError(explain(caught));
    }
  }

  function handleRecognition(task: Task) {
    if (task.status === "failed") { setError(task.error?.message || msg("failure.taskFailed", undefined, "balloon")); return; }
    if (task.status !== "succeeded") { setError(msg("failure.taskCancelled", undefined, "balloon")); return; }
    const value = task.result as RecognitionResult | null;
    if (!value || value.outcome !== "draft") {
      setError(value ? recognitionFailure(value) : msg("failure.recognitionResultMissing", undefined, "balloon"));
      return;
    }
    // "推导" filtering reads the raw issues, never a translated string.
    setNotes((value.issues ?? []).filter((issue) => issue.includes("推导")));
    setCatalogMatch(value.catalog ?? null);
    const catalog = value.catalog;
    const candidates = catalog?.candidates ?? [];
    const next = draftFromRecognition(value);
    const puzzle = next && toPuzzle(next);
    if (next) { setDraft(next); setRecognized(next); setEditing(!puzzle); }
    if (catalog && catalog.status === "disputed" && candidates.length > 1) {
      // Conflicting records are never merged: the user picks, the screenshot one is marked.
      setChoice({ code: catalog.code, candidates, matchedFingerprint: catalog.matched_fingerprint ?? null });
      return;
    }
    if (catalog && candidates.length > 0 && (!catalog.complete || (!puzzle && candidates.length === 1))) {
      // An incomplete screenshot never replaces the record: offer the recorded puzzle next to the draft.
      setChoice({ code: catalog.code, candidates, matchedFingerprint: null });
      return;
    }
    if (!next) { setError(msg("failure.noBoard", undefined, "balloon")); return; }
    if (!puzzle) return;
    if (!canSolve) { setError(msg("failure.solveUnavailable", undefined, "balloon")); return; }
    void solve(puzzle, msg("answer.sourceScreenshot", undefined, "balloon"), "screenshot");
  }

  const recognize = async () => {
    if (!selection || !canRecognize || busy) return;
    resetWork();
    setOrigin({ kind: "screenshot" });
    try {
      const outcome = await runner.run("recognition", () => submitRecognition(selection.blob, selection.filename));
      if (outcome.finished) handleRecognition(outcome.task);
    } catch (caught) {
      setError(explain(caught));
    }
  };

  const queryCode = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || service.state !== "ready") return;
    const value = code.trim();
    resetWork();
    if (!value) { setError(msg("query.emptyCode", undefined, "balloon")); return; }
    const controller = new AbortController();
    lookup.current = controller;
    const version = lookupVersion.current;
    setLookingUp(true);
    try {
      const entry = await getCatalogEntry(value, controller.signal);
      if (controller.signal.aborted || version !== lookupVersion.current) return;
      const candidates = entry.candidates ?? [];
      setOrigin({ kind: "code", code: entry.code, status: entry.status, count: candidates.length });
      if (!candidates.length) { setError(msg("query.errorNotFound", undefined, "balloon")); return; }
      if (candidates.length > 1) { setChoice({ code: entry.code, candidates, matchedFingerprint: null }); return; }
      const checked = puzzleFromCandidate(candidates[0]);
      if (!checked.puzzle) { setError(checked.error); return; }
      setDraft(draftFromPuzzle(checked.puzzle, candidates[0].target_total_lift ?? null));
      if (!canSolve) { setError(msg("query.solveUnavailable", undefined, "balloon")); return; }
      void solve(checked.puzzle, msg("answer.sourceCode", { code: entry.code }, "balloon"), "code");
    } catch (caught) {
      if (controller.signal.aborted || version !== lookupVersion.current) return;
      setError(explainQuery(caught));
    } finally {
      if (version === lookupVersion.current) { setLookingUp(false); lookup.current = null; }
    }
  };

  const chooseCandidate = (puzzle: BalloonPuzzle, letter: string) => {
    if (!choice || runner.busy) return;
    void solve(puzzle, msg("workbench.sourceCandidate", { code: choice.code, letter }, "balloon"), "candidate");
  };

  const cancel = () => {
    if (!runner.busy) return;
    if (runner.state?.kind === "recognition") resetWork();
    else stopRunner();
    setError(msg("failure.cancelled", undefined, "balloon"));
  };

  const problems = useMemo(() => draft && editing ? draftProblems(draft) : [], [draft, editing]);
  const listedProblems = problems.filter((problem) => problem.kind !== "cellUnknown");
  const unknownCells = problems.length - listedProblems.length;
  const edited = recognized !== null && draft !== recognized;
  const stale = solved !== null && solved.fromDraft && draft !== null && !samePuzzle(toPuzzle(draft), solved.puzzle);
  const solveRunning = runner.busy && runner.state?.kind === "solve";
  const recognitionRunning = runner.busy && runner.state?.kind === "recognition";
  const canSolveDraft = draft !== null && problems.length === 0 && toPuzzle(draft) !== null && !runner.busy && canSolve;
  const solveDraft = () => {
    const puzzle = draft && toPuzzle(draft);
    if (!puzzle || runner.busy || !canSolve) return;
    setEditing(false);
    void solve(puzzle, edited ? msg("workbench.sourceEdited", undefined, "balloon") : msg("answer.sourceScreenshot", undefined, "balloon"),
      edited ? "edited" : "screenshot");
  };

  const step = solved || solveRunning ? 2 : hasPuzzle ? 1 : 0;
  const flow = recognitionRunning || lookingUp ? "recognizing" : solveRunning ? "solving" : solved ? "answer"
    : hasPuzzle ? "puzzle" : error ? "failed" : "import";
  const taskLine = runner.state?.task && <p className={w.task} role="status" aria-live="polite" data-task-status={runner.state.task.status}>
    {tc("task.label", { operation: tc(runner.state.kind === "recognition" ? "task.recognition" : "task.solve"), status: tc(`task.${runner.state.task.status}`) })}
  </p>;
  const recognizeLabel = recognitionRunning
    ? runner.state?.phase === "submitting" ? t("recognize.uploading") : t("recognize.recognizing")
    : t("recognize.submit");
  const codeConfidence = catalogMatch?.code_confidence != null
    ? t("confidence", { value: (catalogMatch.code_confidence * 100).toFixed(1) }) : "";
  const errorNotice = error ? <Notice tone="danger" role="alert">{render(error, "error")}</Notice> : null;

  return <div className={w.page} data-flow={flow}>
    <WorkbenchHeader eyebrow={t("eyebrow")} title={t("heading")} intro={t("workbench.intro")} step={step}
      service={service} capability={capability} capabilityMissing={t("capabilityMissing")} help={<BalloonHelp />} />

    <Panel as="section" aria-labelledby="balloon-import-title">
      <SectionTitle id="balloon-import-title" aside={<span className={w.badge}>{tc("image.localOnlyBadge")}</span>}>
        {tc("workbench.importTitle")}
      </SectionTitle>
      <div className={w.importGrid}>
        <div className={w.importMain}>
          <ImageImport source={source} cropHint={tc("image.cropNoteDefault")} />
          <div className={w.actions}>
            <Button variant="accent" icon={<ArrowRightIcon />} disabled={!selection || !canRecognize || busy} onClick={() => void recognize()}>
              {recognizeLabel}
            </Button>
            {recognitionRunning && <Button variant="secondary" icon={<CloseIcon />} onClick={cancel}>{t("recognize.cancel")}</Button>}
            {!recognitionRunning && <span className={w.hint}>{tc("image.uploadNote")}</span>}
          </div>
          {recognitionRunning && taskLine}
        </div>
        <form className={w.code} onSubmit={(event) => void queryCode(event)} aria-labelledby="balloon-code-title">
          <p className={w.codeTitle} id="balloon-code-title">
            <span className={w.or} aria-hidden="true">{tc("workbench.or")}</span>{tc("workbench.codeTitle")}
          </p>
          <label className={w.label} htmlFor="question-code">{t("query.label")}</label>
          <div className={w.codeRow}>
            <input id="question-code" name="question-code" className={w.codeInput} value={code} placeholder="WL-A1001"
              autoComplete="off" spellCheck={false} onChange={(event) => setCode(event.target.value)} />
            <Button type="submit" variant="secondary" icon={<SearchIcon />} disabled={busy || service.state !== "ready"}>
              {lookingUp ? t("query.loading") : t("workbench.lookup")}
            </Button>
          </div>
          <p className={w.hint}>{t("query.help")}</p>
        </form>
      </div>
      {!hasPuzzle && errorNotice && <div className={w.notices}>{errorNotice}</div>}
    </Panel>

    <div ref={results} className={w.results}>
      <Panel as="section" aria-labelledby="balloon-puzzle-title" data-puzzle-panel="" data-editing={editing || undefined}>
        <SectionTitle id="balloon-puzzle-title" aside={editing
          ? <span className={w.badge} data-tone="edit">{t("workbench.editing")}</span>
          : origin?.kind === "code" ? <span className={w.badge}>{t("workbench.readOnly")}</span> : undefined}>
          {origin?.kind === "code" ? t("workbench.puzzleFromCode", { code: origin.code })
            : origin?.kind === "screenshot" && hasPuzzle ? t("workbench.puzzleRecognized") : tc("workbench.stepPuzzle")}
        </SectionTitle>
        {!hasPuzzle
          ? <WaitingState text={recognitionRunning || lookingUp ? t("recognize.recognizing") : tc("workbench.puzzleWaiting")}
            busy={recognitionRunning || lookingUp} />
          : <div className={w.stack}>
            <div className={w.notices}>
              {editing && problems.length > 0 && <Notice tone="warning" role="status">{t("workbench.needsInput")}</Notice>}
              {notes.length > 0 && <Notice tone="info" role="status" title={t("issueTitle")}>{notes.map((issue) => tm(issue)).join(" ")}</Notice>}
              {origin?.kind === "code" && <Notice tone="info" role="status">
                {t("query.entryLine", { code: origin.code, status: t(statusKey(origin.status)), count: origin.count })}
              </Notice>}
              {catalogMatch && <Notice tone={catalogMatch.available ? "info" : "warning"} role="status" title={t("catalog.title")}>
                {catalogMatch.available
                  ? t("catalog.line", { code: catalogMatch.code, confidence: codeConfidence, status: t(statusKey(catalogMatch.status)),
                    completeness: t(catalogMatch.complete ? "catalog.complete" : "catalog.incomplete") })
                  : t("catalog.unavailable")}
                {(catalogMatch.issues ?? []).map((issue) => <span key={issue} className={w.subline}>{tm(issue)}</span>)}
              </Notice>}
              {choice && <Notice tone="info" role="status" title={t("choice.title")}>
                {choice.candidates.length > 1
                  ? origin?.kind === "code" ? t("query.multiple") : t("choice.disputed", { code: choice.code })
                  : t("choice.single", { code: choice.code })}
              </Notice>}
            </div>
            {draft && <div className={s.puzzle}>
              <div className={s.boardColumn}>
                <BalloonBoard draft={draft} mode={editing ? "edit" : "view"}
                  onToggle={(index) => setDraft({ ...draft, cells: draft.cells.map((cell, position) => position === index ? nextKind(cell) : cell) })} />
                {editing && <p className={w.hint}>{unknownCells > 0 ? t("problems.cellUnknown", { count: unknownCells }) : t("editor.toggleHint")}</p>}
              </div>
              <InventoryEditor draft={draft} editable={editing} problems={problems}
                onChange={(inventory) => setDraft({ ...draft, inventory })} onTargetChange={(target) => setDraft({ ...draft, target })} />
            </div>}
            {listedProblems.length > 0 && <ul className={s.problems} aria-live="polite">
              {listedProblems.map((problem, index) => <li key={index}>{problemText(problem, t)}</li>)}
            </ul>}
            {draft && origin?.kind === "screenshot" && <div className={w.actions}>
              {(editing || stale || (!solved && !solveRunning)) &&
                <Button variant="accent" icon={<ArrowRightIcon />} disabled={!canSolveDraft} onClick={solveDraft}>
                  {solved ? t("workbench.solveAgain") : t("workbench.solveDraft")}
                </Button>}
              {!editing && <Button variant="secondary" disabled={runner.busy} onClick={() => setEditing(true)}>{t("workbench.edit")}</Button>}
              {editing && edited && <Button variant="ghost" onClick={() => setDraft(recognized)}>{t("workbench.revert")}</Button>}
            </div>}
            {choice && <CandidateCards key={`${choice.code}-${choice.matchedFingerprint ?? "none"}`} code={choice.code}
              candidates={choice.candidates} matchedFingerprint={choice.matchedFingerprint}
              disabled={runner.busy || !canSolve} onSolve={chooseCandidate} />}
            {errorNotice}
          </div>}
      </Panel>

      <Panel as="section" corners aria-labelledby="balloon-answer-title" data-answer-panel="" data-answer-source={solved?.sourceKey}>
        <SectionTitle id="balloon-answer-title">{t("answer.eyebrow")}</SectionTitle>
        {solveRunning
          ? <WaitingState busy text={runner.state?.phase === "submitting" ? t("recognize.submittingSolve") : t("recognize.solving")}>
            {taskLine}
            <Button variant="secondary" size="sm" icon={<CloseIcon />} onClick={cancel}>{t("recognize.cancel")}</Button>
          </WaitingState>
          : solved
            ? <BalloonAnswer solved={solved} stale={stale} />
            : <WaitingState text={tc("puzzle.answerWaiting")} />}
      </Panel>
    </div>
  </div>;
}
