import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  getCircuitCatalogEntry,
  type CircuitCatalogEntry,
  type CircuitPuzzle,
} from "./api";
import { puzzleFromCircuitCandidate } from "./circuit";
import CircuitCatalogCandidates from "./CircuitCatalogCandidates";

type Props = {
  canQuery: boolean;
  canSolve: boolean;
  busy: boolean;
  onQueryStart: () => void;
  onSolve: (puzzle: CircuitPuzzle, label: string) => void;
};

const dashes = "-֊־᐀᠆‐‑‒–—―−⸺⸻﹘﹣－";
const triangles = "△▲▵▴Δ∆";

function normalizeInput(value: string): string | null {
  const token = value.normalize("NFKC").replace(/[\s\uFE00-\uFE0F\u{E0100}-\u{E01EF}]/gu, "");
  const decoration = new RegExp(`^[${triangles}]?[${dashes.replace("-", "\\-")}]?`);
  const normalized = token.replace(decoration, "");
  return /^(?:V\d{5}|WL\d{4})$/.test(normalized) ? normalized : null;
}

function explain(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "INVALID_CODE") return "题号格式无效：请输入 V 加五位数字或 WL 加四位数字。";
    if (error.code === "CATALOG_NOT_FOUND") return "目录中还没有这个题号的完整题面。请先用截图识别，或核对题号后重试。";
    if (error.code === "CATALOG_UNAVAILABLE") return "题号目录暂时不可用，请稍后重试，或改用截图识别。";
    if (error.code === "NETWORK_ERROR") return "无法连接解题服务，请检查网络后重试。";
    return error.message;
  }
  return "查询未完成，请稍后重试。";
}

export default function CircuitCodeQuery({ canQuery, canSolve, busy, onQueryStart, onSolve }: Props) {
  const [code, setCode] = useState("");
  const [entry, setEntry] = useState<CircuitCatalogEntry | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const generation = useRef(0);
  const request = useRef<AbortController | null>(null);

  useEffect(() => () => {
    generation.current++;
    request.current?.abort();
  }, []);

  async function query(event: FormEvent) {
    event.preventDefault();
    const normalized = normalizeInput(code);
    if (!normalized) {
      setError("请输入 V 加五位数字或 WL 加四位数字，例如 V40020 或 WL0020。");
      return;
    }
    request.current?.abort();
    onQueryStart();
    const controller = new AbortController();
    request.current = controller;
    const version = ++generation.current;
    setLoading(true); setError(""); setNotice(""); setEntry(null);
    try {
      const result = await getCircuitCatalogEntry(normalized, controller.signal);
      if (controller.signal.aborted || version !== generation.current) return;
      setEntry(result);
      const candidates = result.candidates ?? [];
      if (candidates.length === 0) {
        setError("目录中没有可用于求解的完整题面变体。");
        return;
      }
      if (candidates.length === 1) {
        const checked = puzzleFromCircuitCandidate(candidates[0]);
        if (!checked.puzzle) { setError(checked.error); return; }
        if (!canSolve) { setError("源石电路求解服务当前不可用，请稍后重试。"); return; }
        setNotice(`题号 ${result.code} 只有一个题面变体，已自动提交求解。`);
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

  return <section className="panel" aria-labelledby="circuit-code-title">
    <div className="section-heading"><div><span className="eyebrow">按题号</span>
      <h2 id="circuit-code-title">用题号直接取题</h2></div><span className="badge">目录复用</span></div>
    <p className="muted">输入题号后读取目录中经过校验的题面。同一题号可能有多个正常变体，届时请根据约束、棋盘和库存选择。</p>
    <form className="code-form" onSubmit={(event) => void query(event)}>
      <label htmlFor="circuit-question-code">题号</label>
      <div className="code-row">
        <input id="circuit-question-code" name="circuit-question-code" value={code} placeholder="V40020 或 WL0020"
          autoComplete="off" spellCheck={false} onChange={(event) => setCode(event.target.value)} />
        <button type="submit" className="button primary" disabled={loading || busy || !canQuery}>
          {loading ? "正在查询…" : "查询并求解"}
        </button>
      </div>
      <p className="muted small">接受 V 加五位数字或 WL 加四位数字；装饰三角、连字符和空格会自动规范化。</p>
    </form>
    {notice && <div className="notice" role="status">{notice}</div>}
    {error && <div className="notice warning" role="alert">{error}</div>}
    {entry && (entry.candidates ?? []).length > 1 && <div className="catalog-entry">
      <p><strong>{entry.code}</strong> · 正常题面变体 {(entry.candidates ?? []).length} 个</p>
      <CircuitCatalogCandidates key={`${entry.code}-${entry.updated_at}`} candidates={entry.candidates ?? []}
        code={entry.code} disabled={busy || !canSolve} onSolve={onSolve} />
    </div>}
  </section>;
}
