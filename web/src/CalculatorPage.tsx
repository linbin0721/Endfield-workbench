import { useCallback, useEffect, useRef, useState } from "react";
import type { TFunction } from "i18next";
import { Link } from "react-router-dom";
import { gameData } from "./calculator/data.ts";
import EntityIcon from "./calculator/EntityIcon.tsx";
import { preloadCharacterAvatars } from "./calculator/avatarPreload.ts";
import { localizedName, localizePath, msg, useAppTranslation, useMessages, type MessageText } from "./i18n";
import {
  ATTRIBUTE_NAMES,
  DEFAULT_REQUEST,
  type Character,
  type Equipment,
  type Evaluation,
  type GearSelection,
  type Modifier,
  type SearchRequest,
  type SearchResult,
  type Solution,
  type Weapon,
  type WorkerRequest,
  type WorkerResponse,
} from "./calculator/types.ts";
import "./calculator.css";

const TARGET = DEFAULT_REQUEST.target;
const POTENTIAL_CHOICES: (number | "any")[] = [0, 1, 2, 3, 4, 5, "any"];
const REFINE_CHOICES = (max: number) => Array.from({ length: max + 1 }, (_, value) => value);
/** Display order of the four stats; the domain keeps ATTRIBUTE_NAMES untouched. */
const ATTRIBUTE_KEYS = ["strength", "agility", "intellect", "will"] as const;

const characterById = new Map(gameData.characters.map((item) => [item.id, item]));
const weaponById = new Map(gameData.weapons.map((item) => [item.id, item]));
const equipmentById = new Map(gameData.equipment.map((item) => [item.id, item]));
const setById = new Map(gameData.sets.map((item) => [item.id, item]));
const DEFAULT_CHARACTER: Character | undefined =
  characterById.get(DEFAULT_REQUEST.characterId) ??
  (gameData.characters.length > 0 ? gameData.characters[0] : undefined);

type AdvancedLimits = {
  maxGearRefine: number;
  maxWeaponRefine: number;
  maxGemFirst: number;
  maxGemPassive: number;
};
type CopyNotice = { solutionIndex: number; ok: boolean; message: MessageText } | null;
type EquipmentEntry = { slot: number; accessory: number; gear: GearSelection; item: Equipment | undefined };

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

