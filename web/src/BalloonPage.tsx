import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, cancelTask, getCapabilities, getTask, submitBalloon, submitRecognition,
  type Capability, type CatalogCandidate, type CatalogMatch, type RecognitionResult, type Task } from "./api";
import CatalogCandidates, { catalogStatusText } from "./CatalogCandidates";
import CodeGuideExample from "./CodeGuideExample";
import CodeQuery from "./CodeQuery";
import GuideExample from "./GuideExample";
import ImageInput, { type ImageSelection } from "./ImageInput";
import Result from "./Result";
import { msg, useAppTranslation, useMessages, type MessageText } from "./i18n";
import { puzzleFromRecognition, type BalloonPuzzle, type BalloonSolveResult } from "./puzzle";
import { AnswerPanel, ModeSwitch, SectionHead, ServiceStatus, TaskStatus, type ModeOption } from "./features/puzzles/PuzzleParts";
import s from "./features/puzzles/puzzles.module.css";
import { Button } from "./ui/Button/Button";
import { ArrowRightIcon, CloseIcon, ImageIcon, SearchIcon } from "./ui/icons";
import { Notice } from "./ui/Notice/Notice";
import { PageHeader } from "./ui/PageHeader/PageHeader";
import { Panel } from "./ui/Panel/Panel";

type ServiceState = "loading" | "ready" | "error";
type Operation = "recognition" | "solve";
type Mode = "screenshot" | "code";
type CandidateChoice = { code: string; candidates: CatalogCandidate[]; matchedFingerprint: string | null };
const pause = (milliseconds: number, signal: AbortSignal) => new Promise<void>((resolve) => {
  if (signal.aborted) return resolve();
  const timer = window.setTimeout(() => { signal.removeEventListener("abort", stop); resolve(); }, milliseconds);
  const stop = () => { window.clearTimeout(timer); resolve(); };
  signal.addEventListener("abort", stop, { once: true });
});

const screenshotSource = () => msg("answer.sourceScreenshot", undefined, "balloon");

function explain(error: unknown): MessageText {
  if (error instanceof ApiError) {
    if (error.code === "QUEUE_FULL" || error.code === "UPLOAD_BUSY") return msg("failure.busy", undefined, "balloon");
    if (error.code === "INVALID_REQUEST") return msg("failure.invalidRequest", undefined, "balloon");
    if (error.code === "NOT_FOUND") return msg("failure.expired", undefined, "balloon");
    return error.message;
  }
  return msg("failure.request", undefined, "balloon");
}

function recognitionFailure(value: RecognitionResult): MessageText {
  if (value.outcome === "no_board") {
    // The placed-balloon guard still reads the raw issue text; only its display is translated.
    const placed = value.issues?.find((issue) => issue.includes("已有气球摆放"));
    return placed || msg("failure.noBoard", undefined, "balloon");
  }
  if (value.outcome === "invalid_image") return msg("failure.invalidImage", undefined, "balloon");
  if (value.outcome === "timeout") return msg("failure.timeout", undefined, "balloon");
  return msg("failure.generic", undefined, "balloon");
}

