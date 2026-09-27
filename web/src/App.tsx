import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, cancelTask, getCapabilities, getTask, submitBalloon, submitRecognition, type Capability, type RecognitionResult, type Task } from "./api";
import ImageInput, { type ImageSelection } from "./ImageInput";
import Result from "./Result";
import { puzzleFromRecognition, type BalloonPuzzle, type BalloonSolveResult } from "./puzzle";

type ServiceState = "loading" | "ready" | "error";
type Operation = "recognition" | "solve";
const pause = (milliseconds: number, signal: AbortSignal) => new Promise<void>((resolve) => {
  if (signal.aborted) return resolve();
  const timer = window.setTimeout(() => { signal.removeEventListener("abort", stop); resolve(); }, milliseconds);
  const stop = () => { window.clearTimeout(timer); resolve(); };
  signal.addEventListener("abort", stop, { once: true });
});

function explain(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "QUEUE_FULL" || error.code === "UPLOAD_BUSY") return "当前任务较多，请稍后重试。";
    if (error.code === "INVALID_REQUEST") return "服务未能接受这张图片，请换一张清晰完整的截图重试。";
    if (error.code === "NOT_FOUND") return "任务已过期或服务重启，请重新识别。";
    return error.message;
  }
  return "请求未完成，请稍后重试。";
}

function recognitionFailure(value: RecognitionResult): string {
  if (value.outcome === "no_board") {
    const placed = value.issues?.find((issue) => issue.includes("已有气球摆放"));
    return placed || "未能从图片中定位完整棋盘。请上传包含完整棋盘和右侧所有气球库存的清晰截图重试。";
  }
  if (value.outcome === "invalid_image") return "图片无法读取、格式不支持或尺寸过大，请换一张清晰完整的截图重试。";
  if (value.outcome === "timeout") return "图片识别超时，请换一张清晰完整的截图重试。";
  return "图片识别失败，请稍后重试或换一张清晰完整的截图。";
}

