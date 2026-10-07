import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { gameData } from "./calculator/data.ts";
import EntityIcon from "./calculator/EntityIcon.tsx";
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
type CopyNotice = { solutionIndex: number; ok: boolean; message: string } | null;
type EquipmentEntry = { label: string; gear: GearSelection; item: Equipment | undefined };

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

function formatDuration(milliseconds: unknown): string {
  if (typeof milliseconds !== "number" || !Number.isFinite(milliseconds) || milliseconds < 0) return "—";
  if (milliseconds < 1000) return `${Math.round(milliseconds)} 毫秒`;
  return `${(milliseconds / 1000).toFixed(1)} 秒`;
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
    let label = `装备${slot + 1}`;
    if (slot === 0) label = "护甲";
    else if (slot === 1) label = "护手";
    else if (slot === 2) { accessories += 1; label = `配件${accessories}`; }
    return { label, gear, item };
  });
}

/** data.sets only holds the four resident four-axis sets; other equipment sets are left unlabelled.
 * Never fall back to the raw suit_* id in the UI or in copied text. */
function equipmentSetName(item: Equipment | undefined): string {
  if (!item?.set) return "";
  return setById.get(item.set)?.name ?? "";
}

/** Unknown non-empty ids may be reported as missing data, but the technical id is never a display name. */
function equipmentDisplayName(gear: GearSelection, item: Equipment | undefined): string {
  if (!gear.id) return "未装备";
  return item?.name ?? "未知装备";
}

/** evaluate.ts only emits ids present in data.sets; an unexpected id still must not leak as raw text. */
function activeSetLabels(activeSets: unknown): { names: string[]; unknown: number } {
  const names: string[] = [];
  let unknown = 0;
  if (Array.isArray(activeSets)) {
    for (const id of activeSets) {
      if (typeof id !== "string") continue;
      const name = setById.get(id)?.name;
      if (name) names.push(name); else unknown += 1;
    }
  }
  return { names, unknown };
}

/** The base gem affix uses the weapon's own attribute; -1 means the character's main attribute. */
function gemAttributeName(weapon: Weapon | undefined, character: Character): string {
  if (!weapon) return "";
  const axis = weapon.attribute === -1 ? character.main : weapon.attribute;
  return ATTRIBUTE_NAMES[axis] ?? "";
}

