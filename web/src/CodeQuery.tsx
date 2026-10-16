import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, getCatalogEntry, type CatalogEntry } from "./api";
import CatalogCandidates, { catalogStatusRef, catalogStatusText } from "./CatalogCandidates";
import { msg, useAppTranslation, useMessages, type MessageText } from "./i18n";
import type { BalloonPuzzle } from "./puzzle";
import { SectionHead } from "./features/puzzles/PuzzleParts";
import s from "./features/puzzles/puzzles.module.css";
import { Button } from "./ui/Button/Button";
import { SearchIcon } from "./ui/icons";
import { Notice } from "./ui/Notice/Notice";
import { Panel } from "./ui/Panel/Panel";
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

  return <Panel as="section" aria-labelledby="code-title">
    <SectionHead eyebrow={t("query.eyebrow")} title={t("query.heading")} id="code-title" badge={t("query.badge")} />
    <p className={s.text}>{t("query.description")}</p>
    <form className={s.form} onSubmit={(event) => void query(event)}>
      <label className={s.label} htmlFor="question-code">{t("query.label")}</label>
      <div className={s.codeRow}>
        <input id="question-code" name="question-code" className={`${s.input} ${s.codeInput}`} value={code} placeholder="WL-A1001"
          autoComplete="off" spellCheck={false} onChange={(event) => setCode(event.target.value)} />
        <Button type="submit" variant="accent" icon={<SearchIcon />} disabled={loading || busy || !canQuery}>
          {loading ? t("query.loading") : t("query.submit")}</Button>
      </div>
      <p className={`${s.text} ${s.small}`}>{t("query.help")}</p>
    </form>
    <div className={s.stack}>
      {notice && <Notice tone="info" role="status">{render(notice)}</Notice>}
      {error && <Notice tone="danger" role="alert">{render(error, "error")}</Notice>}
    </div>
    {entry && <div className={s.entry}>
      <p>{t("query.entryLine", { code: entry.code, status: catalogStatusText(t, entry.status),
        count: (entry.candidates ?? []).length })}</p>
      {(entry.candidates ?? []).length > 1 && <>
        <p className={`${s.text} ${s.small}`}>{t("query.multiple")}</p>
        <CatalogCandidates key={`${entry.code}-${entry.updated_at}`} candidates={entry.candidates ?? []}
          code={entry.code} disabled={busy || !canSolve} onSolve={onSolve} />
      </>}
    </div>}
  </Panel>;
}
