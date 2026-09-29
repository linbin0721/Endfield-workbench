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

type ServiceState = "loading" | "ready" | "error";
type Operation = "recognition" | "solve";
type Mode = "screenshot" | "code";
type CandidateChoice = {
  code: string;
  candidates: CircuitCatalogCandidate[];
  matchedFingerprint: string | null;
};

const notationText: Record<string, string> = {
  bars: "短条约束",
  digits: "数字约束",
  roman: "罗马数字约束",
  mixed: "混合约束",
};
const candidateStatusText: Record<string, string> = { provisional: "待确认", verified: "已确认" };
const pause = (milliseconds: number, signal: AbortSignal) => new Promise<void>((resolve) => {
  if (signal.aborted) return resolve();
  const timer = window.setTimeout(() => { signal.removeEventListener("abort", stop); resolve(); }, milliseconds);
  const stop = () => { window.clearTimeout(timer); resolve(); };
  signal.addEventListener("abort", stop, { once: true });
});

function explain(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "QUEUE_FULL" || error.code === "UPLOAD_BUSY") return "当前任务较多，请稍后重试。";
    if (error.code === "INVALID_REQUEST") return "服务未能接受这张图片或题面，请检查后重试。";
    if (error.code === "NOT_FOUND") return "任务已过期或服务重启，请重新识别。";
    if (error.code === "NETWORK_ERROR") return "无法连接解题服务，请检查网络后重试。";
    return error.message;
  }
  return "请求未完成，请稍后重试。";
}

function recognitionFailure(value: CircuitRecognitionResult): string {
  if (value.outcome === "incomplete") return "已定位题面，但行列约束、棋盘格或库存拼块识别不完整。请上传包含完整棋盘（含上方和左侧约束）与右侧全部拼块的清晰截图。";
  if (value.outcome === "no_board") return "未能定位完整棋盘。请上传包含完整棋盘（含上方和左侧约束）与右侧全部拼块的清晰截图。";
  if (value.outcome === "already_completed") return "截图中的谜题已经完成。请先在游戏中重置谜题，再重新截图识别。";
  if (value.outcome === "invalid_image") return "图片无法读取、格式不支持或尺寸过大，请换一张清晰完整的截图重试。";
  if (value.outcome === "timeout") return "图片识别达到时间上限，请换一张清晰完整的截图重试。";
  return "图片识别失败，请稍后重试或换一张清晰完整的截图。";
}

