import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { gameData } from "../../calculator/data.ts";
import { preloadCharacterAvatars } from "../../calculator/avatarPreload.ts";
import EntityIcon from "../../calculator/EntityIcon.tsx";
import { ATTRIBUTE_NAMES, DEFAULT_REQUEST, type SearchRequest, type SearchResult, type Solution, type WorkerRequest, type WorkerResponse } from "../../calculator/types.ts";
import { localizePath, msg, useAppTranslation, useMessages, type MessageText } from "../../i18n";
import { Button } from "../../ui/Button/Button";
import { CloseIcon, RefreshIcon, SearchIcon } from "../../ui/icons";
import { Notice } from "../../ui/Notice/Notice";
import { PageHeader } from "../../ui/PageHeader/PageHeader";
import { Panel } from "../../ui/Panel/Panel";
import { SectionTitle } from "../../ui/SectionTitle/SectionTitle";
import { SegmentedControl } from "../../ui/SegmentedControl/SegmentedControl";
import { useChangeCount } from "../../ui/useChangeCount";
import { BuildBench } from "./BuildBench";
import { CharacterPicker } from "./CharacterPicker";
import { LevelControl } from "./LevelControl";
import {
  DEFAULT_CHARACTER,
  POTENTIAL_CHOICES,
  REFINE_CHOICES,
  TARGET,
  attributeName,
  characterById,
  characterDisplayName,
  clamp,
  describeError,
  formatCount,
  formatDuration,
  normalizeResult,
  solutionCopyText,
  writeClipboard,
  type AdvancedLimits,
  type CopyNotice,
} from "./model";
import { ResultTable } from "./ResultTable";
import b from "./bench.module.css";
import s from "./calculator.module.css";

/** Advanced search limits, shown as small segmented switches. */
const LIMIT_FIELDS: { key: keyof AdvancedLimits; max: number; labelKey: string }[] = [
  { key: "maxGearRefine", max: 3, labelKey: "form.maxGearRefine" },
  { key: "maxWeaponRefine", max: 5, labelKey: "form.maxWeaponRefine" },
  { key: "maxGemFirst", max: 6, labelKey: "form.maxGemFirst" },
  { key: "maxGemPassive", max: 3, labelKey: "form.maxGemPassive" },
];
const EMPTY_SLOTS = ["slot.armor", "slot.gauntlet", "slot.accessory", "slot.accessory"] as const;

/** The bench before any result: the chosen operator and empty slots. */
function EmptyBench({ character, level, potential, busy }: {
  character: NonNullable<typeof DEFAULT_CHARACTER>;
  level: number;
  potential: number | "any";
  busy: boolean;
}) {
  const { t } = useAppTranslation("calculator");
  const name = characterDisplayName(character);
  return <div className={b.bench} data-empty="" data-busy={busy || undefined}>
    <header className={b.benchHead}>
      <EntityIcon kind="characters" id={character.id} name={name} size={88} />
      <div className={b.benchTitle}>
        <span className={b.benchIndex}>{t("bench.preview")}</span>
        <h3 className={b.benchName}>{name}</h3>
        <span className={b.benchMeta}>{t("solution.meta", { level, potential: potential === "any" ? t("form.potentialAnyShort") : potential })}</span>
      </div>
    </header>
    <div className={b.loadout}>
      <div className={b.weapon} data-empty=""><span className={b.slotLabel}>{t("bench.weaponSlot")}</span></div>
      <div className={b.gear}>
        {EMPTY_SLOTS.map((key, index) => <div key={index} className={b.slot} data-empty="">
          <span className={b.slotLabel}>{key === "slot.accessory" ? t(key, { index: index - 1 }) : t(key)}</span>
        </div>)}
      </div>
    </div>
  </div>;
}