function formatValue(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function formatCount(value: unknown, fallback = "?"): string {
  return typeof value === "number" && Number.isFinite(value) ? String(Math.trunc(value)) : fallback;
}

function formatDuration(milliseconds: unknown, t: TFunction): string {
  if (typeof milliseconds !== "number" || !Number.isFinite(milliseconds) || milliseconds < 0) return "—";
  if (milliseconds < 1000) return t("duration.milliseconds", { value: Math.round(milliseconds) });
  return t("duration.seconds", { value: (milliseconds / 1000).toFixed(1) });
}

function readVector(vector: unknown, index: number): number | null {
  if (!Array.isArray(vector)) return null;
  const value: unknown = vector[index];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function matchedSet(evaluation: Evaluation): Set<number> {
  const matched = new Set<number>();
  if (!Array.isArray(evaluation.matched)) return matched;
  for (const value of evaluation.matched) {
    if (typeof value === "number" && Number.isInteger(value) && value >= 0 && value < ATTRIBUTE_NAMES.length) {
      matched.add(value);
    }
  }
  return matched;
}

const POSITION_SLOTS = [0, 1, 2, 2];

/** Slots are 0 armor, 1 gauntlet, 2 accessory; sort by data slot and fall back to the build's slot order.
 * An empty id is a legal "unequipped" slot, so it keeps the position-derived label. */
function orderEquipment(equipment: GearSelection[]): EquipmentEntry[] {
  const entries = equipment.map((gear, position) => {
    const item = equipmentById.get(gear.id);
    return { gear, position, item, slot: item ? item.slot : POSITION_SLOTS[position] ?? 2 };
  });
  entries.sort((left, right) => left.slot - right.slot || left.position - right.position);
  let accessories = 0;
  return entries.map(({ gear, item, slot }) => {
    let accessory = 0;
    if (slot === 2) { accessories += 1; accessory = accessories; }
    return { slot, accessory, gear, item };
  });
}

/** One shared slot label for the cards and for the copied text. */
function slotLabel(entry: EquipmentEntry, t: TFunction): string {
  if (entry.slot === 0) return t("slot.armor");
  if (entry.slot === 1) return t("slot.gauntlet");
  if (entry.slot === 2) return t("slot.accessory", { index: entry.accessory });
  return t("slot.equipment", { index: entry.slot + 1 });
}

function characterDisplayName(character: Character): string {
  return localizedName("characters", character.id, character.name);
}

function weaponDisplayName(weapon: Weapon | undefined, t: TFunction): string {
  return weapon ? localizedName("weapons", weapon.id, weapon.name) : t("solution.unknownWeapon");
}

/** data.sets only holds the four resident four-axis sets; other equipment sets are left unlabelled.
 * Never fall back to the raw suit_* id in the UI or in copied text. */
function equipmentSetName(item: Equipment | undefined): string {
  if (!item?.set) return "";
  return localizedName("sets", item.set, setById.get(item.set)?.name ?? "");
}

/** Unknown non-empty ids may be reported as missing data, but the technical id is never a display name. */
function equipmentDisplayName(gear: GearSelection, item: Equipment | undefined, t: TFunction): string {
  if (!gear.id) return t("slot.unequipped");
  return item ? localizedName("equipment", item.id, item.name) : t("slot.unknownItem");
}

/** evaluate.ts only emits ids present in data.sets; an unexpected id still must not leak as raw text. */
function activeSetLabels(activeSets: unknown): { names: string[]; unknown: number } {
  const names: string[] = [];
  let unknown = 0;
  if (Array.isArray(activeSets)) {
    for (const id of activeSets) {
      if (typeof id !== "string") continue;
      const name = setById.get(id)?.name;
      if (name) names.push(localizedName("sets", id, name)); else unknown += 1;
    }
  }
  return { names, unknown };
}

function attributeName(index: number, t: TFunction): string {
  const key = ATTRIBUTE_KEYS[index];
  return key ? t(`attributes.${key}`) : "";
}

/** The base gem affix uses the weapon's own attribute; -1 means the character's main attribute. */
function gemAttributeName(weapon: Weapon | undefined, character: Character, t: TFunction): string {
  if (!weapon) return "";
  const axis = weapon.attribute === -1 ? character.main : weapon.attribute;
  return attributeName(axis, t);
}

function modifierLabel(modifier: Modifier, character: Character, t: TFunction): string {
  if (modifier.scope === 1) {
    return t("modifier.main", { attribute: attributeName(character.main, t) || t("attributes.mainFallback") });
  }
  if (modifier.scope === 2) {
    return t("modifier.sub", { attribute: attributeName(character.sub, t) || t("attributes.subFallback") });
  }
  if (modifier.scope === 3) return t("modifier.all");
  return attributeName(modifier.attribute, t) || t("modifier.unknown", { index: formatCount(modifier.attribute) });
}

/** Frozen contract: search.ts emits one refinement per equipment.modifiers element in array order.
 * Modifier.index is the source affix id, never an array index, so refinements are read by position only. */
function modifierRefinement(gear: GearSelection, slot: number): number {
  const list: unknown = gear.refinements;
  if (!Array.isArray(list)) return 0;
  const value: unknown = list[slot];
  return typeof value === "number" && Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0;
}

function modifierValue(modifier: Modifier, refinement: number): string {
  const values: unknown = modifier.values;
  if (!Array.isArray(values)) return "—";
  const value: unknown = values[refinement];
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return modifier.stage === "percent" ? `${formatValue(value * 100)}%` : formatValue(value);
}

function isSolution(value: unknown): value is Solution {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<Solution>;
  return Boolean(candidate.build) && Boolean(candidate.evaluation) &&
    Array.isArray(candidate.build?.equipment) && Array.isArray(candidate.evaluation?.display) &&
    Array.isArray(candidate.evaluation?.matched);
}

/** Worker output is untrusted input too: normalize it so a malformed message cannot crash the page. */
function normalizeResult(value: unknown): { result: SearchResult | null; dropped: boolean } {
  if (!value || typeof value !== "object") return { result: null, dropped: false };
  const raw = value as Partial<SearchResult>;
  if (!Array.isArray(raw.results)) return { result: null, dropped: false };
  const results = raw.results.filter(isSolution);
  return {
    result: {
      results,
      elapsedMs: typeof raw.elapsedMs === "number" ? raw.elapsedMs : Number.NaN,
      candidates: typeof raw.candidates === "number" && Number.isFinite(raw.candidates) ? raw.candidates : 0,
      complete: raw.complete === true,
      notes: Array.isArray(raw.notes) ? raw.notes.filter((note): note is string => typeof note === "string") : [],
    },
    dropped: results.length < raw.results.length,
  };
}

/** Browser/worker exceptions stay raw; the display bridge localizes or falls back. */
function describeError(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "";
}

async function writeClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to the legacy path; both may fail in insecure contexts.
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(area);
    return copied;
  } catch {
    return false;
  }
}

