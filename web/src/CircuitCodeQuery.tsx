import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  getCircuitCatalogEntry,
  type CircuitCatalogEntry,
  type CircuitPuzzle,
} from "./api";
import { puzzleFromCircuitCandidate } from "./circuit";
import CircuitCatalogCandidates from "./CircuitCatalogCandidates";
import { msg, useAppTranslation, useMessages, type MessageText } from "./i18n";

type Props = {
  canQuery: boolean;
  canSolve: boolean;
  busy: boolean;
  onQueryStart: () => void;
  onSolve: (puzzle: CircuitPuzzle, displayPalette: unknown, source: MessageText) => void;
};

const dashes = "-֊־᐀᠆‐‑‒–—―−⸺⸻﹘﹣－";
const triangles = "△▲▵▴Δ∆";

function normalizeInput(value: string): string | null {
  const token = value.normalize("NFKC").replace(/[\s\uFE00-\uFE0F\u{E0100}-\u{E01EF}]/gu, "");
  const decoration = new RegExp(`^[${triangles}]?[${dashes.replace("-", "\\-")}]?`);
  const normalized = token.replace(decoration, "");
  return /^(?:V\d{5}|WL\d{4})$/.test(normalized) ? normalized : null;
}

function explain(error: unknown): MessageText {
  if (error instanceof ApiError) {
    if (error.code === "INVALID_CODE") return msg("query.errorInvalidCode", undefined, "circuit");
    if (error.code === "CATALOG_NOT_FOUND") return msg("query.errorNotFound", undefined, "circuit");
    if (error.code === "CATALOG_UNAVAILABLE") return msg("query.errorCatalogUnavailable", undefined, "circuit");
    if (error.code === "NETWORK_ERROR") return msg("query.errorNetwork", undefined, "circuit");
    return error.message;
  }
  return msg("query.errorFailed", undefined, "circuit");
}

export default function CircuitCodeQuery({ canQuery, canSolve, busy, onQueryStart, onSolve }: Props) {
  const { t } = useAppTranslation("circuit");
  const { render } = useMessages();
  const [code, setCode] = useState("");
  const [entry, setEntry] = useState<CircuitCatalogEntry | null>(null);
  const [error, setError] = useState<MessageText>("");
  const [notice, setNotice] = useState<MessageText>("");
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
      setError(msg("query.emptyCode", undefined, "circuit"));
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
        setError(msg("query.noCandidates", undefined, "circuit"));
        return;
      }
      if (candidates.length === 1) {
        const checked = puzzleFromCircuitCandidate(candidates[0]);
        if (!checked.puzzle) { setError(checked.error); return; }
        if (!canSolve) { setError(msg("query.solveUnavailable", undefined, "circuit")); return; }
        setNotice(msg("query.autoSolve", { code: result.code }, "circuit"));
        onSolve(checked.puzzle, candidates[0].display_palette, msg("answer.sourceCode", { code: result.code }, "circuit"));
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
    <div className="section-heading"><div><span className="eyebrow">{t("query.eyebrow")}</span>
      <h2 id="circuit-code-title">{t("query.heading")}</h2></div><span className="badge">{t("query.badge")}</span></div>
    <p className="muted">{t("query.description")}</p>
    <form className="code-form" onSubmit={(event) => void query(event)}>
      <label htmlFor="circuit-question-code">{t("query.label")}</label>
      <div className="code-row">
        <input id="circuit-question-code" name="circuit-question-code" value={code} placeholder={t("query.placeholder")}
          autoComplete="off" spellCheck={false} onChange={(event) => setCode(event.target.value)} />
        <button type="submit" className="button primary" disabled={loading || busy || !canQuery}>
          {loading ? t("query.loading") : t("query.submit")}
        </button>
      </div>
      <p className="muted small">{t("query.help")}</p>
    </form>
    {notice && <div className="notice" role="status">{render(notice)}</div>}
    {error && <div className="notice warning" role="alert">{render(error, "error")}</div>}
    {entry && (entry.candidates ?? []).length > 1 && <div className="catalog-entry">
      <p>{t("query.entryLine", { code: entry.code, count: (entry.candidates ?? []).length })}</p>
      <CircuitCatalogCandidates key={`${entry.code}-${entry.updated_at}`} candidates={entry.candidates ?? []}
        code={entry.code} disabled={busy || !canSolve} onSolve={onSolve} />
    </div>}
  </section>;
}
