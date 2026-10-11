import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, getCatalogEntry, type CatalogEntry } from "./api";
import CatalogCandidates, { catalogStatusRef, catalogStatusText } from "./CatalogCandidates";
import { msg, useAppTranslation, useMessages, type MessageText } from "./i18n";
import type { BalloonPuzzle } from "./puzzle";
import { puzzleFromCandidate } from "./puzzle";

type Props = {
  canQuery: boolean;
  canSolve: boolean;
  busy: boolean;
  onQueryStart: () => void;
  onSolve: (puzzle: BalloonPuzzle, source: MessageText) => void;
};

function explain(error: unknown): MessageText {
  if (error instanceof ApiError) {
    if (error.code === "INVALID_CODE") return msg("query.errorInvalidCode", undefined, "balloon");
    if (error.code === "CATALOG_NOT_FOUND") return msg("query.errorNotFound", undefined, "balloon");
    if (error.code === "CATALOG_UNAVAILABLE") return msg("query.errorCatalogUnavailable", undefined, "balloon");
    return error.message;
  }
  return msg("query.errorFailed", undefined, "balloon");
}

export default function CodeQuery({ canQuery, canSolve, busy, onQueryStart, onSolve }: Props) {
  const { t } = useAppTranslation("balloon");
  const { render } = useMessages();
  const [code, setCode] = useState("");
  const [entry, setEntry] = useState<CatalogEntry | null>(null);
  const [error, setError] = useState<MessageText>("");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<MessageText>("");
  const generation = useRef(0);
  const request = useRef<AbortController | null>(null);

  useEffect(() => () => {
    generation.current++;
    request.current?.abort();
  }, []);

  async function query(event: FormEvent) {
    event.preventDefault();
    const value = code.trim();
    if (!value) { setError(msg("query.emptyCode", undefined, "balloon")); return; }
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
        if (!canSolve) { setError(msg("query.solveUnavailable", undefined, "balloon")); return; }
        setNotice(msg("query.autoSolve", { status: catalogStatusRef(result.status) }, "balloon"));
        onSolve(checked.puzzle, msg("answer.sourceCode", { code: result.code }, "balloon"));
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
    <div className="section-heading"><div><span className="eyebrow">{t("query.eyebrow")}</span><h2 id="code-title">{t("query.heading")}</h2></div>
      <span className="badge">{t("query.badge")}</span></div>
    <p className="muted">{t("query.description")}</p>
    <form className="code-form" onSubmit={(event) => void query(event)}>
      <label htmlFor="question-code">{t("query.label")}</label>
      <div className="code-row">
        <input id="question-code" name="question-code" value={code} placeholder="WL-A1001" autoComplete="off"
          spellCheck={false} onChange={(event) => setCode(event.target.value)} />
        <button type="submit" className="button primary" disabled={loading || busy || !canQuery}>
          {loading ? t("query.loading") : t("query.submit")}</button>
      </div>
      <p className="muted small">{t("query.help")}</p>
    </form>
    {notice && <div className="notice" role="status">{render(notice)}</div>}
    {error && <div className="notice warning" role="alert">{render(error, "error")}</div>}
    {entry && <div className="catalog-entry">
      <p>{t("query.entryLine", { code: entry.code, status: catalogStatusText(t, entry.status),
        count: (entry.candidates ?? []).length })}</p>
      {(entry.candidates ?? []).length > 1 && <>
        <p className="muted small">{t("query.multiple")}</p>
        <CatalogCandidates key={`${entry.code}-${entry.updated_at}`} candidates={entry.candidates ?? []}
          code={entry.code} disabled={busy || !canSolve} onSolve={onSolve} />
      </>}
    </div>}
  </section>;
}