/** Built at click time so the copied text always uses the language selected then. */
function solutionCopyText(solution: Solution, index: number, character: Character, t: TFunction): string {
  const { build, evaluation } = solution;
  const lines: string[] = [];
  lines.push(t("copy.title", { index: index + 1, name: characterDisplayName(character) }));
  lines.push(t("copy.level", { level: formatCount(build.level), potential: formatCount(build.potential) }));
  lines.push(t("copy.panel", { values: ATTRIBUTE_NAMES.map((_, position) =>
    `${attributeName(position, t)} ${formatValue(readVector(evaluation.display, position))}`).join(" / ") }));
  const matched = matchedSet(evaluation);
  lines.push(t("copy.matched", { target: TARGET, count: matched.size, list: matched.size > 0
    ? t("copy.matchedList", { names: [...matched].map((position) => attributeName(position, t)).join(t("listSeparator")) })
    : "" }));
  const { names: setNames, unknown: unknownSets } = activeSetLabels(evaluation.activeSets);
  if (setNames.length > 0 || unknownSets > 0) {
    const parts = [...setNames];
    if (unknownSets > 0) parts.push(t("copy.unknownSets", { count: unknownSets }));
    lines.push(t("copy.sets", { names: parts.join(t("listSeparator")) }));
  }
  lines.push("");
  const weapon = weaponById.get(build.weapon?.id ?? "");
  const gemAttribute = gemAttributeName(weapon, character, t);
  lines.push(t("copy.weapon", {
    name: weaponDisplayName(weapon, t),
    suffix: weapon ? t("copy.weaponMax", { level: formatCount(weapon.level) }) : t("copy.weaponMissing"),
  }));
  lines.push(t("copy.gem", {
    refinement: formatCount(build.weapon?.refinement),
    attribute: gemAttribute ? t("copy.gemAttribute", { attribute: gemAttribute }) : "",
    gemFirst: formatCount(build.weapon?.gemFirst),
    gemPassive: formatCount(build.weapon?.gemPassive),
  }));
  lines.push(t("copy.gemNote"));
  lines.push("");
  lines.push(t("copy.gearHeading"));
  for (const entry of orderEquipment(build.equipment)) {
    const label = slotLabel(entry, t);
    if (!entry.gear.id) {
      lines.push(t("copy.gearUnequipped", { label }));
      continue;
    }
    const setName = equipmentSetName(entry.item);
    lines.push(t("copy.gearLine", {
      label,
      name: equipmentDisplayName(entry.gear, entry.item, t),
      set: setName ? t("copy.gearSet", { name: setName }) : "",
    }));
    if (!entry.item) {
      lines.push(t("copy.gearMissing"));
      continue;
    }
    for (const [modifierPosition, modifier] of entry.item.modifiers.entries()) {
      const refinement = modifierRefinement(entry.gear, modifierPosition);
      lines.push(t("copy.modLine", {
        refinement,
        label: modifierLabel(modifier, character, t),
        value: modifierValue(modifier, refinement),
      }));
    }
  }
  lines.push("");
  lines.push(t("copy.source", { source: gameData.source, version: gameData.version, date: gameData.sourceUpdatedAt }));
  return lines.join("\n");
}