export default function App() {
  const [service, setService] = useState<ServiceState>("loading");
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [serviceError, setServiceError] = useState("");
  const [task, setTask] = useState<Task | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [imageSelection, setImageSelection] = useState<ImageSelection | null>(null);
  const [workError, setWorkError] = useState("");
  const [recognitionNotes, setRecognitionNotes] = useState<string[]>([]);
  const [result, setResult] = useState<BalloonSolveResult | null>(null);
  const [submittedPuzzle, setSubmittedPuzzle] = useState<BalloonPuzzle | null>(null);
  const generation = useRef(0);
  const busy = useRef(false);
  const activeTaskId = useRef<string | null>(null);
  const pollController = useRef<AbortController | null>(null);
  const mounted = useRef(true);

  const invalidate = useCallback(() => {
    generation.current++;
    pollController.current?.abort();
    pollController.current = null;
    if (activeTaskId.current) void cancelTask(activeTaskId.current).catch(() => {});
    activeTaskId.current = null;
    busy.current = false;
    setTask(null); setResult(null); setSubmittedPuzzle(null); setWorkError(""); setSubmitting(false); setOperation(null);
    setRecognitionNotes([]);
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

  async function beginSolve(puzzle: BalloonPuzzle, version: number) {
    if (!mounted.current || generation.current !== version) return;
    setOperation("solve"); setTask(null); setSubmitting(true); setSubmittedPuzzle(puzzle);
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
              else setWorkError("服务返回了无法识别的求解结果，请稍后重试。");
            } else {
              const value = current.result as RecognitionResult | null;
              if (value?.outcome === "draft") {
                setRecognitionNotes((value.issues ?? []).filter((issue) => issue.includes("推导")));
                const checked = puzzleFromRecognition(value);
                if (checked.puzzle && canSolve) {
                  await beginSolve(checked.puzzle, version);
                  return;
                }
                busy.current = false;
                setWorkError(checked.error || "识别已完成，但求解服务当前不可用，请稍后重试。");
              } else {
                busy.current = false;
                setWorkError(value ? recognitionFailure(value) : "服务未返回有效识别结果，请重试。");
              }
            }
          } else if (current.status === "failed") { busy.current = false; setWorkError(current.error?.message || "任务失败，请稍后重试。"); }
          else { busy.current = false; setWorkError("任务已取消。"); }
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
    setWorkError("已取消本次识别与求解。正在运行的服务任务可能仍需片刻结束。");
  };

  return <div className="page">
    <header className="site-header"><div className="brand">终末地解谜助手</div><span className="header-note">浮空回收 · 图片识别与求解</span></header>
    <main>
      <div className="intro"><span className="eyebrow">解谜工具 / BALLOON</span><h1>浮空回收解谜</h1>
        <p>导入包含完整棋盘和右侧所有气球库存的清晰截图，点击一次识别并求解。默认上传完整原图，由服务自动定位棋盘。</p>
      </div>
      <div className="notice rule-note"><strong>平衡规则：</strong>以棋盘中心为支点，每个气球的升力分别乘以它到中心的行、列距离；左右和上下的加权升力各自相等。5×5 棋盘中，中心距离为 0，相邻格为 1，外圈为 2。每格至多一个气球，库存全部使用。</div>
      <div className="service-status" role="status" aria-live="polite">
        {service === "loading" ? "正在查询服务能力…" : service === "error" ? <><span>服务不可用：{serviceError}</span><button type="button" className="text-button" onClick={() => void refreshCapabilities()}>重试连接</button></>
          : balloon ? <span>服务状态：{balloon.solving_available ? "求解可用" : "求解暂不可用"} · {balloon.recognition_available ? "图片识别可用" : "图片识别暂不可用"}</span> : "服务未声明气球能力，暂不可提交。"}
      </div>
      <div className={`content-grid ${result ? "" : "no-result"}`}>
        <div className="left-column"><ImageInput onChanged={changeImage} />
          <section className="panel" aria-labelledby="recognize-title"><span className="eyebrow">识别与求解</span><h2 id="recognize-title">从图片得到答案</h2>
            <p className="muted">只有点击后才上传当前预览的图片。库存数字不完整时不会凭空猜测；只有当目标总升力能唯一确定缺失的升力或数量时才会推导补齐，并在下方标明推导来源。其余缺失字段仍需换一张完整清晰的截图重试。</p>
            <div className="row-actions"><button type="button" className="button primary" disabled={!canRecognize || !imageSelection || busy.current} onClick={() => void recognize()}>
              {submitting && operation === "recognition" ? "正在上传…" : operation === "recognition" && busy.current ? "正在识别…" : submitting && operation === "solve" ? "正在提交求解…" : operation === "solve" && busy.current ? "正在求解…" : "识别并求解"}</button>
              {busy.current && <button type="button" className="button secondary" onClick={cancel}>取消本次任务</button>}</div>
            {task && <p className="task-status" role="status" aria-live="polite">{operation === "recognition" ? "识别" : "求解"}任务状态：{{ queued: "排队中", running: "处理中", succeeded: "已完成", failed: "失败", cancelled: "已取消" }[task.status]}</p>}
            {recognitionNotes.length > 0 && <div className="notice" role="status">
              <strong>识别提示：</strong>{recognitionNotes.join(" ")}
            </div>}
            {workError && <div className="notice warning" role="alert">{workError}</div>}
          </section>
          <div className="future-note">源石电路 <span>后续支持</span></div></div>
        {result && submittedPuzzle && <div className="right-column"><section className="panel answer-panel" aria-label="求解结果"><span className="eyebrow">答案</span><Result result={result} puzzle={submittedPuzzle} /></section></div>}
      </div>
    </main>
    <footer>浮空回收支持图片识别与求解。源石电路后续支持。</footer>
  </div>;
}