export default function BalloonPage() {
  const { t, locale } = useAppTranslation("balloon");
  const { t: tc } = useAppTranslation("common");
  const { render, tm } = useMessages();
  const [service, setService] = useState<ServiceState>("loading");
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [serviceError, setServiceError] = useState<MessageText>("");
  const [mode, setMode] = useState<Mode | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [imageSelection, setImageSelection] = useState<ImageSelection | null>(null);
  const [workError, setWorkError] = useState<MessageText>("");
  const [recognitionNotes, setRecognitionNotes] = useState<string[]>([]);
  const [catalogMatch, setCatalogMatch] = useState<CatalogMatch | null>(null);
  const [choice, setChoice] = useState<CandidateChoice | null>(null);
  const [result, setResult] = useState<BalloonSolveResult | null>(null);
  const [submittedPuzzle, setSubmittedPuzzle] = useState<BalloonPuzzle | null>(null);
  const [answerSource, setAnswerSource] = useState<MessageText>(screenshotSource());
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
    setTask(null); setResult(null); setSubmittedPuzzle(null); setWorkError(""); setSubmitting(false); setOperation(null);
    setRecognitionNotes([]); setCatalogMatch(null); setChoice(null); setAnswerSource(screenshotSource());
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

  const changeImage = useCallback((selection: ImageSelection | null, changed = true) => {
    if (changed) invalidate();
    setImageSelection(selection);
  }, [invalidate]);
  const balloon = capabilities.find((item) => item.id === "balloon");
  const canSolve = service === "ready" && balloon?.solving_available === true &&
    balloon.supported_rule_versions.includes("center-torque-v1");
  const canRecognize = service === "ready" && balloon?.recognition_available === true;

  async function beginSolve(puzzle: BalloonPuzzle, version: number, source: MessageText = screenshotSource()) {
    if (!mounted.current || generation.current !== version) return;
    busy.current = true;
    setOperation("solve"); setTask(null); setResult(null); setWorkError(""); setSubmitting(true); setSubmittedPuzzle(puzzle);
    setChoice(null); setAnswerSource(source);
    try {
      const created = await submitBalloon(puzzle);
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

  async function poll(id: string, kind: Operation, version: number, controller: AbortController) {
    while (!controller.signal.aborted && generation.current === version) {
      try {
        const current = await getTask(id, controller.signal);
        if (controller.signal.aborted || generation.current !== version) return;
        setTask(current);
        if (["succeeded", "failed", "cancelled"].includes(current.status)) {
          activeTaskId.current = null;
          pollController.current = null;
          if (current.status === "succeeded") {
            if (kind === "solve") {
              busy.current = false;
              const value = current.result as BalloonSolveResult | null;
              if (value && ["solved", "unsatisfiable", "timeout"].includes(value.outcome)) setResult(value);
              else setWorkError(msg("failure.solveResultUnknown", undefined, "balloon"));
            } else {
              const value = current.result as RecognitionResult | null;
              if (value?.outcome === "draft") {
                // "推导" filtering reads the raw issues, never a translated string.
                setRecognitionNotes((value.issues ?? []).filter((issue) => issue.includes("推导")));
                setCatalogMatch(value.catalog ?? null);
                const candidates = value.catalog?.candidates ?? [];
                const checked = puzzleFromRecognition(value);
                if (value.catalog?.status === "disputed" && candidates.length > 1) {
                  // Conflicting records are never merged: the user picks the
                  // statement to solve, and the screenshot one is marked.
                  busy.current = false;
                  setChoice({ code: value.catalog.code, candidates,
                    matchedFingerprint: value.catalog.matched_fingerprint ?? null });
                  return;
                }
                if (value.catalog && !value.catalog.complete && candidates.length > 0) {
                  busy.current = false;
                  setChoice({ code: value.catalog.code, candidates, matchedFingerprint: null });
                  return;
                }
                if (checked.puzzle && canSolve) {
                  await beginSolve(checked.puzzle, version);
                  return;
                }
                busy.current = false;
                if (!checked.puzzle && candidates.length === 1) {
                  setChoice({ code: value.catalog!.code, candidates, matchedFingerprint: null });
                  return;
                }
                setWorkError(checked.error || msg("failure.solveUnavailable", undefined, "balloon"));
              } else {
                busy.current = false;
                setWorkError(value ? recognitionFailure(value) : msg("failure.recognitionResultMissing", undefined, "balloon"));
              }
            }
          } else if (current.status === "failed") { busy.current = false; setWorkError(current.error?.message || msg("failure.taskFailed", undefined, "balloon")); }
          else { busy.current = false; setWorkError(msg("failure.taskCancelled", undefined, "balloon")); }
          return;
        }
      } catch (error) {
        if (controller.signal.aborted || generation.current !== version) return;
        setWorkError(explain(error));
        activeTaskId.current = null;
        pollController.current = null;
        busy.current = false;
        setTask(null);
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
      const created = await submitRecognition(imageSelection.blob, imageSelection.filename);
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
    const previousOperation = operation;
    invalidate();
    setOperation(previousOperation);
    setWorkError(msg("failure.cancelled", undefined, "balloon"));
  };

  const switchMode = (next: Mode) => {
    if (next === mode) return;
    // Opening the other entry always starts clean: no old task, result, message,
    // catalog state or previously selected image is carried over.
    invalidate();
    setImageSelection(null);
    setMode(next);
  };

  const codeConfidence = catalogMatch?.code_confidence != null
    ? t("confidence", { value: (catalogMatch.code_confidence * 100).toFixed(1) }) : "";
  const catalogIssues = catalogMatch?.issues ?? [];
  const solveFromChoice = (puzzle: BalloonPuzzle, source: MessageText) => {
    if (busy.current) return;
    void beginSolve(puzzle, generation.current, source);
  };

  const modeOptions: ModeOption<Mode>[] = [
    { mode: "screenshot", title: t("mode.screenshotTitle"), note: t("mode.screenshotNote"), icon: <ImageIcon />, controls: "screenshot-flow" },
    { mode: "code", title: t("mode.codeTitle"), note: t("mode.codeNote"), icon: <SearchIcon />, controls: "code-flow" },
  ];
  const serviceState = service === "ready" && !balloon ? "missing" : service;
  const serviceText = service === "loading" ? tc("service.querying")
    : service === "error" ? tc("service.unavailable", { message: render(serviceError, "error") })
      : balloon ? tc("service.status", {
        solving: tc(balloon.solving_available ? "service.solvingAvailable" : "service.solvingUnavailable"),
        recognition: tc(balloon.recognition_available ? "service.recognitionAvailable" : "service.recognitionUnavailable"),
      }) : t("capabilityMissing");
  const taskLine = (kind: Operation | null) => task && <TaskStatus status={task.status}>{tc("task.label", {
    operation: tc(kind === "recognition" ? "task.recognition" : "task.solve"),
    status: tc(`task.${task.status}`),
  })}</TaskStatus>;

  return <div className={s.page}>
    <PageHeader eyebrow={t("eyebrow")} title={t("heading")}>{t("intro")}</PageHeader>
    <ModeSwitch label={t("modeGroupLabel")} value={mode} options={modeOptions} onSelect={switchMode} />
    <ServiceStatus state={serviceState} text={serviceText} retryLabel={tc("service.retry")} onRetry={() => void refreshCapabilities()} />
    {mode && <div className={s.workspace} id={mode === "screenshot" ? "screenshot-flow" : "code-flow"}>
      <div className={s.column}>
        {mode === "screenshot" ? <>
          <GuideExample />
          <ImageInput onChanged={changeImage} />
        </> : <>
          <CodeGuideExample />
          <CodeQuery canQuery={service === "ready"} canSolve={canSolve} busy={busy.current}
            onQueryStart={invalidate} onSolve={solveFromChoice} />
        </>}
      </div>
      <div className={s.column}>
        {mode === "screenshot" ? <Panel as="section" aria-labelledby="recognize-title">
          <SectionHead eyebrow={t("recognize.eyebrow")} title={t("recognize.heading")} id="recognize-title" />
          <p className={s.text}>{t("recognize.description")}</p>
          <p className={`${s.text} ${s.small}`}>{tc("image.ocrNote")}</p>
          <div className={s.actions}>
            <Button variant="accent" icon={<ArrowRightIcon />} disabled={!canRecognize || !imageSelection || busy.current} onClick={() => void recognize()}>
              {submitting && operation === "recognition" ? t("recognize.uploading") : operation === "recognition" && busy.current ? t("recognize.recognizing") : submitting && operation === "solve" ? t("recognize.submittingSolve") : operation === "solve" && busy.current ? t("recognize.solving") : t("recognize.submit")}</Button>
            {busy.current && <Button variant="secondary" icon={<CloseIcon />} onClick={cancel}>{t("recognize.cancel")}</Button>}
          </div>
          {/* The button stays disabled while the connection is unresolved, so
              repeat the connection state next to it instead of only on top. */}
          {service !== "ready" && <ServiceStatus hint state={service}
            text={service === "loading" ? tc("service.connecting") : tc("service.connectFailed", { message: render(serviceError, "error") })}
            retryLabel={tc("service.retry")} onRetry={() => void refreshCapabilities()} />}
          {taskLine(operation)}
          <div className={s.recognition}>
            {recognitionNotes.length > 0 && <Notice tone="info" role="status" title={t("issueTitle")}>
              {recognitionNotes.map((issue) => tm(issue)).join(" ")}
            </Notice>}
            {catalogMatch && <Notice tone={catalogMatch.available ? "info" : "warning"} role="status" title={t("catalog.title")}>
              {catalogMatch.available
                ? t("catalog.line", { code: catalogMatch.code, confidence: codeConfidence,
                  status: catalogStatusText(t, catalogMatch.status),
                  completeness: t(catalogMatch.complete ? "catalog.complete" : "catalog.incomplete") })
                : t("catalog.unavailable")}
              {catalogIssues.length > 0 && <ul className={s.list}>{catalogIssues.map((issue) => <li key={issue}>{tm(issue)}</li>)}</ul>}
            </Notice>}
            {choice && <div className={s.stack} role="status">
              <Notice tone="info" title={t("choice.title")}>{choice.candidates.length > 1
                ? t("choice.disputed", { code: choice.code })
                : t("choice.single", { code: choice.code })}</Notice>
              <CatalogCandidates key={`${choice.code}-${choice.matchedFingerprint ?? "none"}`} candidates={choice.candidates}
                matchedFingerprint={choice.matchedFingerprint} code={choice.code}
                disabled={busy.current || !canSolve} onSolve={solveFromChoice} />
            </div>}
            {workError && <Notice tone="danger" role="alert">{render(workError, "error")}</Notice>}
          </div>
        </Panel> : (task || workError || busy.current) && <Panel as="section" aria-label={t("statusPanelLabel")}>
          {taskLine("solve")}
          {workError && <div className={s.recognition}><Notice tone="danger" role="alert">{render(workError, "error")}</Notice></div>}
          {busy.current && <div className={s.actions}><Button variant="secondary" icon={<CloseIcon />} onClick={cancel}>{t("recognize.cancel")}</Button></div>}
        </Panel>}
        <AnswerPanel label={t("answer.panelLabel")} title={t("answer.eyebrow")} waiting={tc("puzzle.answerWaiting")}
          source={result && answerSource ? t("answer.source", { source: render(answerSource) }) : undefined}>
          {result && submittedPuzzle ? <Result result={result} puzzle={submittedPuzzle} /> : null}
        </AnswerPanel>
      </div>
    </div>}
  </div>;
}
