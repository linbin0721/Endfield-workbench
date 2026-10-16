import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent } from "react";
import {
  ApiError,
  getCircuitCatalogEntry,
  submitCircuit,
  submitCircuitRecognition,
  type CircuitCatalogCandidate,
  type CircuitPuzzle,
  type CircuitRecognitionResult,
  type CircuitSolveResult,
  type Task,
} from "../../api";
import { puzzleFromCircuitCandidate, puzzleFromCircuitRecognition } from "../../circuit";
import { msg, useAppTranslation, useMessages, type MessageText } from "../../i18n";
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
import { CircuitAnswer, type Solved } from "./CircuitAnswer";
import { CircuitBoard } from "./CircuitBoard";
import { CircuitCandidates } from "./CircuitCandidates";
import { CircuitHelp } from "./CircuitHelp";
import { CircuitPieces } from "./CircuitPieces";
import { colorName, useCircuitColors } from "./colors";
import { draftFromPuzzle, draftProblems, nextCell, puzzleKey, toPuzzle, type CircuitDraft, type DraftProblem } from "./draft";
import c from "./circuit.module.css";

type Origin = { kind: "screenshot" } | { kind: "code"; code: string; count: number };
type Choice = { code: string; candidates: CircuitCatalogCandidate[]; matchedFingerprint: string | null };

const SOLVABLE = ["solved", "unsatisfiable", "timeout"];
const NOTATION_KEYS: Record<string, string> = {
  bars: "notation.bars",
  digits: "notation.digits",
  roman: "notation.roman",
  mixed: "notation.mixed",
};
const MATCHED_STATUS_KEYS: Record<string, string> = {
  provisional: "catalog.statusProvisional",
  verified: "catalog.statusVerified",
};
const DASHES = "-֊־᐀᠆‐‑‒–—―−⸺⸻﹘﹣－";
const TRIANGLES = "△▲▵▴Δ∆";

/** V + five digits or WL + four digits; case, decoration triangles, dashes and spaces are normalized. */
function normalizeCode(value: string): string | null {
  const token = value.normalize("NFKC").replace(/[\s\uFE00-\uFE0F\u{E0100}-\u{E01EF}]/gu, "").toUpperCase();
  const decoration = new RegExp(`^[${TRIANGLES}]?[${DASHES.replace("-", "\\-")}]?`);
  const normalized = token.replace(decoration, "");
  return /^(?:V\d{5}|WL\d{4})$/.test(normalized) ? normalized : null;
}

function explain(error: unknown): MessageText {
  if (error instanceof ApiError) {
    if (error.code === "QUEUE_FULL" || error.code === "UPLOAD_BUSY") return msg("failure.busy", undefined, "circuit");
    if (error.code === "INVALID_REQUEST") return msg("failure.invalidRequest", undefined, "circuit");
    if (error.code === "NOT_FOUND") return msg("failure.expired", undefined, "circuit");
    if (error.code === "NETWORK_ERROR") return msg("failure.network", undefined, "circuit");
    return error.message;
  }
  return msg("failure.request", undefined, "circuit");
}

function explainQuery(error: unknown): MessageText {
  if (error instanceof ApiError) {
    if (error.code === "INVALID_CODE") return msg("query.errorInvalidCode", undefined, "circuit");
    if (error.code === "CATALOG_NOT_FOUND") return msg("query.errorNotFound", undefined, "circuit");
    if (error.code === "CATALOG_UNAVAILABLE") return msg("query.errorCatalogUnavailable", undefined, "circuit");
    if (error.code === "NETWORK_ERROR") return msg("query.errorNetwork", undefined, "circuit");
    return error.message;
  }
  return msg("query.errorFailed", undefined, "circuit");
}

function recognitionFailure(value: CircuitRecognitionResult): MessageText {
  if (value.outcome === "incomplete") return msg("failure.incomplete", undefined, "circuit");
  if (value.outcome === "no_board") return msg("failure.noBoard", undefined, "circuit");
  if (value.outcome === "already_completed") return msg("failure.alreadyCompleted", undefined, "circuit");
  if (value.outcome === "invalid_image") return msg("failure.invalidImage", undefined, "circuit");
  if (value.outcome === "timeout") return msg("failure.timeout", undefined, "circuit");
  return msg("failure.generic", undefined, "circuit");
}

/**
 * Circuit workbench: import (screenshot or question code) → puzzle → answer.
 * A fully recognized puzzle solves itself and can be edited (targets,
 * obstacles, fixed cells) and solved again; pieces are never edited, catalog
 * puzzles are read-only, and every answer is re-verified before drawing.
 */
