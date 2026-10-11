import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  cancelTask,
  getCapabilities,
  getTask,
  submitCircuit,
  submitCircuitRecognition,
  type Capability,
  type CircuitCatalogCandidate,
  type CircuitPuzzle,
  type CircuitRecognitionResult,
  type CircuitSolveResult,
  type Task,
} from "./api";
import { puzzleFromCircuitRecognition } from "./circuit";
import CircuitCatalogCandidates from "./CircuitCatalogCandidates";
import CircuitCodeQuery from "./CircuitCodeQuery";
import CircuitGuideExample from "./CircuitGuideExample";
import CircuitResult from "./CircuitResult";
import ImageInput, { type ImageSelection } from "./ImageInput";
import { msg, useAppTranslation, useMessages, type MessageText } from "./i18n";

type ServiceState = "loading" | "ready" | "error";
type Operation = "recognition" | "solve";
type Mode = "screenshot" | "code";
type CandidateChoice = {
  code: string;
  candidates: CircuitCatalogCandidate[];
  matchedFingerprint: string | null;
};
type SolveSubmission = {
  puzzle: CircuitPuzzle;
  displayPalette: unknown;
  source: MessageText;
};

const notationKeys: Record<string, string> = {
  bars: "notation.bars",
  digits: "notation.digits",
  roman: "notation.roman",
  mixed: "notation.mixed",
};
const candidateStatusKeys: Record<string, string> = {
  provisional: "catalog.statusProvisional",
  verified: "catalog.statusVerified",
};
const pause = (milliseconds: number, signal: AbortSignal) => new Promise<void>((resolve) => {
  if (signal.aborted) return resolve();
  const timer = window.setTimeout(() => { signal.removeEventListener("abort", stop); resolve(); }, milliseconds);
  const stop = () => { window.clearTimeout(timer); resolve(); };
  signal.addEventListener("abort", stop, { once: true });
});

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

function recognitionFailure(value: CircuitRecognitionResult): MessageText {
  if (value.outcome === "incomplete") return msg("failure.incomplete", undefined, "circuit");
  if (value.outcome === "no_board") return msg("failure.noBoard", undefined, "circuit");
  if (value.outcome === "already_completed") return msg("failure.alreadyCompleted", undefined, "circuit");
  if (value.outcome === "invalid_image") return msg("failure.invalidImage", undefined, "circuit");
  if (value.outcome === "timeout") return msg("failure.timeout", undefined, "circuit");
  return msg("failure.generic", undefined, "circuit");
}