function modifierLabel(modifier: Modifier, character: Character): string {
  if (modifier.scope === 1) return `${ATTRIBUTE_NAMES[character.main] ?? "主属性"}（主能力）`;
  if (modifier.scope === 2) return `${ATTRIBUTE_NAMES[character.sub] ?? "副属性"}（副能力）`;
  if (modifier.scope === 3) return "全属性";
  return ATTRIBUTE_NAMES[modifier.attribute] ?? `属性 ${formatCount(modifier.attribute)}`;
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

function describeError(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "未知错误";
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

function solutionCopyText(solution: Solution, index: number, character: Character): string {
  const { build, evaluation } = solution;
  const lines: string[] = [];
  lines.push(`325 挑战方案 ${index + 1} · ${character.name}`);
  lines.push(`等级 Lv.${formatCount(build.level)} · 潜能 ${formatCount(build.potential)}`);
  lines.push(`面板：${ATTRIBUTE_NAMES.map((name, position) =>
    `${name} ${formatValue(readVector(evaluation.display, position))}`).join(" / ")}`);
  const matched = matchedSet(evaluation);
  lines.push(`同时达到 ${TARGET}：${matched.size} 项${matched.size > 0
    ? `（${[...matched].map((position) => ATTRIBUTE_NAMES[position]).join("、")}）` : ""}`);
  const { names: setNames, unknown: unknownSets } = activeSetLabels(evaluation.activeSets);
  if (setNames.length > 0 || unknownSets > 0) {
    const parts = [...setNames];
    if (unknownSets > 0) parts.push(`另有 ${unknownSets} 项未收录套装`);
    lines.push(`激活套装：${parts.join("、")}`);
  }
  lines.push("");
  const weapon = weaponById.get(build.weapon?.id ?? "");
  const gemAttribute = gemAttributeName(weapon, character);
  lines.push(`武器：${weapon?.name ?? "未知武器"}${weapon
    ? `（满级 Lv.${formatCount(weapon.level)}）` : "（本地数据中未找到）"}`);
  lines.push(`精炼 +${formatCount(build.weapon?.refinement)}` +
    ` · 基质基础词条${gemAttribute ? `（${gemAttribute}）` : ""} +${formatCount(build.weapon?.gemFirst)}` +
    ` · 基质技能词条 +${formatCount(build.weapon?.gemPassive)}`);
  lines.push("基质数字为最低词条增级需求，第二词条不限；+0表示无需该项增级。");
  lines.push("");
  lines.push("装备：");
  for (const { label, gear, item } of orderEquipment(build.equipment)) {
    if (!gear.id) {
      lines.push(`  ${label}：未装备`);
      continue;
    }
    const setName = equipmentSetName(item);
    lines.push(`  ${label}：${equipmentDisplayName(gear, item)}${setName ? `（套装：${setName}）` : ""}`);
    if (!item) {
      lines.push("    （本地数据中未找到该装备，无法列出锤炼词条）");
      continue;
    }
    for (const [modifierPosition, modifier] of item.modifiers.entries()) {
      const refinement = modifierRefinement(gear, modifierPosition);
      lines.push(`    锤炼 +${refinement} → ${modifierLabel(modifier, character)} ${modifierValue(modifier, refinement)}`);
    }
  }
  lines.push("");
  lines.push(`数据来源：${gameData.source} · 版本 ${gameData.version} · 数据更新 ${gameData.sourceUpdatedAt}`);
  return lines.join("\n");
}

function AttributeGrid({ evaluation }: { evaluation: Evaluation }) {
  const matched = matchedSet(evaluation);
  return <div className="calc-attributes">
    {ATTRIBUTE_NAMES.map((name, index) => {
      const value = readVector(evaluation.display, index);
      const reached = matched.has(index);
      const gap = value === null ? null : TARGET - value;
      const state = reached ? `达到 ${TARGET}` : gap === null ? "数值缺失"
        : gap > 0 ? `还差 ${formatValue(gap)}` : `高于 ${TARGET}`;
      return <div className={`calc-attribute${reached ? " matched" : ""}`} key={name}>
        <span className="calc-attribute-name">{name}</span>
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
  const { build, evaluation } = solution;
  const matched = matchedSet(evaluation);
  const { names: setNames, unknown: unknownSets } = activeSetLabels(evaluation.activeSets);
  const weapon = weaponById.get(build.weapon?.id ?? "");
  const gemAttribute = gemAttributeName(weapon, character);
  const entries = orderEquipment(Array.isArray(build.equipment) ? build.equipment : []);
  const notice = copyNotice && copyNotice.solutionIndex === index ? copyNotice : null;
  return <article className="calc-solution" aria-labelledby={`calc-solution-${index}`}>
    <header className="calc-solution-head">
      <div className="calc-solution-title calc-entity-row">
        <EntityIcon kind="characters" id={character.id} name={character.name} size={56} />
        <div className="calc-entity-text">
          <h3 id={`calc-solution-${index}`}>方案 {index + 1} · {character.name}</h3>
          <p className="calc-solution-meta">
            等级 Lv.{formatCount(build.level)} · 潜能 {formatCount(build.potential)}
          </p>
        </div>
      </div>
      <span className={`calc-match-badge${matched.size > 0 ? " reached" : ""}`}>
        同时达标 {matched.size} 项
      </span>
    </header>
    <AttributeGrid evaluation={evaluation} />
    {(setNames.length > 0 || unknownSets > 0) && <p className="calc-sets">激活套装：{setNames.map((name, position) =>
      <span key={`${name}-${position}`}>{name}</span>)}
      {unknownSets > 0 && <span>另有 {unknownSets} 项未收录套装</span>}</p>}
    <div className="calc-gear">
      <section className="calc-gear-block" aria-label="武器与基质">
        <h4>武器与基质</h4>
        <div className="calc-weapon-row calc-entity-row">
          <EntityIcon kind="weapons" id={build.weapon?.id ?? ""} name={weapon?.name ?? "未知武器"} />
          <div className="calc-entity-text">
            <p className="calc-weapon-name">
              <strong>{weapon?.name ?? "未知武器"}</strong>
              {weapon && <span className="muted small">满级 Lv.{formatCount(weapon.level)}</span>}
              {!weapon && <span className="calc-missing">本地数据中未找到该武器</span>}
            </p>
          </div>
        </div>
        <ul className="calc-tags">
          <li>精炼 +{formatCount(build.weapon?.refinement)}</li>
          <li>基质基础词条{gemAttribute ? `（${gemAttribute}）` : ""} +{formatCount(build.weapon?.gemFirst)}</li>
          <li>基质技能词条 +{formatCount(build.weapon?.gemPassive)}</li>
        </ul>
        <p className="muted small calc-gem-note">基质数字为最低词条增级需求，第二词条不限；+0表示无需该项增级。</p>
      </section>
      <section className="calc-gear-block" aria-label="装备与锤炼">
        <h4>装备与锤炼</h4>
        <div className="calc-equip-list">
          {entries.map(({ label, gear, item }, position) => {
            const setName = equipmentSetName(item);
            return <div className="calc-equip" key={`${gear.id}-${position}`}>
              <div className="calc-entity-row">
                {gear.id && <EntityIcon kind="equipment" id={gear.id} name={equipmentDisplayName(gear, item)} />}
                <div className="calc-entity-text">
                  <p className="calc-equip-head">
                    <span className="calc-slot">{label}</span>
                    <strong>{equipmentDisplayName(gear, item)}</strong>
                    {gear.id && setName && <span className="muted small">套装：{setName}</span>}
                    {gear.id && !item && <span className="calc-missing">本地数据中未找到该装备</span>}
                  </p>
                </div>
              </div>
              {gear.id && (item
                ? <ul className="calc-mod-list">{item.modifiers.map((modifier, modifierPosition) => {
                  const refinement = modifierRefinement(gear, modifierPosition);
                  return <li className="calc-mod" key={`${modifier.index}-${modifier.scope}-${modifier.attribute}-${modifierPosition}`}>
                    <span>锤炼 +{refinement} · {modifierLabel(modifier, character)}</span>
                    <b>{modifierValue(modifier, refinement)}</b>
                  </li>;
                })}</ul>
                : <p className="muted small">无法列出锤炼词条。</p>)}
            </div>;
          })}
        </div>
      </section>
    </div>
    <div className="row-actions">
      <button type="button" className="button quiet" onClick={onCopy}>复制方案</button>
      {notice && <span className={notice.ok ? "calc-copy-ok" : "error-text"} role="status" aria-live="polite">
        {notice.message}
      </span>}
    </div>
  </article>;
}

export default function CalculatorPage() {
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
  const [error, setError] = useState("");
  const [statusNote, setStatusNote] = useState("");
  const [copyNotice, setCopyNotice] = useState<CopyNotice>(null);
  const workerRef = useRef<Worker | null>(null);
  const runRef = useRef(0);
  const busyRef = useRef(false);

  const character = characterById.get(characterId) ?? DEFAULT_CHARACTER;
  const maxLevel = character?.maxLevel ?? DEFAULT_REQUEST.level;
  const parsedLevel = Number(levelText);
  const levelValid = levelText.trim() !== "" && Number.isInteger(parsedLevel) && parsedLevel >= 1 && parsedLevel <= maxLevel;
  const level = levelValid ? parsedLevel : clamp(Number.isFinite(parsedLevel) ? Math.round(parsedLevel) : 1, 1, maxLevel);

  useEffect(() => { document.title = "325 挑战计算器 | 终末地工具台"; }, []);

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

  const failSearch = useCallback((worker: Worker, run: number, message: string) => {
    if (workerRef.current !== worker || runRef.current !== run) return;
    releaseWorker();
    busyRef.current = false;
    setRunning(false);
    setPhase("");
    setError(message || "搜索失败，请重试。");
  }, [releaseWorker]);

  const finishSearch = useCallback((worker: Worker, run: number, payload: unknown) => {
    if (workerRef.current !== worker || runRef.current !== run) return;
    releaseWorker();
    busyRef.current = false;
    setRunning(false);
    setPhase("");
    const { result: normalized, dropped } = normalizeResult(payload);
    if (!normalized || dropped) {
      setError("搜索返回的结果不完整，请重试。");
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
    try {
      if (typeof Worker === "undefined") throw new Error("当前浏览器不支持 Web Worker");
      worker = new Worker(new URL("./calculator/search.worker.ts", import.meta.url), { type: "module" });
    } catch (creationError) {
      setError(`无法启动本地搜索线程：${describeError(creationError)}。请刷新页面或更换浏览器后重试。`);
      return;
    }
    workerRef.current = worker;
    busyRef.current = true;
    setRunning(true);
    setPhase("正在准备搜索…");
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
        failSearch(worker, run, typeof data.message === "string" ? data.message : "");
      }
    };
    worker.onerror = (event: ErrorEvent) => {
      event.preventDefault();
      failSearch(worker, run, event.message
        ? `本地搜索线程出错：${event.message}`
        : "本地搜索线程出错，请重试。");
    };
    worker.onmessageerror = () => failSearch(worker, run, "搜索返回了无法解析的数据，请重试。");
    const message: WorkerRequest = { type: "search", request };
    try {
      worker.postMessage(message);
    } catch (postError) {
      failSearch(worker, run, `无法提交搜索任务：${describeError(postError)}。请重试。`);
    }
  }, [character, failSearch, finishSearch, level, levelValid, limits, potential, required, resetSearch]);

  const cancelSearch = () => {
    if (!busyRef.current) return;
    resetSearch();
    setStatusNote("已取消本次搜索。");
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
    const copied = await writeClipboard(solutionCopyText(solution, index, character));
    setCopyNotice({
      solutionIndex: index,
      ok: copied,
      message: copied ? "已复制方案到剪贴板。" : "复制失败，请手动选择文本，或允许浏览器访问剪贴板后重试。",
    });
  };

  if (!character) {
    return <div className="notice warning" role="alert">本地养成数据没有可用的干员记录，无法使用计算器。</div>;
  }

  const notes = result?.notes ?? [];
  return <>
    <div className="intro">
      <span className="eyebrow">养成计算器 / 325</span>
      <h1>325 挑战计算器</h1>
      <p>寻找干员常驻面板属性达到 {TARGET} 的方案，优先展示多属性 {TARGET}。可以指定必须同时达标的属性。计算在浏览器本地完成。</p>
    </div>
    <div className="calc-workbench">
      <section className="panel calc-form-panel" aria-labelledby="calc-form-title">
        <h2 id="calc-form-title">搜索条件</h2>
        <form className="calc-form" onSubmit={(event) => { event.preventDefault(); startSearch(); }}>
          <div className="calc-field">
            <label htmlFor="calc-character">干员</label>
            <div className="calc-character-selection">
              <EntityIcon kind="characters" id={character.id} name={character.name} eager />
              <select id="calc-character" value={character.id} onChange={(event) => changeCharacter(event.target.value)}>
                {gameData.characters.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </div>
          </div>
          <div className="calc-form-grid">
            <div className="calc-field">
              <label htmlFor="calc-level">等级（1–{maxLevel}）</label>
              <input id="calc-level" type="number" inputMode="numeric" min={1} max={maxLevel} step={1}
                value={levelText} onChange={(event) => changeLevel(event.target.value)} onBlur={normalizeLevel} />
              {!levelValid && <span className="error-text small">请输入 1 到 {maxLevel} 之间的等级。</span>}
            </div>
            <div className="calc-field">
              <label htmlFor="calc-potential">潜能</label>
              <select id="calc-potential" value={String(potential)} onChange={(event) => changePotential(event.target.value)}>
                {POTENTIAL_CHOICES.map((choice) => <option key={String(choice)} value={String(choice)}>
                  {choice === "any" ? "任意潜能（0–5）" : `潜能 ${choice}`}
                </option>)}
              </select>
            </div>
          </div>
          <div className="calc-target-row">
            <span className="field-label">目标属性值</span>
            <strong className="calc-target">{TARGET}</strong>
            <span className="muted small">固定值</span>
          </div>
          <fieldset className="calc-required">
            <legend>必须同时达到 {TARGET} 的属性</legend>
            <p className="muted small">不勾选时任意一项达到 {TARGET} 即可；勾选多项时方案必须同时满足，并按同时达标数量优先排列。</p>
            <div className="calc-required-grid">
              {ATTRIBUTE_NAMES.map((name, index) => <label className="calc-check" key={name} htmlFor={`calc-required-${index}`}>
                <input id={`calc-required-${index}`} type="checkbox" checked={required.includes(index)}
                  onChange={() => toggleRequired(index)} />
                <span>{name}</span>
              </label>)}
            </div>
          </fieldset>
          <details className="calc-advanced">
            <summary>高级选项（搜索上限）</summary>
            <p className="muted small">上限越高，可选的养成组合越多，搜索需要的时间也越长。</p>
            <div className="calc-form-grid">
              <div className="calc-field">
                <label htmlFor="calc-gear-refine">装备锤炼上限</label>
                <select id="calc-gear-refine" value={String(limits.maxGearRefine)}
                  onChange={(event) => changeLimit("maxGearRefine", event.target.value)}>
                  {REFINE_CHOICES(3).map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </div>
              <div className="calc-field">
                <label htmlFor="calc-weapon-refine">武器精炼上限</label>
                <select id="calc-weapon-refine" value={String(limits.maxWeaponRefine)}
                  onChange={(event) => changeLimit("maxWeaponRefine", event.target.value)}>
                  {REFINE_CHOICES(5).map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </div>
              <div className="calc-field">
                <label htmlFor="calc-gem-first">基质基础词条上限</label>
                <select id="calc-gem-first" value={String(limits.maxGemFirst)}
                  onChange={(event) => changeLimit("maxGemFirst", event.target.value)}>
                  {REFINE_CHOICES(6).map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </div>
              <div className="calc-field">
                <label htmlFor="calc-gem-passive">基质技能词条上限</label>
                <select id="calc-gem-passive" value={String(limits.maxGemPassive)}
                  onChange={(event) => changeLimit("maxGemPassive", event.target.value)}>
                  {REFINE_CHOICES(3).map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </div>
            </div>
          </details>
          <div className="row-actions">
            <button type="submit" className="button primary" disabled={running || !levelValid}>
              {running ? "搜索中…" : "开始搜索"}
            </button>
            {running && <button type="button" className="button secondary" onClick={cancelSearch}>取消搜索</button>}
          </div>
        </form>
      </section>
      <div className="calc-output">
        {running && <section className="panel calc-progress" role="status" aria-live="polite">
          <span className="calc-spinner" aria-hidden="true" />
          <p>正在搜索：{phase || "正在计算…"}</p>
          <button type="button" className="button secondary" onClick={cancelSearch}>取消搜索</button>
        </section>}
        {!running && error && <section className="panel calc-error" role="alert">
          <h2>搜索未完成</h2>
          <p className="error-text">{error}</p>
          <div className="row-actions">
            <button type="button" className="button primary" disabled={!levelValid} onClick={startSearch}>重试搜索</button>
          </div>
        </section>}
        {!running && !error && statusNote && <p className="notice" role="status" aria-live="polite">{statusNote}</p>}
        {!running && !error && !result && <section className="panel calc-empty">
          <h2>搜索结果</h2>
          <p className="muted">设置条件后点击“开始搜索”。</p>
          <ul className="calc-notes">
            <li>不勾选属性要求时，任意一项面板属性达到 {TARGET} 即算命中。</li>
            <li>勾选多项时，方案必须同时满足所选属性，结果按同时达标数量优先排列。</li>
            <li>搜索使用本地数据，不会上传干员、等级或装备信息。</li>
          </ul>
        </section>}
        {!running && result && <section className="panel calc-results" aria-label="搜索结果">
          <div className="calc-result-head">
            <h2>搜索结果</h2>
            <div className="summary">
              <span>用时 {formatDuration(result.elapsedMs)}</span>
              <span>已评估 {formatCount(result.candidates, "0")} 个候选</span>
              <span>{result.complete ? "已搜索完当前范围" : "限时搜索"}</span>
              <span>方案 {result.results.length} 个（上限 {DEFAULT_REQUEST.limit}）</span>
            </div>
          </div>
          {!result.complete && <div className="notice warning">
            <p>限时搜索已结束，优先展示已找到的多属性方案，不保证全局最优。</p>
            {result.results.length === 0 &&
              <p>本次限时搜索没有返回方案，这不代表无解；可以调整等级、潜能或高级上限后重试。</p>}
          </div>}
          {result.complete && result.results.length === 0 && <div className="notice">
            当前条件下未找到符合 {TARGET} 的养成方案；搜索已穷尽当前范围内的组合，可以调整等级、潜能或高级上限后重试。
          </div>}
          {result.complete && result.results.length > 0 &&
            <p className="muted small">已搜索完当前范围内的组合，方案按同时达到 {TARGET} 的属性数量优先排列。</p>}
          {notes.length > 0 && <ul className="calc-notes">{notes.map((note, index) =>
            <li key={`${index}-${note}`}>{note}</li>)}</ul>}
          <div className="calc-solution-list">
            {result.results.map((solution, index) => <SolutionCard key={index} solution={solution} index={index}
              character={character} copyNotice={copyNotice} onCopy={() => void copySolution(index, solution)} />)}
          </div>
        </section>}
      </div>
    </div>
    <section className="panel calc-about" aria-labelledby="calc-about-title">
      <h2 id="calc-about-title">计算说明</h2>
      <ul className="calc-notes">
        <li>只计算非战斗常驻面板属性，不包含战斗内触发或限时增益。</li>
        <li>按当前等级下合法的突破与能力节点全满计算，武器按满级计算。</li>
        <li>同类型武器都可以选择；按部位选择可穿戴装备，两件配件可以相同。</li>
        <li>结果会注明武器、两个基质词条、每件装备及其每条锤炼要求。</li>
        <li>基质数字为最低词条增级需求，第二词条不限；+0表示无需该项增级。</li>
      </ul>
      <p className="muted small calc-source">数据来源：<a href={gameData.source} target="_blank" rel="noopener noreferrer">{gameData.source}</a>
        {" · "}版本 {gameData.version}{" · "}数据更新 {gameData.sourceUpdatedAt}</p>
      <p className="muted small calc-source">图标与数据来源为 <a href="https://www.akedata.wiki/" target="_blank" rel="noopener noreferrer">AKEndfield Wiki</a>；点击图标查看资料；游戏素材版权归鹰角及相关权利方，本站为非官方玩家工具。</p>
      <p className="muted small">基于公开数据，可能包含尚未拥有的物品；请在游戏内核对。</p>
      <p className="calc-other-tools">其他工具：<Link to="/balloon">浮空回收解谜</Link><Link to="/circuit">源石电路解谜</Link></p>
    </section>
  </>;
}
