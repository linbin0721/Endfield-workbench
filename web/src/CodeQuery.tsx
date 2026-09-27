import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, getCatalogEntry, type CatalogEntry } from "./api";
import CatalogCandidates, { catalogStatusText } from "./CatalogCandidates";
import type { BalloonPuzzle } from "./puzzle";
import { puzzleFromCandidate } from "./puzzle";

type Props = {
  canQuery: boolean;
  canSolve: boolean;
  busy: boolean;
  onQueryStart: () => void;
  onSolve: (puzzle: BalloonPuzzle, label: string) => void;
};

function explain(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "INVALID_CODE") return "题号格式无效：请输入 WL-A 加四位数字，例如 WL-A1001。";
    if (error.code === "CATALOG_NOT_FOUND") return "目录中还没有这个题号的完整题面记录。先用截图识别一次，完整题面就会记入目录。";
    if (error.code === "CATALOG_UNAVAILABLE") return "题号目录暂时不可用，请稍后重试，或改用截图识别。";
    return error.message;
  }
  return "查询未完成，请稍后重试。";
}

export default function CodeQuery({ canQuery, canSolve, busy, onQueryStart, onSolve }: Props) {
  const [code, setCode] = useState("");
  const [entry, setEntry] = useState<CatalogEntry | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const generation = useRef(0);
  const request = useRef<AbortController | null>(null);

  useEffect(() => () => {
    generation.current++;
    request.current?.abort();
  }, []);

  async function query(event: FormEvent) {
    event.preventDefault();
    const value = code.trim();
    if (!value) { setError("请输入题号，例如 WL-A1001。"); return; }
    onQueryStart();
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const version = ++generation.current;
    setLoading(true); setError(""); setNotice(""); setEntry(null);
    try {
      const result = await getCatalogEntry(value, controller.signal);
      if (controller.signal.aborted || version !== generation.current) return;
      setEntry(result);
      const candidates = result.candidates ?? [];
      if (candidates.length === 1) {
        const checked = puzzleFromCandidate(candidates[0]);
        if (!checked.puzzle) { setError(checked.error); return; }
        if (!canSolve) { setError("求解服务当前不可用，请稍后重试。"); return; }
        setNotice(`目录中只有唯一候选，已直接提交求解（记录状态：${catalogStatusText(result.status)}）。`);
        onSolve(checked.puzzle, `题号 ${result.code}`);
      }
    } catch (caught) {
      if (controller.signal.aborted || version !== generation.current) return;
      setError(explain(caught));
    } finally {
      if (request.current === controller) request.current = null;
      if (!controller.signal.aborted && version === generation.current) setLoading(false);
    }
  }

  return <section className="panel" aria-labelledby="code-title">
    <div className="section-heading"><div><span className="eyebrow">按题号</span><h2 id="code-title">用题号直接取题</h2></div>
      <span className="badge">目录复用</span></div>
    <p className="muted">输入完整截图识别过的题号，直接使用目录中经过校验的题面求解，不必重新上传图片。
      争议记录会列出全部候选，由你选择后再求解。</p>
    <form className="code-form" onSubmit={(event) => void query(event)}>
      <label htmlFor="question-code">题号</label>
      <div className="code-row">
        <input id="question-code" name="question-code" value={code} placeholder="WL-A1001" autoComplete="off"
          spellCheck={false} onChange={(event) => setCode(event.target.value)} />
        <button type="submit" className="button primary" disabled={loading || busy || !canQuery}>
          {loading ? "正在查询…" : "查询并求解"}</button>
      </div>
      <p className="muted small">只接受 WL-A 加四位数字；大小写与空格会自动规范化。</p>
    </form>
    {notice && <div className="notice" role="status">{notice}</div>}
    {error && <div className="notice warning" role="alert">{error}</div>}
    {entry && <div className="catalog-entry">
      <p><strong>{entry.code}</strong> · 目录状态：{catalogStatusText(entry.status)} · 候选 {(entry.candidates ?? []).length} 个</p>
      {(entry.candidates ?? []).length > 1 && <>
        <p className="muted small">该题号存在多个不同题面，均已保留。请核对库存与目标总升力后选择正确候选。</p>
        <CatalogCandidates key={`${entry.code}-${entry.updated_at}`} candidates={entry.candidates ?? []}
          code={entry.code} disabled={busy || !canSolve} onSolve={onSolve} />
      </>}
    </div>}
  </section>;
}