export default function CalculatorBench() {
  const { t, locale } = useAppTranslation("calculator");
  const { render, tm } = useMessages();
  const [characterId, setCharacterId] = useState(DEFAULT_CHARACTER?.id ?? "");
  const [levelText, setLevelText] = useState(() => String(DEFAULT_REQUEST.level));
  const [potential, setPotential] = useState<number | "any">(DEFAULT_REQUEST.potential);
  const [required, setRequired] = useState<number[]>(() => [...DEFAULT_REQUEST.required]);
  const [limits, setLimits] = useState<AdvancedLimits>(() => ({
    maxGearRefine: DEFAULT_REQUEST.maxGearRefine,
    maxWeaponRefine: DEFAULT_REQUEST.maxWeaponRefine,
    maxGemFirst: DEFAULT_REQUEST.maxGemFirst,
    maxGemPassive: DEFAULT_REQUEST.maxGemPassive,
  }));
  const [running, setRunning] = useState(false);
  const [phase, setPhase] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [searchedRequired, setSearchedRequired] = useState<number[]>([]);
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState<MessageText>("");
  const [statusNote, setStatusNote] = useState<MessageText>("");
  const [copyNotice, setCopyNotice] = useState<CopyNotice>(null);
  const workerRef = useRef<Worker | null>(null);
  const runRef = useRef(0);
  const busyRef = useRef(false);

  const character = characterById.get(characterId) ?? DEFAULT_CHARACTER;
  const maxLevel = character?.maxLevel ?? DEFAULT_REQUEST.level;
  const parsedLevel = Number(levelText);
  const levelValid = levelText.trim() !== "" && Number.isInteger(parsedLevel) && parsedLevel >= 1 && parsedLevel <= maxLevel;
  const level = levelValid ? parsedLevel : clamp(Number.isFinite(parsedLevel) ? Math.round(parsedLevel) : 1, 1, maxLevel);

  useEffect(() => { document.title = t("title"); }, [t, locale]);
  useEffect(() => preloadCharacterAvatars(gameData.characters.map((item) => item.id), DEFAULT_CHARACTER?.id), []);

  const releaseWorker = useCallback(() => {
    runRef.current += 1;
    const worker = workerRef.current;
    workerRef.current = null;
    if (!worker) return;
    worker.onmessage = null;
    worker.onerror = null;
    worker.onmessageerror = null;
    worker.terminate();
  }, []);

  useEffect(() => releaseWorker, [releaseWorker]);

  const resetSearch = useCallback(() => {
    releaseWorker();
    busyRef.current = false;
    setRunning(false);
    setPhase("");
    setResult(null);
    setError("");
    setStatusNote("");
    setCopyNotice(null);
  }, [releaseWorker]);

  const failSearch = useCallback((worker: Worker, run: number, message: MessageText) => {
    if (workerRef.current !== worker || runRef.current !== run) return;
    releaseWorker();
    busyRef.current = false;
    setRunning(false);
    setPhase("");
    setError(message);
  }, [releaseWorker]);

  const finishSearch = useCallback((worker: Worker, run: number, payload: unknown) => {
    if (workerRef.current !== worker || runRef.current !== run) return;
    releaseWorker();
    busyRef.current = false;
    setRunning(false);
    setPhase("");
    const { result: normalized, dropped } = normalizeResult(payload);
    if (!normalized || dropped) {
      setError(msg("error.incompleteResult", undefined, "calculator"));
      return;
    }
    setSelected(0);
    setResult(normalized);
  }, [releaseWorker]);

  const startSearch = useCallback(() => {
    if (busyRef.current || !character || !levelValid) return;
    resetSearch();
    const run = runRef.current;
    const request: SearchRequest = {
      characterId: character.id,
      level,
      potential,
      target: TARGET,
      required: [...required].sort((left, right) => left - right),
      maxGearRefine: limits.maxGearRefine,
      maxWeaponRefine: limits.maxWeaponRefine,
      maxGemFirst: limits.maxGemFirst,
      maxGemPassive: limits.maxGemPassive,
      budgetMs: DEFAULT_REQUEST.budgetMs,
      limit: DEFAULT_REQUEST.limit,
    };
    let worker: Worker;
    if (typeof Worker === "undefined") {
      setError(msg("error.workerCreate", { message: msg("error.workerUnsupported", undefined, "calculator") }, "calculator"));
      return;
    }
    try {
      worker = new Worker(new URL("../../calculator/search.worker.ts", import.meta.url), { type: "module" });
    } catch (creationError) {
      setError(msg("error.workerCreate", { message: describeError(creationError) || msg("error.unknown", undefined, "calculator") }, "calculator"));
      return;
    }
    workerRef.current = worker;
    busyRef.current = true;
    setRunning(true);
    setPhase("");
    setError("");
    setResult(null);
    setStatusNote("");
    setCopyNotice(null);
    setSearchedRequired(request.required);
    worker.onmessage = (event: MessageEvent<unknown>) => {
      const data = event.data as WorkerResponse | null | undefined;
      if (!data || typeof data !== "object") return;
      if (data.type === "progress") {
        if (workerRef.current === worker && runRef.current === run && typeof data.phase === "string") {
          setPhase(data.phase);
        }
        return;
      }
      if (data.type === "done") { finishSearch(worker, run, data.result); return; }
      if (data.type === "error") {
        failSearch(worker, run, typeof data.message === "string" && data.message
          ? data.message : msg("error.failed", undefined, "calculator"));
      }
    };
    worker.onerror = (event: ErrorEvent) => {
      event.preventDefault();
      failSearch(worker, run, event.message
        ? msg("error.workerError", { message: event.message }, "calculator")
        : msg("error.workerErrorGeneric", undefined, "calculator"));
    };
    worker.onmessageerror = () => failSearch(worker, run, msg("error.workerMessageParse", undefined, "calculator"));
    const message: WorkerRequest = { type: "search", request };
    try {
      worker.postMessage(message);
    } catch (postError) {
      failSearch(worker, run, msg("error.workerPost", {
        message: describeError(postError) || msg("error.unknown", undefined, "calculator") }, "calculator"));
    }
  }, [character, failSearch, finishSearch, level, levelValid, limits, potential, required, resetSearch]);

  const cancelSearch = () => {
    if (!busyRef.current) return;
    resetSearch();
    setStatusNote(msg("cancelled", undefined, "calculator"));
  };

  const changeCharacter = (nextId: string) => {
    resetSearch();
    const next = characterById.get(nextId);
    setCharacterId(nextId);
    if (next) {
      const current = Number.parseInt(levelText, 10);
      const kept = Number.isFinite(current) ? clamp(current, 1, next.maxLevel) : next.maxLevel;
      setLevelText(String(kept));
    }
  };

  const changeLevel = (value: string) => {
    resetSearch();
    setLevelText(value);
  };

  const normalizeLevel = () => { setLevelText(String(level)); };

  const changePotential = (value: string) => {
    resetSearch();
    setPotential(value === "any" ? "any" : Number.parseInt(value, 10));
  };

  const toggleRequired = (index: number) => {
    resetSearch();
    setRequired((current) => current.includes(index)
      ? current.filter((value) => value !== index)
      : [...current, index].sort((left, right) => left - right));
  };

  const changeLimit = (key: keyof AdvancedLimits, value: string) => {
    resetSearch();
    setLimits((current) => ({ ...current, [key]: Number.parseInt(value, 10) }));
  };

  const copySolution = async (index: number, solution: Solution) => {
    if (!character) return;
    const copied = await writeClipboard(solutionCopyText(solution, index, character, t));
    setCopyNotice({
      solutionIndex: index,
      ok: copied,
      message: msg(copied ? "solution.copied" : "solution.copyFailed", undefined, "calculator"),
    });
  };

  const resultKey = useChangeCount(result);
  if (!character) {
    return <Notice tone="danger" role="alert">{t("noData")}</Notice>;
  }

  const notes = result?.notes ?? [];
  const chosen = result?.results[selected] ?? result?.results[0] ?? null;
  return <div className={b.page}>
    <PageHeader eyebrow={t("eyebrow")} title={t("heading")}>{t("intro", { target: TARGET })}</PageHeader>
    <div className={b.layout}>
      <Panel as="section" aria-labelledby="calc-form-title">
        <SectionTitle id="calc-form-title" aside={<span className={b.targetChip}><small>{t("form.targetLabel")}</small>{TARGET}</span>}>
          {t("form.heading")}
        </SectionTitle>
        <form className={s.form} onSubmit={(event) => { event.preventDefault(); startSearch(); }}>
          <div className={s.field}>
            <span className={s.label} id="calc-character-label">{t("form.character")}</span>
            <CharacterPicker id="calc-character" labelId="calc-character-label" character={character}
              characters={gameData.characters} onSelect={changeCharacter} />
          </div>
          <LevelControl id="calc-level" label={t("form.level", { max: maxLevel })} text={levelText} level={level}
            max={maxLevel} valid={levelValid} invalidText={t("form.levelInvalid", { max: maxLevel })}
            decreaseLabel={t("level.decrease")} increaseLabel={t("level.increase")} sliderLabel={t("level.slider")}
            onText={changeLevel} onBlur={normalizeLevel} />
          <div className={s.field}>
            <span className={s.label}>{t("form.potential")}</span>
            <SegmentedControl block className={s.segments} aria-label={t("form.potential")} value={String(potential)} onValueChange={changePotential}
              segments={POTENTIAL_CHOICES.map((choice) => ({
                value: String(choice),
                label: choice === "any" ? t("form.potentialAnyShort") : String(choice),
              }))} />
          </div>
          <fieldset className={s.fieldset}>
            <legend className={s.legend}>{t("form.requiredLegend", { target: TARGET })}</legend>
            <p className={`${s.text} ${s.small}`}>{t("form.requiredHelp", { target: TARGET })}</p>
            <div className={s.chips}>
              {ATTRIBUTE_NAMES.map((name, index) => <label className={s.chip} key={name} htmlFor={`calc-required-${index}`}>
                <input id={`calc-required-${index}`} type="checkbox" checked={required.includes(index)}
                  onChange={() => toggleRequired(index)} />
                <span>{attributeName(index, t)}</span>
              </label>)}
            </div>
          </fieldset>
          <details className={s.advanced}>
            <summary>{t("form.advanced")}</summary>
            <div className={s.advancedBody}>
              <p className={`${s.text} ${s.small}`}>{t("form.advancedHelp")}</p>
              {LIMIT_FIELDS.map((field) => <div className={s.field} key={field.key}>
                <span className={s.label}>{t(field.labelKey)}</span>
                <SegmentedControl size="sm" block className={s.segments} aria-label={t(field.labelKey)} value={String(limits[field.key])}
                  onValueChange={(value) => changeLimit(field.key, value)}
                  segments={REFINE_CHOICES(field.max).map((value) => ({ value: String(value), label: String(value) }))} />
              </div>)}
            </div>
          </details>
          <div className={s.actions}>
            <Button type="submit" variant="accent" icon={<SearchIcon />} disabled={running || !levelValid}>
              {running ? t("form.searching") : t("form.start")}
            </Button>
            {running && <Button variant="secondary" icon={<CloseIcon />} onClick={cancelSearch}>{t("form.cancel")}</Button>}
          </div>
        </form>
      </Panel>

      <div className={b.main}>
        {running && <div className={b.progress} role="status" aria-live="polite" data-calc="progress">
          <p>{t("progress.searching", { phase: phase ? tm(phase) : t("progress.preparing") })}</p>
          <div className={b.progressTrack} aria-hidden="true"><span /></div>
          <Button variant="secondary" size="sm" icon={<CloseIcon />} onClick={cancelSearch}>{t("form.cancel")}</Button>
        </div>}
        {!running && error && <Panel as="section" role="alert" data-calc="error">
          <SectionTitle>{t("error.title")}</SectionTitle>
          <Notice tone="danger">{render(error, "error")}</Notice>
          <div className={b.actions}>
            <Button variant="accent" icon={<RefreshIcon />} disabled={!levelValid} onClick={startSearch}>{t("error.retry")}</Button>
          </div>
        </Panel>}
        {!running && !error && statusNote && <Notice tone="info" role="status">{render(statusNote)}</Notice>}

        {!running && result && <Panel as="section" aria-labelledby="calc-results-title" data-calc="results">
          <SectionTitle id="calc-results-title">{t("results.heading")}</SectionTitle>
          <div className={b.summary}>
            <span>{t("results.elapsed", { duration: formatDuration(result.elapsedMs, t) })}</span>
            <span>{t("results.evaluated", { count: formatCount(result.candidates, "0") })}</span>
            <span data-complete={result.complete || undefined}>{t(result.complete ? "results.complete" : "results.limited")}</span>
            <span>{t("results.solutionCount", { count: result.results.length, limit: DEFAULT_REQUEST.limit })}</span>
          </div>
          <div className={b.notices}>
            {!result.complete && <Notice tone="warning">
              <p>{t("results.timeoutNotice")}</p>
              {result.results.length === 0 && <p>{t("results.timeoutEmpty")}</p>}
            </Notice>}
            {result.complete && result.results.length === 0 && <Notice tone="info">{t("results.completeEmpty", { target: TARGET })}</Notice>}
            {result.complete && result.results.length > 0 && <p className={b.note}>{t("results.completeSorted", { target: TARGET })}</p>}
            {notes.length > 0 && <ul className={b.noteList}>{notes.map((note, index) => <li key={`${index}-${note}`}>{tm(note)}</li>)}</ul>}
          </div>
          {result.results.length > 0 && <ResultTable key={resultKey} results={result.results} selected={selected} onSelect={setSelected} />}
        </Panel>}

        <Panel as="section" corners className={b.benchPanel} aria-label={t("bench.panelLabel")} data-calc={!running && !error && !result ? "empty" : undefined}>
          {!running && chosen
            ? <BuildBench key={`${resultKey}-${selected}`} solution={chosen} index={selected} character={character}
              required={searchedRequired} copyNotice={copyNotice} onCopy={() => void copySolution(selected, chosen)} />
            : <>
              <EmptyBench character={character} level={level} potential={potential} busy={running} />
              {!running && !result && <ul className={b.noteList}>
                <li>{t("results.emptyHint")}</li>
                <li>{t("results.emptyNote1", { target: TARGET })}</li>
                <li>{t("results.emptyNote2")}</li>
                <li>{t("results.emptyNote3")}</li>
              </ul>}
            </>}
        </Panel>
      </div>
    </div>
    <Panel as="section" aria-labelledby="calc-about-title">
      <SectionTitle id="calc-about-title">{t("about.title")}</SectionTitle>
      <div className={s.about}>
        <ul className={s.notes}>
          <li>{t("about.note1")}</li>
          <li>{t("about.note2")}</li>
          <li>{t("about.note3")}</li>
          <li>{t("about.note4")}</li>
          <li>{t("about.note5")}</li>
        </ul>
        <p className={s.source}>{t("about.sourcePrefix")}<a href={gameData.source} target="_blank" rel="noopener noreferrer">{gameData.source}</a>
          {" · "}{t("about.version", { version: gameData.version })}{" · "}{t("about.updated", { date: gameData.sourceUpdatedAt })}</p>
        <p className={s.source}>{t("about.iconSourcePrefix")}<a href="https://www.akedata.wiki/" target="_blank" rel="noopener noreferrer">{t("about.wiki")}</a>{t("about.iconSourceSuffix")}</p>
        <p className={s.source}>{t("about.disclaimer")}</p>
        <p className={s.links}>{t("about.otherTools")}<Link to={localizePath("/balloon", locale)}>{t("about.balloonLink")}</Link><Link to={localizePath("/circuit", locale)}>{t("about.circuitLink")}</Link></p>
      </div>
    </Panel>
  </div>;
}