export default function CircuitPage() {
  const { t, locale } = useAppTranslation("circuit");
  const { t: tc } = useAppTranslation("common");
  const { render, tm } = useMessages();
  const [service, setService] = useState<ServiceState>("loading");
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [serviceError, setServiceError] = useState<MessageText>("");
  const [mode, setMode] = useState<Mode | null>(null);
  const [imageSelection, setImageSelection] = useState<ImageSelection | null>(null);
  const [imageVersion, setImageVersion] = useState(0);
  const [queryVersion, setQueryVersion] = useState(0);
  const [task, setTask] = useState<Task | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [workError, setWorkError] = useState<MessageText>("");
  const [recognition, setRecognition] = useState<CircuitRecognitionResult | null>(null);
  const [choice, setChoice] = useState<CandidateChoice | null>(null);
  const [result, setResult] = useState<CircuitSolveResult | null>(null);
  const [submission, setSubmission] = useState<SolveSubmission | null>(null);
  const generation = useRef(0);
  const busy = useRef(false);
  const activeTaskId = useRef<string | null>(null);
  const pollController = useRef<AbortController | null>(null);
  const mounted = useRef(true);

  useEffect(() => { document.title = t("title"); }, [t, locale]);

  const invalidate = useCallback(() => {
    generation.current++;
    pollController.current?.abort();
    pollController.current = null;
    if (activeTaskId.current) void cancelTask(activeTaskId.current).catch(() => {});
    activeTaskId.current = null;
    busy.current = false;
    setTask(null); setSubmitting(false); setOperation(null); setWorkError("");
    setRecognition(null); setChoice(null); setResult(null); setSubmission(null);
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      generation.current++;
      pollController.current?.abort();
      if (activeTaskId.current) void cancelTask(activeTaskId.current).catch(() => {});
    };
  }, []);

  const refreshCapabilities = useCallback(async (signal?: AbortSignal) => {
    setService("loading"); setServiceError("");
    try {
      const list = await getCapabilities(signal);
      if (signal?.aborted || !mounted.current) return;
      setCapabilities(list); setService("ready");
    } catch (error) {
      if (signal?.aborted || !mounted.current) return;
      setCapabilities([]); setService("error"); setServiceError(explain(error));
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refreshCapabilities(controller.signal);
    return () => controller.abort();
  }, [refreshCapabilities]);

  const circuit = capabilities.find((item) => item.id === "circuit");
  const supportsRule = circuit?.supported_rule_versions.includes("line-count-v1") === true;
  const canRecognize = service === "ready" && circuit?.recognition_available === true && supportsRule;
  const canSolve = service === "ready" && circuit?.solving_available === true && supportsRule;
  const canQuery = canSolve;

  const changeImage = useCallback((selection: ImageSelection | null, changed = true) => {
    if (changed) invalidate();
    setImageSelection(selection);
  }, [invalidate]);

  async function beginSolve(
    puzzle: CircuitPuzzle,
    displayPalette: unknown,
    version: number,
    source: MessageText,
  ) {
    if (!mounted.current || generation.current !== version || !canSolve) return;
    busy.current = true;
    setOperation("solve"); setTask(null); setResult(null); setWorkError(""); setSubmitting(true);
    setSubmission({ puzzle, displayPalette, source }); setChoice(null);
    try {
      const created = await submitCircuit(puzzle);
      if (!mounted.current || generation.current !== version) {
        void cancelTask(created.id).catch(() => {});
        return;
      }
      setSubmitting(false); setTask(created); activeTaskId.current = created.id;
      const controller = new AbortController();
      pollController.current = controller;
      void poll(created.id, "solve", version, controller);
    } catch (error) {
      if (!mounted.current || generation.current !== version) return;
      busy.current = false; setSubmitting(false); setWorkError(explain(error));
    }
  }

  async function finishRecognition(value: CircuitRecognitionResult, version: number) {
    setRecognition(value);
    const candidates = value.catalog?.available ? value.catalog.candidates ?? [] : [];
    if (value.outcome === "recognized") {
      const checked = puzzleFromCircuitRecognition(value);
      if (!checked.puzzle) {
        busy.current = false;
        setWorkError(checked.error);
        return;
      }
      if (!canSolve) {
        busy.current = false;
        setWorkError(msg("failure.solveUnavailable", undefined, "circuit"));
        return;
      }
      await beginSolve(checked.puzzle, value.display_palette, version,
        msg("answer.sourceScreenshot", undefined, "circuit"));
      return;
    }
    busy.current = false;
    if ((value.outcome === "incomplete" || value.outcome === "no_board") && candidates.length > 0) {
      setWorkError(recognitionFailure(value));
      setChoice({
        code: value.catalog!.code,
        candidates,
        matchedFingerprint: value.catalog!.matched_fingerprint ?? null,
      });
      return;
    }
    setWorkError(recognitionFailure(value));
  }

  async function poll(id: string, kind: Operation, version: number, controller: AbortController) {
    while (!controller.signal.aborted && generation.current === version) {
      try {
        const current = await getTask(id, controller.signal);
        if (controller.signal.aborted || generation.current !== version || !mounted.current) return;
        setTask(current);
        if (["succeeded", "failed", "cancelled"].includes(current.status)) {
          activeTaskId.current = null;
          pollController.current = null;
          if (current.status === "succeeded") {
            if (kind === "solve") {
              busy.current = false;
              const value = current.result as CircuitSolveResult | null;
              if (value && ["solved", "unsatisfiable", "timeout"].includes(value.outcome)) setResult(value);
              else setWorkError(msg("failure.solveResultUnknown", undefined, "circuit"));
            } else {
              const value = current.result as CircuitRecognitionResult | null;
              if (value) await finishRecognition(value, version);
              else { busy.current = false; setWorkError(msg("failure.recognitionResultMissing", undefined, "circuit")); }
            }
          } else if (current.status === "failed") {
            busy.current = false; setWorkError(current.error?.message || msg("failure.taskFailed", undefined, "circuit"));
          } else {
            busy.current = false; setWorkError(msg("failure.taskCancelled", undefined, "circuit"));
          }
          return;
        }
      } catch (error) {
        if (controller.signal.aborted || generation.current !== version || !mounted.current) return;
        activeTaskId.current = null;
        pollController.current = null;
        busy.current = false;
        setTask(null); setWorkError(explain(error));
        return;
      }
      await pause(700, controller.signal);
    }
  }

  const recognize = async () => {
    if (!imageSelection || !canRecognize || busy.current) return;
    invalidate();
    busy.current = true;
    const version = generation.current;
    setOperation("recognition"); setSubmitting(true);
    try {
      const created = await submitCircuitRecognition(imageSelection.blob, imageSelection.filename);
      if (!mounted.current || generation.current !== version) {
        void cancelTask(created.id).catch(() => {});
        return;
      }
      setSubmitting(false); setTask(created); activeTaskId.current = created.id;
      const controller = new AbortController();
      pollController.current = controller;
      void poll(created.id, "recognition", version, controller);
    } catch (error) {
      if (!mounted.current || generation.current !== version) return;
      busy.current = false; setSubmitting(false); setWorkError(explain(error));
    }
  };

  const cancel = () => {
    if (!busy.current) return;
    invalidate();
    setImageSelection(null); setImageVersion((value) => value + 1);
    setQueryVersion((value) => value + 1);
    setWorkError(msg("failure.cancelled", undefined, "circuit"));
  };

  const switchMode = (next: Mode) => {
    if (next === mode) return;
    invalidate();
    setImageSelection(null); setImageVersion((value) => value + 1); setMode(next);
  };

  const solveFromChoice = (puzzle: CircuitPuzzle, displayPalette: unknown, source: MessageText) => {
    if (busy.current || !canSolve) return;
    void beginSolve(puzzle, displayPalette, generation.current, source);
  };

  const catalog = recognition?.catalog ?? null;
  const catalogClass = catalog?.image_digest_mismatch || catalog?.available === false ? " warning" : "";
  const catalogConfidence = catalog?.code_confidence != null
    ? t("confidence", { value: (catalog.code_confidence * 100).toFixed(1) }) : "";
  const questionConfidence = recognition?.question_code_confidence != null
    ? t("confidence", { value: (recognition.question_code_confidence * 100).toFixed(1) }) : "";
  const notationKey = recognition?.notation ? notationKeys[recognition.notation] ?? "notation.unknown" : "";
  return <>
    <div className="intro"><span className="eyebrow">{t("eyebrow")}</span><h1>{t("heading")}</h1>
      <p>{t("intro")}</p>
    </div>
    <div className="mode-choices" role="group" aria-label={t("modeGroupLabel")}>
      <button type="button" className={`mode-choice ${mode === "screenshot" ? "active" : ""}`}
        aria-expanded={mode === "screenshot"} aria-controls="circuit-screenshot-flow" onClick={() => switchMode("screenshot")}>
        <span className="mode-choice-title">{t("mode.screenshotTitle")}</span>
        <span className="mode-choice-note">{t("mode.screenshotNote")}</span>
      </button>
      <button type="button" className={`mode-choice ${mode === "code" ? "active" : ""}`}
        aria-expanded={mode === "code"} aria-controls="circuit-code-flow" onClick={() => switchMode("code")}>
        <span className="mode-choice-title">{t("mode.codeTitle")}</span>
        <span className="mode-choice-note">{t("mode.codeNote")}</span>
      </button>
    </div>
    <div className="service-status" role="status" aria-live="polite">
      {service === "loading" ? tc("service.querying") : service === "error"
        ? <><span>{tc("service.unavailable", { message: render(serviceError, "error") })}</span><button type="button" className="text-button" onClick={() => void refreshCapabilities()}>{tc("service.retry")}</button></>
        : circuit ? <span>{tc("service.status", {
          solving: tc(canSolve ? "service.solvingAvailable" : "service.solvingUnavailable"),
          recognition: tc(canRecognize ? "service.recognitionAvailable" : "service.recognitionUnavailable"),
        })}</span>
          : t("capabilityMissing")}
    </div>
    {mode && <div className={`content-grid ${result ? "" : "no-result"}`}>
      <div className="left-column">
        {mode === "screenshot" ? <div className="flow" id="circuit-screenshot-flow">
          <CircuitGuideExample mode="screenshot" />
          <ImageInput key={imageVersion} onChanged={changeImage}
            cropHint={tc("image.cropNoteCircuit")} />
          <section className="panel" aria-labelledby="circuit-recognize-title">
            <span className="eyebrow">{t("recognize.eyebrow")}</span><h2 id="circuit-recognize-title">{t("recognize.heading")}</h2>
            <p className="muted">{t("recognize.description")}</p>
            <p className="muted small">{tc("image.ocrNote")}</p>
            <div className="row-actions"><button type="button" className="button primary"
              disabled={!canRecognize || !imageSelection || busy.current} onClick={() => void recognize()}>
              {submitting && operation === "recognition" ? t("recognize.uploading") : operation === "recognition" && busy.current
                ? t("recognize.recognizing") : submitting && operation === "solve" ? t("recognize.submittingSolve")
                  : operation === "solve" && busy.current ? t("recognize.solving") : t("recognize.submit")}
            </button>{busy.current && <button type="button" className="button secondary" onClick={cancel}>{t("recognize.cancel")}</button>}</div>
            {/* The button stays disabled while the connection is unresolved, so
                repeat the connection state next to it instead of only on top. */}
            {service !== "ready" && <div className="service-status" role="status" aria-live="polite" data-service-hint={service}>
              {service === "loading" ? tc("service.connecting") : <><span>{tc("service.connectFailed", { message: render(serviceError, "error") })}</span><button type="button" className="text-button" onClick={() => void refreshCapabilities()}>{tc("service.retry")}</button></>}
            </div>}
            {task && <p className="task-status" role="status" aria-live="polite">{tc("task.label", {
              operation: tc(operation === "recognition" ? "task.recognition" : "task.solve"),
              status: tc(`task.${task.status}`),
            })}</p>}
            {recognition && <div className="circuit-recognition-meta" role="status">
              {(recognition.notation || recognition.question_code) && <div className="notice">
                {recognition.notation && <p><strong>{t("notation.label")}</strong>{t(notationKey)}</p>}
                {recognition.question_code && <p><strong>{t("questionCode")}</strong>{recognition.question_code}{questionConfidence}</p>}
              </div>}
              {(recognition.issues ?? []).length > 0 && <div className="notice"><strong>{t("issueTitle")}</strong>
                <ul>{(recognition.issues ?? []).map((issue) => <li key={issue}>{tm(issue)}</li>)}</ul></div>}
              {catalog && <div className={`notice${catalogClass}`}>
                <strong>{t("catalog.title")}</strong>{catalog.available ? <>
                  {t("catalog.code", { code: catalog.code, confidence: catalogConfidence })}
                  {` · ${t(catalog.complete ? "catalog.complete" : "catalog.incomplete")}`}
                  {catalog.recorded ? t("catalog.recorded") : ""}{catalog.duplicate ? t("catalog.duplicate") : ""}
                  {catalog.image_digest_mismatch ? t("catalog.digestMismatch") : ""}
                  {catalog.matched_status ? t("catalog.matchedStatus", { status: t(candidateStatusKeys[catalog.matched_status] ?? "catalog.statusUnknown") }) : ""}
                  {t("catalog.variantCount", { count: (catalog.candidates ?? []).length })}
                </> : t("catalog.unavailable")}
                {(catalog.issues ?? []).length > 0 && <ul>{(catalog.issues ?? []).map((issue) => <li key={issue}>{tm(issue)}</li>)}</ul>}
              </div>}
            </div>}
            {workError && <div className="notice warning" role="alert">{render(workError, "error")}</div>}
            {choice && <div className="notice circuit-choice">
              <strong>{t("choice.title")}</strong>{t("choice.line", { code: choice.code, count: choice.candidates.length })}
              <CircuitCatalogCandidates candidates={choice.candidates} code={choice.code}
                matchedFingerprint={choice.matchedFingerprint} disabled={busy.current || !canSolve} onSolve={solveFromChoice} />
            </div>}
          </section>
        </div> : <div className="flow" id="circuit-code-flow">
          <CircuitGuideExample mode="code" />
          <CircuitCodeQuery key={queryVersion} canQuery={canQuery} canSolve={canSolve} busy={busy.current}
            onQueryStart={invalidate} onSolve={solveFromChoice} />
          {(task || workError || busy.current) && <section className="panel" aria-label={t("statusPanelLabel")}>
            {task && <p className="task-status" role="status" aria-live="polite">{tc("task.label", {
              operation: tc("task.solve"), status: tc(`task.${task.status}`) })}</p>}
            {workError && <div className="notice warning" role="alert">{render(workError, "error")}</div>}
            {busy.current && <div className="row-actions"><button type="button" className="button secondary" onClick={cancel}>{t("recognize.cancel")}</button></div>}
          </section>}
        </div>}
      </div>
      {result && submission && <div className="right-column"><section className="panel answer-panel" aria-label={t("answer.panelLabel")}
        data-answer-source={typeof submission.source === "string" ? submission.source : submission.source.key}>
        <span className="eyebrow">{t("answer.eyebrow")}</span>
        <CircuitResult puzzle={submission.puzzle} displayPalette={submission.displayPalette} result={result} />
      </section></div>}
    </div>}
  </>;
}