export default function CircuitPage() {
  const [service, setService] = useState<ServiceState>("loading");
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [serviceError, setServiceError] = useState("");
  const [mode, setMode] = useState<Mode | null>(null);
  const [imageSelection, setImageSelection] = useState<ImageSelection | null>(null);
  const [imageVersion, setImageVersion] = useState(0);
  const [queryVersion, setQueryVersion] = useState(0);
  const [task, setTask] = useState<Task | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [workError, setWorkError] = useState("");
  const [recognition, setRecognition] = useState<CircuitRecognitionResult | null>(null);
  const [choice, setChoice] = useState<CandidateChoice | null>(null);
  const [result, setResult] = useState<CircuitSolveResult | null>(null);
  const [submittedPuzzle, setSubmittedPuzzle] = useState<CircuitPuzzle | null>(null);
  const [answerSource, setAnswerSource] = useState("");
  const generation = useRef(0);
  const busy = useRef(false);
  const activeTaskId = useRef<string | null>(null);
  const pollController = useRef<AbortController | null>(null);
  const mounted = useRef(true);

  useEffect(() => { document.title = "源石电路 | 终末地解谜助手"; }, []);

  const invalidate = useCallback(() => {
    generation.current++;
    pollController.current?.abort();
    pollController.current = null;
    if (activeTaskId.current) void cancelTask(activeTaskId.current).catch(() => {});
    activeTaskId.current = null;
    busy.current = false;
    setTask(null); setSubmitting(false); setOperation(null); setWorkError("");
    setRecognition(null); setChoice(null); setResult(null); setSubmittedPuzzle(null); setAnswerSource("");
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

  async function beginSolve(puzzle: CircuitPuzzle, version: number, source: string) {
    if (!mounted.current || generation.current !== version || !canSolve) return;
    busy.current = true;
    setOperation("solve"); setTask(null); setResult(null); setWorkError(""); setSubmitting(true);
    setSubmittedPuzzle(puzzle); setChoice(null); setAnswerSource(source);
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
        setWorkError("识别已完成，但源石电路求解服务当前不可用，请稍后重试。");
        return;
      }
      await beginSolve(checked.puzzle, version, "本次截图识别");
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
              else setWorkError("服务返回了无法识别的源石电路求解结果，请稍后重试。");
            } else {
              const value = current.result as CircuitRecognitionResult | null;
              if (value) await finishRecognition(value, version);
              else { busy.current = false; setWorkError("服务未返回有效识别结果，请重试。"); }
            }
          } else if (current.status === "failed") {
            busy.current = false; setWorkError(current.error?.message || "任务失败，请稍后重试。");
          } else {
            busy.current = false; setWorkError("任务已取消。");
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
    setWorkError("已取消本次识别或求解；服务中的任务可能仍需片刻结束。");
  };

  const switchMode = (next: Mode) => {
    if (next === mode) return;
    invalidate();
    setImageSelection(null); setImageVersion((value) => value + 1); setMode(next);
  };

  const solveFromChoice = (puzzle: CircuitPuzzle, label: string) => {
    if (busy.current || !canSolve) return;
    void beginSolve(puzzle, generation.current, label);
  };

  const catalog = recognition?.catalog ?? null;
  const catalogClass = catalog?.image_digest_mismatch || catalog?.available === false ? " warning" : "";
  return <>
    <div className="intro"><span className="eyebrow">解谜工具 / CIRCUIT</span><h1>源石电路解谜</h1>
      <p>导入包含完整棋盘、上方和左侧约束及右侧全部库存拼块的截图，自动识别并求解；也可以按题号复用目录中的题面变体。</p>
    </div>
    <div className="mode-choices" role="group" aria-label="解题入口">
      <button type="button" className={`mode-choice ${mode === "screenshot" ? "active" : ""}`}
        aria-expanded={mode === "screenshot"} aria-controls="circuit-screenshot-flow" onClick={() => switchMode("screenshot")}>
        <span className="mode-choice-title">截图识别</span>
        <span className="mode-choice-note">上传完整棋盘、约束与库存拼块，识别并求解</span>
      </button>
      <button type="button" className={`mode-choice ${mode === "code" ? "active" : ""}`}
        aria-expanded={mode === "code"} aria-controls="circuit-code-flow" onClick={() => switchMode("code")}>
        <span className="mode-choice-title">按题号查询</span>
        <span className="mode-choice-note">查询目录中的一个或多个正常题面变体</span>
      </button>
    </div>
    <div className="service-status" role="status" aria-live="polite">
      {service === "loading" ? "正在查询服务能力…" : service === "error"
        ? <><span>服务不可用：{serviceError}</span><button type="button" className="text-button" onClick={() => void refreshCapabilities()}>重试连接</button></>
        : circuit ? <span>服务状态：{canSolve ? "求解可用" : "求解暂不可用"} · {canRecognize ? "图片识别可用" : "图片识别暂不可用"}</span>
          : "服务未声明源石电路能力，暂不可提交。"}
    </div>
    {mode && <div className={`content-grid ${result ? "" : "no-result"}`}>
      <div className="left-column">
        {mode === "screenshot" ? <div className="flow" id="circuit-screenshot-flow">
          <CircuitGuideExample mode="screenshot" />
          <ImageInput key={imageVersion} onChanged={changeImage}
            cropHint="请保留完整棋盘（含上方和左侧全部约束）以及右侧所有库存拼块。" />
          <section className="panel" aria-labelledby="circuit-recognize-title">
            <span className="eyebrow">识别与求解</span><h2 id="circuit-recognize-title">从图片得到答案</h2>
            <p className="muted">只有点击后才上传当前预览的图片。识别到完整题面后始终求解本次截图；题号目录只用于记录和匹配说明。</p>
            <div className="row-actions"><button type="button" className="button primary"
              disabled={!canRecognize || !imageSelection || busy.current} onClick={() => void recognize()}>
              {submitting && operation === "recognition" ? "正在上传…" : operation === "recognition" && busy.current
                ? "正在识别…" : submitting && operation === "solve" ? "正在提交求解…"
                  : operation === "solve" && busy.current ? "正在求解…" : "识别并求解"}
            </button>{busy.current && <button type="button" className="button secondary" onClick={cancel}>取消本次任务</button>}</div>
            {task && <p className="task-status" role="status" aria-live="polite">{operation === "recognition" ? "识别" : "求解"}任务状态：{{ queued: "排队中", running: "处理中", succeeded: "已完成", failed: "失败", cancelled: "已取消" }[task.status]}</p>}
            {recognition && <div className="circuit-recognition-meta" role="status">
              {(recognition.notation || recognition.question_code) && <div className="notice">
                {recognition.notation && <p><strong>约束表示：</strong>{notationText[recognition.notation] ?? recognition.notation}</p>}
                {recognition.question_code && <p><strong>识别题号：</strong>{recognition.question_code}{recognition.question_code_confidence != null
                  ? ` · 置信度 ${(recognition.question_code_confidence * 100).toFixed(1)}%` : ""}</p>}
              </div>}
              {(recognition.issues ?? []).length > 0 && <div className="notice"><strong>识别提示：</strong>
                <ul>{(recognition.issues ?? []).map((issue) => <li key={issue}>{issue}</li>)}</ul></div>}
              {catalog && <div className={`notice${catalogClass}`}>
                <strong>题号目录：</strong>{catalog.available ? <>
                  题号 {catalog.code}{catalog.code_confidence != null ? ` · 置信度 ${(catalog.code_confidence * 100).toFixed(1)}%` : ""}
                  {` · ${catalog.complete ? "本次题面完整" : "本次题面不完整"}`}
                  {catalog.recorded ? " · 已记录新观察" : ""}{catalog.duplicate ? " · 图片已记录，未重复计数" : ""}
                  {catalog.image_digest_mismatch ? " · 图片摘要对应的历史题面与本次结果不同，未改写记录" : ""}
                  {catalog.matched_status ? ` · 匹配变体${candidateStatusText[catalog.matched_status] ?? catalog.matched_status}` : ""}
                  {` · 目录变体 ${(catalog.candidates ?? []).length} 个`}
                </> : "暂不可用，本次仍可按截图完整题面求解"}
                {(catalog.issues ?? []).length > 0 && <ul>{(catalog.issues ?? []).map((issue) => <li key={issue}>{issue}</li>)}</ul>}
              </div>}
            </div>}
            {workError && <div className="notice warning" role="alert">{workError}</div>}
            {choice && <div className="notice circuit-choice">
              <strong>可用目录题面：</strong>本次截图没有完整题面；题号 {choice.code} 有 {choice.candidates.length} 个正常变体，可核对后选择求解。
              <CircuitCatalogCandidates candidates={choice.candidates} code={choice.code}
                matchedFingerprint={choice.matchedFingerprint} disabled={busy.current || !canSolve} onSolve={solveFromChoice} />
            </div>}
          </section>
        </div> : <div className="flow" id="circuit-code-flow">
          <CircuitGuideExample mode="code" />
          <CircuitCodeQuery key={queryVersion} canQuery={canQuery} canSolve={canSolve} busy={busy.current}
            onQueryStart={invalidate} onSolve={solveFromChoice} />
          {(task || workError || busy.current) && <section className="panel" aria-label="查询与求解状态">
            {task && <p className="task-status" role="status" aria-live="polite">求解任务状态：{{ queued: "排队中", running: "处理中", succeeded: "已完成", failed: "失败", cancelled: "已取消" }[task.status]}</p>}
            {workError && <div className="notice warning" role="alert">{workError}</div>}
            {busy.current && <div className="row-actions"><button type="button" className="button secondary" onClick={cancel}>取消本次任务</button></div>}
          </section>}
        </div>}
      </div>
      {result && submittedPuzzle && <div className="right-column"><section className="panel answer-panel" aria-label="求解结果">
        <span className="eyebrow">答案</span>{answerSource && <p className="muted small">来源：{answerSource}</p>}
        <CircuitResult puzzle={submittedPuzzle} result={result} />
      </section></div>}
    </div>}
  </>;
}