function AttributeGrid({ evaluation }: { evaluation: Evaluation }) {
  const { t } = useAppTranslation("calculator");
  const matched = matchedSet(evaluation);
  return <div className="calc-attributes">
    {ATTRIBUTE_NAMES.map((name, index) => {
      const value = readVector(evaluation.display, index);
      const reached = matched.has(index);
      const gap = value === null ? null : TARGET - value;
      const state = reached ? t("attributeState.reached", { target: TARGET })
        : gap === null ? t("attributeState.missing")
          : gap > 0 ? t("attributeState.gap", { gap: formatValue(gap) })
            : t("attributeState.above", { target: TARGET });
      return <div className={`calc-attribute${reached ? " matched" : ""}`} key={name}>
        <span className="calc-attribute-name">{attributeName(index, t)}</span>
        <strong>{formatValue(value)}</strong>
        <span className="calc-attribute-state">{state}</span>
      </div>;
    })}
  </div>;
}

function SolutionCard({ solution, index, character, copyNotice, onCopy }: {
  solution: Solution;
  index: number;
  character: Character;
  copyNotice: CopyNotice;
  onCopy: () => void;
}) {
  const { t } = useAppTranslation("calculator");
  const { render } = useMessages();
  const { build, evaluation } = solution;
  const matched = matchedSet(evaluation);
  const { names: setNames, unknown: unknownSets } = activeSetLabels(evaluation.activeSets);
  const weapon = weaponById.get(build.weapon?.id ?? "");
  const gemAttribute = gemAttributeName(weapon, character, t);
  const entries = orderEquipment(Array.isArray(build.equipment) ? build.equipment : []);
  const notice = copyNotice && copyNotice.solutionIndex === index ? copyNotice : null;
  return <article className="calc-solution" aria-labelledby={`calc-solution-${index}`}>
    <header className="calc-solution-head">
      <div className="calc-solution-title calc-entity-row">
        <EntityIcon kind="characters" id={character.id} name={characterDisplayName(character)} size={56} />
        <div className="calc-entity-text">
          <h3 id={`calc-solution-${index}`}>{t("solution.title", { index: index + 1, name: characterDisplayName(character) })}</h3>
          <p className="calc-solution-meta">
            {t("solution.meta", { level: formatCount(build.level), potential: formatCount(build.potential) })}
          </p>
        </div>
      </div>
      <span className={`calc-match-badge${matched.size > 0 ? " reached" : ""}`}>
        {t("solution.badge", { count: matched.size })}
      </span>
    </header>
    <AttributeGrid evaluation={evaluation} />
    {(setNames.length > 0 || unknownSets > 0) && <p className="calc-sets">{t("solution.sets")}{setNames.map((name, position) =>
      <span key={`${name}-${position}`}>{name}</span>)}
      {unknownSets > 0 && <span>{t("solution.unknownSets", { count: unknownSets })}</span>}</p>}
    <div className="calc-gear">
      <section className="calc-gear-block" aria-label={t("solution.weaponSection")}>
        <h4>{t("solution.weaponSection")}</h4>
        <div className="calc-weapon-row calc-entity-row">
          <EntityIcon kind="weapons" id={build.weapon?.id ?? ""} name={weaponDisplayName(weapon, t)} />
          <div className="calc-entity-text">
            <p className="calc-weapon-name">
              <strong>{weaponDisplayName(weapon, t)}</strong>
              {weapon && <span className="muted small">{t("solution.weaponLevel", { level: formatCount(weapon.level) })}</span>}
              {!weapon && <span className="calc-missing">{t("solution.weaponMissing")}</span>}
            </p>
          </div>
        </div>
        <ul className="calc-tags">
          <li>{t("solution.refine", { value: formatCount(build.weapon?.refinement) })}</li>
          <li>{t("solution.gemFirst", { attribute: gemAttribute ? t("copy.gemAttribute", { attribute: gemAttribute }) : "",
            value: formatCount(build.weapon?.gemFirst) })}</li>
          <li>{t("solution.gemPassive", { value: formatCount(build.weapon?.gemPassive) })}</li>
        </ul>
        <p className="muted small calc-gem-note">{t("solution.gemNote")}</p>
      </section>
      <section className="calc-gear-block" aria-label={t("solution.gearSection")}>
        <h4>{t("solution.gearSection")}</h4>
        <div className="calc-equip-list">
          {entries.map((entry, position) => {
            const setName = equipmentSetName(entry.item);
            return <div className="calc-equip" key={`${entry.gear.id}-${position}`}>
              <div className="calc-entity-row">
                {entry.gear.id && <EntityIcon kind="equipment" id={entry.gear.id}
                  name={equipmentDisplayName(entry.gear, entry.item, t)} />}
                <div className="calc-entity-text">
                  <p className="calc-equip-head">
                    <span className="calc-slot">{slotLabel(entry, t)}</span>
                    <strong>{equipmentDisplayName(entry.gear, entry.item, t)}</strong>
                    {entry.gear.id && setName && <span className="muted small">{t("solution.set", { name: setName })}</span>}
                    {entry.gear.id && !entry.item && <span className="calc-missing">{t("solution.gearMissing")}</span>}
                  </p>
                </div>
              </div>
              {entry.gear.id && (entry.item
                ? <ul className="calc-mod-list">{entry.item.modifiers.map((modifier, modifierPosition) => {
                  const refinement = modifierRefinement(entry.gear, modifierPosition);
                  return <li className="calc-mod" key={`${modifier.index}-${modifier.scope}-${modifier.attribute}-${modifierPosition}`}>
                    <span>{t("solution.modifier", { refinement, label: modifierLabel(modifier, character, t) })}</span>
                    <b>{modifierValue(modifier, refinement)}</b>
                  </li>;
                })}</ul>
                : <p className="muted small">{t("solution.modsUnavailable")}</p>)}
            </div>;
          })}
        </div>
      </section>
    </div>
    <div className="row-actions">
      <button type="button" className="button quiet" onClick={onCopy}>{t("solution.copy")}</button>
      {notice && <span className={notice.ok ? "calc-copy-ok" : "error-text"} role="status" aria-live="polite">
        {render(notice.message, "error")}
      </span>}
    </div>
  </article>;
}