export default function CircuitWorkbench() {
  const { t, locale } = useAppTranslation("circuit");
  const { t: tc } = useAppTranslation("common");
  const { render, tm } = useMessages();
  const runner = useTaskRunner();
  const service = useServiceCapabilities(explain);
  const [selection, setSelection] = useState<ImageSelection | null>(null);
  const [origin, setOrigin] = useState<Origin | null>(null);
  const [recognition, setRecognition] = useState<CircuitRecognitionResult | null>(null);
  const [draft, setDraft] = useState<CircuitDraft | null>(null);
  const [recognized, setRecognized] = useState<CircuitDraft | null>(null);
  const [editing, setEditing] = useState(false);
  const [activeChannel, setActiveChannel] = useState(0);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [solved, setSolved] = useState<Solved | null>(null);
  const [warning, setWarning] = useState<MessageText>("");
  const [error, setError] = useState<MessageText>("");
  const [code, setCode] = useState("");
  const [lookingUp, setLookingUp] = useState(false);
  const lookup = useRef<AbortController | null>(null);
  const lookupVersion = useRef(0);
  const results = useRef<HTMLDivElement>(null);
  const stopRunner = runner.stop;

  useEffect(() => { document.title = t("title"); }, [t, locale]);
  useEffect(() => () => { lookupVersion.current += 1; lookup.current?.abort(); }, []);

  const capability = service.capabilities.find((item) => item.id === "circuit");
  const supportsRule = capability?.supported_rule_versions.includes("line-count-v1") === true;
  const canSolve = service.state === "ready" && capability?.solving_available === true && supportsRule;
  const canRecognize = service.state === "ready" && capability?.recognition_available === true && supportsRule;
  const busy = runner.busy || lookingUp;
  const { colors, usedFallback } = useCircuitColors(draft?.channels.length ?? 0, draft?.palette);

  const resetWork = useCallback(() => {
    stopRunner();
    lookupVersion.current += 1;
    lookup.current?.abort();
    lookup.current = null;
    setLookingUp(false);
    setOrigin(null); setRecognition(null); setDraft(null); setRecognized(null); setEditing(false); setActiveChannel(0);
    setChoice(null); setSolved(null); setWarning(""); setError("");
  }, [stopRunner]);

  const source = useImageSource(useCallback((next: ImageSelection | null, isNew: boolean) => {
    if (isNew) resetWork();
    setSelection(next);
  }, [resetWork]));

  const hasPuzzle = draft !== null || choice !== null;
  useEffect(() => { if (hasPuzzle) revealIfHidden(results.current); }, [hasPuzzle]);
  useEffect(() => { if (solved) revealIfHidden(results.current); }, [solved]);

  async function solve(puzzle: CircuitPuzzle, palette: unknown, from: MessageText, sourceKey: Solved["sourceKey"]) {
    setError("");
    setSolved(null);
    try {
      const outcome = await runner.run("solve", () => submitCircuit(puzzle));
      if (!outcome.finished) return;
      const task = outcome.task;
      if (task.status === "succeeded") {
        const value = task.result as CircuitSolveResult | null;
        if (value && SOLVABLE.includes(value.outcome)) {
          setSolved({ puzzle, palette, result: value, source: from, sourceKey, fromDraft: sourceKey !== "candidate" });
        } else setError(msg("failure.solveResultUnknown", undefined, "circuit"));
      } else if (task.status === "failed") setError(task.error?.message || msg("failure.taskFailed", undefined, "circuit"));
      else setError(msg("failure.taskCancelled", undefined, "circuit"));
    } catch (caught) {
      setError(explain(caught));
    }
  }

  function handleRecognition(task: Task) {
    if (task.status === "failed") { setError(task.error?.message || msg("failure.taskFailed", undefined, "circuit")); return; }
    if (task.status !== "succeeded") { setError(msg("failure.taskCancelled", undefined, "circuit")); return; }
    const value = task.result as CircuitRecognitionResult | null;
    if (!value) { setError(msg("failure.recognitionResultMissing", undefined, "circuit")); return; }
    setRecognition(value);
    const candidates = value.catalog?.available ? value.catalog.candidates ?? [] : [];
    if (value.outcome === "recognized") {
      // A complete screenshot is always solved as read; the catalog only explains the match.
      const checked = puzzleFromCircuitRecognition(value);
      if (!checked.puzzle) { setError(checked.error); return; }
      const next = draftFromPuzzle(checked.puzzle, value.display_palette);
      setDraft(next); setRecognized(next);
      if (!canSolve) { setError(msg("failure.solveUnavailable", undefined, "circuit")); return; }
      void solve(checked.puzzle, value.display_palette, msg("answer.sourceScreenshot", undefined, "circuit"), "screenshot");
      return;
    }
    if ((value.outcome === "incomplete" || value.outcome === "no_board") && candidates.length > 0) {
      setWarning(recognitionFailure(value));
      setChoice({ code: value.catalog!.code, candidates, matchedFingerprint: value.catalog!.matched_fingerprint ?? null });
      return;
    }
    setError(recognitionFailure(value));
  }

  const recognize = async () => {
    if (!selection || !canRecognize || busy) return;
    resetWork();
    setOrigin({ kind: "screenshot" });
    try {
      const outcome = await runner.run("recognition", () => submitCircuitRecognition(selection.blob, selection.filename));
      if (outcome.finished) handleRecognition(outcome.task);
    } catch (caught) {
      setError(explain(caught));
    }
  };

  const queryCode = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || service.state !== "ready") return;
    resetWork();
    const normalized = normalizeCode(code);
    if (!normalized) { setError(msg("query.emptyCode", undefined, "circuit")); return; }
    const controller = new AbortController();
    lookup.current = controller;
    const version = lookupVersion.current;
    setLookingUp(true);
    try {
      const entry = await getCircuitCatalogEntry(normalized, controller.signal);
      if (controller.signal.aborted || version !== lookupVersion.current) return;
      const candidates = entry.candidates ?? [];
      setOrigin({ kind: "code", code: entry.code, count: candidates.length });
      if (!candidates.length) { setError(msg("query.noCandidates", undefined, "circuit")); return; }
      if (candidates.length > 1) { setChoice({ code: entry.code, candidates, matchedFingerprint: null }); return; }
      const checked = puzzleFromCircuitCandidate(candidates[0]);
      if (!checked.puzzle) { setError(checked.error); return; }
      setDraft(draftFromPuzzle(checked.puzzle, candidates[0].display_palette));
      if (!canSolve) { setError(msg("query.solveUnavailable", undefined, "circuit")); return; }
      void solve(checked.puzzle, candidates[0].display_palette, msg("answer.sourceCode", { code: entry.code }, "circuit"), "code");
    } catch (caught) {
      if (controller.signal.aborted || version !== lookupVersion.current) return;
      setError(explainQuery(caught));
    } finally {
      if (version === lookupVersion.current) { setLookingUp(false); lookup.current = null; }
    }
  };

  const chooseCandidate = (puzzle: CircuitPuzzle, palette: unknown, letter: string) => {
    if (!choice || runner.busy) return;
    void solve(puzzle, palette, msg("workbench.sourceCandidate", { code: choice.code, letter }, "circuit"), "candidate");
  };

  const cancel = () => {
    if (!runner.busy) return;
    if (runner.state?.kind === "recognition") resetWork();
    else stopRunner();
    setError(msg("failure.cancelled", undefined, "circuit"));
  };

  const problems = useMemo(() => draft && editing ? draftProblems(draft) : [], [draft, editing]);
  const edited = recognized !== null && draft !== recognized;
  const draftPuzzle = useMemo(() => draft ? toPuzzle(draft) : null, [draft]);
  const stale = solved !== null && solved.fromDraft && draft !== null &&
    (draftPuzzle === null || puzzleKey(draftPuzzle) !== puzzleKey(solved.puzzle));
  const solveRunning = runner.busy && runner.state?.kind === "solve";
  const recognitionRunning = runner.busy && runner.state?.kind === "recognition";
  const canSolveDraft = draftPuzzle !== null && !runner.busy && canSolve;
  const solveDraft = () => {
    if (!draft || !draftPuzzle || runner.busy || !canSolve) return;
    setEditing(false);
    void solve(draftPuzzle, draft.palette, edited ? msg("workbench.sourceEdited", undefined, "circuit") : msg("answer.sourceScreenshot", undefined, "circuit"),
      edited ? "edited" : "screenshot");
  };
  const problemText = (problem: DraftProblem) => {
    const color = "channel" in problem ? colors[problem.channel] : undefined;
    switch (problem.kind) {
      case "targetMissing": case "targetInvalid":
        return t(`problems.${problem.kind}`, { color: color ? colorName(t, color) : "", axis: t(problem.axis === "row" ? "problems.axisRow" : "problems.axisColumn"), index: problem.index + 1 });
      case "cellUnknown": case "fixedChannel": return t(`problems.${problem.kind}`, { count: problem.count });
      default: return tm(problem.message, "error");
    }
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
  const catalog = recognition?.catalog ?? null;
  const catalogConfidence = catalog?.code_confidence != null ? t("confidence", { value: (catalog.code_confidence * 100).toFixed(1) }) : "";
  const questionConfidence = recognition?.question_code_confidence != null
    ? t("confidence", { value: (recognition.question_code_confidence * 100).toFixed(1) }) : "";
  const errorNotice = error ? <Notice tone="danger" role="alert">{render(error, "error")}</Notice> : null;

  return <div className={w.page} data-flow={flow}>
    <WorkbenchHeader eyebrow={t("eyebrow")} title={t("heading")} intro={t("workbench.intro")} step={step}
      service={service} capability={capability} capabilityMissing={t("capabilityMissing")} help={<CircuitHelp />} />

    <Panel as="section" aria-labelledby="circuit-import-title">
      <SectionTitle id="circuit-import-title" aside={<span className={w.badge}>{tc("image.localOnlyBadge")}</span>}>
        {tc("workbench.importTitle")}
      </SectionTitle>
      <div className={w.importGrid}>
        <div className={w.importMain}>
          <ImageImport source={source} cropHint={tc("image.cropNoteCircuit")} />
          <div className={w.actions}>
            <Button variant="accent" icon={<ArrowRightIcon />} disabled={!selection || !canRecognize || busy} onClick={() => void recognize()}>
              {recognizeLabel}
            </Button>
            {recognitionRunning && <Button variant="secondary" icon={<CloseIcon />} onClick={cancel}>{t("recognize.cancel")}</Button>}
            {!recognitionRunning && <span className={w.hint}>{tc("image.uploadNote")}</span>}
          </div>
          {recognitionRunning && taskLine}
        </div>
        <form className={w.code} onSubmit={(event) => void queryCode(event)} aria-labelledby="circuit-code-title">
          <p className={w.codeTitle} id="circuit-code-title">
            <span className={w.or} aria-hidden="true">{tc("workbench.or")}</span>{tc("workbench.codeTitle")}
          </p>
          <label className={w.label} htmlFor="circuit-question-code">{t("query.label")}</label>
          <div className={w.codeRow}>
            <input id="circuit-question-code" name="circuit-question-code" className={w.codeInput} value={code} placeholder={t("query.placeholder")}
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
      <Panel as="section" aria-labelledby="circuit-puzzle-title" data-puzzle-panel="" data-editing={editing || undefined}>
        <SectionTitle id="circuit-puzzle-title" aside={editing
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
              {warning && <Notice tone="warning" role="status">{render(warning)}</Notice>}
              {recognition && (recognition.notation || recognition.question_code) && <Notice tone="info" role="status">
                {recognition.notation && <span className={w.subline}><strong>{t("notation.label")}</strong>{t(NOTATION_KEYS[recognition.notation] ?? "notation.unknown")}</span>}
                {recognition.question_code && <span className={w.subline}><strong>{t("questionCode")}</strong>{recognition.question_code}{questionConfidence}</span>}
              </Notice>}
              {recognition && (recognition.issues ?? []).length > 0 && <Notice tone="info" role="status" title={t("issueTitle")}>
                {(recognition.issues ?? []).map((issue) => <span key={issue} className={w.subline}>{tm(issue)}</span>)}
              </Notice>}
              {catalog && <Notice tone={catalog.image_digest_mismatch || !catalog.available ? "warning" : "info"} role="status" title={t("catalog.title")}>
                {catalog.available ? <>
                  {t("catalog.code", { code: catalog.code, confidence: catalogConfidence })}
                  {` · ${t(catalog.complete ? "catalog.complete" : "catalog.incomplete")}`}
                  {catalog.recorded ? t("catalog.recorded") : ""}{catalog.duplicate ? t("catalog.duplicate") : ""}
                  {catalog.image_digest_mismatch ? t("catalog.digestMismatch") : ""}
                  {catalog.matched_status ? t("catalog.matchedStatus", { status: t(MATCHED_STATUS_KEYS[catalog.matched_status] ?? "catalog.statusUnknown") }) : ""}
                  {t("catalog.variantCount", { count: (catalog.candidates ?? []).length })}
                </> : t("catalog.unavailable")}
                {(catalog.issues ?? []).map((issue) => <span key={issue} className={w.subline}>{tm(issue)}</span>)}
              </Notice>}
              {origin?.kind === "code" && choice && <Notice tone="info" role="status">{t("query.entryLine", { code: origin.code, count: origin.count })}</Notice>}
              {origin?.kind === "screenshot" && choice && <Notice tone="info" role="status" title={t("choice.title")}>
                {t("choice.line", { code: choice.code, count: choice.candidates.length })}
              </Notice>}
            </div>
            {draft && colors.length === draft.channels.length && <div className={c.puzzle}>
              {editing && <div className={c.channels} role="group" aria-label={t("editor.channelGroup")}>
                <span className={c.channelsLabel}>{t("editor.channelLabel")}</span>
                {draft.channels.map((channel) => {
                  const color = colors[channel.index];
                  return <button key={channel.index} type="button" className={c.channel} aria-pressed={activeChannel === channel.index}
                    style={{ "--chip-bg": color.fill, "--chip-fg": color.edge } as CSSProperties} onClick={() => setActiveChannel(channel.index)}>
                    <i aria-hidden="true" />{colorName(t, color)}
                  </button>;
                })}
              </div>}
              <CircuitBoard draft={draft} colors={colors} mode={editing ? "edit" : "view"} activeChannel={activeChannel}
                onCell={(index) => setDraft({ ...draft, cells: draft.cells.map((cell, position) => position === index ? nextCell(cell, activeChannel) : cell) })}
                onTarget={(channel, axis, index, value) => setDraft({
                  ...draft,
                  channels: draft.channels.map((item) => item.index !== channel ? item : axis === "row"
                    ? { ...item, row_targets: item.row_targets.map((target, position) => position === index ? value : target) }
                    : { ...item, column_targets: item.column_targets.map((target, position) => position === index ? value : target) }),
                })} />
              {editing && <p className={w.hint}>{t("editor.cellHint")}</p>}
              <div className={c.inventory}>
                <p className={c.inventoryTitle}>{t("preview.piecesLabel", { count: draft.pieces.length })}</p>
                <CircuitPieces pieces={draft.pieces} colors={colors} />
                <p className={c.legendLine}>
                  <span>{t("preview.legendBlocked")}</span><span>{t("preview.legendFixed")}</span>
                  {usedFallback && <span>{t("preview.fallbackColors")}</span>}
                </p>
              </div>
            </div>}
            {problems.length > 0 && <ul className={c.problems} aria-live="polite">
              {problems.map((problem, index) => <li key={index}>{problemText(problem)}</li>)}
            </ul>}
            {draft && origin?.kind === "screenshot" && <div className={w.actions}>
              {(editing || stale || (!solved && !solveRunning)) &&
                <Button variant="accent" icon={<ArrowRightIcon />} disabled={!canSolveDraft} onClick={solveDraft}>
                  {solved ? t("workbench.solveAgain") : t("workbench.solveDraft")}
                </Button>}
              {!editing && <Button variant="secondary" disabled={runner.busy} onClick={() => setEditing(true)}>{t("workbench.edit")}</Button>}
              {editing && edited && <Button variant="ghost" onClick={() => setDraft(recognized)}>{t("workbench.revert")}</Button>}
            </div>}
            {choice && <CircuitCandidates key={`${choice.code}-${choice.matchedFingerprint ?? "none"}`} code={choice.code}
              candidates={choice.candidates} matchedFingerprint={choice.matchedFingerprint}
              disabled={runner.busy || !canSolve} onSolve={chooseCandidate} />}
            {errorNotice}
          </div>}
      </Panel>

      <Panel as="section" corners aria-labelledby="circuit-answer-title" data-answer-panel="" data-answer-source={solved?.sourceKey}>
        <SectionTitle id="circuit-answer-title">{t("answer.eyebrow")}</SectionTitle>
        {solveRunning
          ? <WaitingState busy text={runner.state?.phase === "submitting" ? t("recognize.submittingSolve") : t("recognize.solving")}>
            {taskLine}
            <Button variant="secondary" size="sm" icon={<CloseIcon />} onClick={cancel}>{t("recognize.cancel")}</Button>
          </WaitingState>
          : solved
            ? <CircuitAnswer solved={solved} stale={stale} />
            : <WaitingState text={tc("puzzle.answerWaiting")} />}
      </Panel>
    </div>
  </div>;
}