export default function CalculatorPage() {
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
      worker = new Worker(new URL("./calculator/search.worker.ts", import.meta.url), { type: "module" });
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

  if (!character) {
    return <div className="notice warning" role="alert">{t("noData")}</div>;
  }

  const notes = result?.notes ?? [];
  return <>
    <div className="intro">
      <span className="eyebrow">{t("eyebrow")}</span>
      <h1>{t("heading")}</h1>
      <p>{t("intro", { target: TARGET })}</p>
    </div>
    <div className="calc-workbench">
      <section className="panel calc-form-panel" aria-labelledby="calc-form-title">
        <h2 id="calc-form-title">{t("form.heading")}</h2>
        <form className="calc-form" onSubmit={(event) => { event.preventDefault(); startSearch(); }}>
          <div className="calc-field">
            <label htmlFor="calc-character">{t("form.character")}</label>
            <div className="calc-character-selection">
              <EntityIcon kind="characters" id={character.id} name={characterDisplayName(character)} eager />
              <select id="calc-character" value={character.id} onChange={(event) => changeCharacter(event.target.value)}>
                {gameData.characters.map((item) => <option key={item.id} value={item.id}>
                  {localizedName("characters", item.id, item.name)}</option>)}
              </select>
            </div>
          </div>
          <div className="calc-form-grid">
            <div className="calc-field">
              <label htmlFor="calc-level">{t("form.level", { max: maxLevel })}</label>
              <input id="calc-level" type="number" inputMode="numeric" min={1} max={maxLevel} step={1}
                value={levelText} onChange={(event) => changeLevel(event.target.value)} onBlur={normalizeLevel} />
              {!levelValid && <span className="error-text small">{t("form.levelInvalid", { max: maxLevel })}</span>}
            </div>
            <div className="calc-field">
              <label htmlFor="calc-potential">{t("form.potential")}</label>
              <select id="calc-potential" value={String(potential)} onChange={(event) => changePotential(event.target.value)}>
                {POTENTIAL_CHOICES.map((choice) => <option key={String(choice)} value={String(choice)}>
                  {choice === "any" ? t("form.potentialAny") : t("form.potentialValue", { value: choice })}
                </option>)}
              </select>
            </div>
          </div>
          <div className="calc-target-row">
            <span className="field-label">{t("form.targetLabel")}</span>
            <strong className="calc-target">{TARGET}</strong>
            <span className="muted small">{t("form.targetFixed")}</span>
          </div>
          <fieldset className="calc-required">
            <legend>{t("form.requiredLegend", { target: TARGET })}</legend>
            <p className="muted small">{t("form.requiredHelp", { target: TARGET })}</p>
            <div className="calc-required-grid">
              {ATTRIBUTE_NAMES.map((name, index) => <label className="calc-check" key={name} htmlFor={`calc-required-${index}`}>
                <input id={`calc-required-${index}`} type="checkbox" checked={required.includes(index)}
                  onChange={() => toggleRequired(index)} />
                <span>{attributeName(index, t)}</span>
              </label>)}
            </div>
          </fieldset>
          <details className="calc-advanced">
            <summary>{t("form.advanced")}</summary>
            <p className="muted small">{t("form.advancedHelp")}</p>
            <div className="calc-form-grid">
              <div className="calc-field">
                <label htmlFor="calc-gear-refine">{t("form.maxGearRefine")}</label>
                <select id="calc-gear-refine" value={String(limits.maxGearRefine)}
                  onChange={(event) => changeLimit("maxGearRefine", event.target.value)}>
                  {REFINE_CHOICES(3).map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </div>
              <div className="calc-field">
                <label htmlFor="calc-weapon-refine">{t("form.maxWeaponRefine")}</label>
                <select id="calc-weapon-refine" value={String(limits.maxWeaponRefine)}
                  onChange={(event) => changeLimit("maxWeaponRefine", event.target.value)}>
                  {REFINE_CHOICES(5).map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </div>
              <div className="calc-field">
                <label htmlFor="calc-gem-first">{t("form.maxGemFirst")}</label>
                <select id="calc-gem-first" value={String(limits.maxGemFirst)}
                  onChange={(event) => changeLimit("maxGemFirst", event.target.value)}>
                  {REFINE_CHOICES(6).map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </div>
              <div className="calc-field">
                <label htmlFor="calc-gem-passive">{t("form.maxGemPassive")}</label>
                <select id="calc-gem-passive" value={String(limits.maxGemPassive)}
                  onChange={(event) => changeLimit("maxGemPassive", event.target.value)}>
                  {REFINE_CHOICES(3).map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </div>
            </div>
          </details>
          <div className="row-actions">
            <button type="submit" className="button primary" disabled={running || !levelValid}>
              {running ? t("form.searching") : t("form.start")}
            </button>
            {running && <button type="button" className="button secondary" onClick={cancelSearch}>{t("form.cancel")}</button>}
          </div>
        </form>
      </section>
      <div className="calc-output">
        {running && <section className="panel calc-progress" role="status" aria-live="polite">
          <span className="calc-spinner" aria-hidden="true" />
          <p>{t("progress.searching", { phase: phase ? tm(phase) : t("progress.preparing") })}</p>
          <button type="button" className="button secondary" onClick={cancelSearch}>{t("form.cancel")}</button>
        </section>}
        {!running && error && <section className="panel calc-error" role="alert">
          <h2>{t("error.title")}</h2>
          <p className="error-text">{render(error, "error")}</p>
          <div className="row-actions">
            <button type="button" className="button primary" disabled={!levelValid} onClick={startSearch}>{t("error.retry")}</button>
          </div>
        </section>}
        {!running && !error && statusNote && <p className="notice" role="status" aria-live="polite">{render(statusNote)}</p>}
        {!running && !error && !result && <section className="panel calc-empty">
          <h2>{t("results.heading")}</h2>
          <p className="muted">{t("results.emptyHint")}</p>
          <ul className="calc-notes">
            <li>{t("results.emptyNote1", { target: TARGET })}</li>
            <li>{t("results.emptyNote2")}</li>
            <li>{t("results.emptyNote3")}</li>
          </ul>
        </section>}
        {!running && result && <section className="panel calc-results" aria-label={t("results.panelLabel")}>
          <div className="calc-result-head">
            <h2>{t("results.heading")}</h2>
            <div className="summary">
              <span>{t("results.elapsed", { duration: formatDuration(result.elapsedMs, t) })}</span>
              <span>{t("results.evaluated", { count: formatCount(result.candidates, "0") })}</span>
              <span>{t(result.complete ? "results.complete" : "results.limited")}</span>
              <span>{t("results.solutionCount", { count: result.results.length, limit: DEFAULT_REQUEST.limit })}</span>
            </div>
          </div>
          {!result.complete && <div className="notice warning">
            <p>{t("results.timeoutNotice")}</p>
            {result.results.length === 0 && <p>{t("results.timeoutEmpty")}</p>}
          </div>}
          {result.complete && result.results.length === 0 && <div className="notice">
            {t("results.completeEmpty", { target: TARGET })}
          </div>}
          {result.complete && result.results.length > 0 &&
            <p className="muted small">{t("results.completeSorted", { target: TARGET })}</p>}
          {notes.length > 0 && <ul className="calc-notes">{notes.map((note, index) =>
            <li key={`${index}-${note}`}>{tm(note)}</li>)}</ul>}
          <div className="calc-solution-list">
            {result.results.map((solution, index) => <SolutionCard key={index} solution={solution} index={index}
              character={character} copyNotice={copyNotice} onCopy={() => void copySolution(index, solution)} />)}
          </div>
        </section>}
      </div>
    </div>
    <section className="panel calc-about" aria-labelledby="calc-about-title">
      <h2 id="calc-about-title">{t("about.title")}</h2>
      <ul className="calc-notes">
        <li>{t("about.note1")}</li>
        <li>{t("about.note2")}</li>
        <li>{t("about.note3")}</li>
        <li>{t("about.note4")}</li>
        <li>{t("about.note5")}</li>
      </ul>
      <p className="muted small calc-source">{t("about.sourcePrefix")}<a href={gameData.source} target="_blank" rel="noopener noreferrer">{gameData.source}</a>
        {" · "}{t("about.version", { version: gameData.version })}{" · "}{t("about.updated", { date: gameData.sourceUpdatedAt })}</p>
      <p className="muted small calc-source">{t("about.iconSourcePrefix")}<a href="https://www.akedata.wiki/" target="_blank" rel="noopener noreferrer">{t("about.wiki")}</a>{t("about.iconSourceSuffix")}</p>
      <p className="muted small">{t("about.disclaimer")}</p>
      <p className="calc-other-tools">{t("about.otherTools")}<Link to={localizePath("/balloon", locale)}>{t("about.balloonLink")}</Link><Link to={localizePath("/circuit", locale)}>{t("about.circuitLink")}</Link></p>
    </section>
  </>;
}
