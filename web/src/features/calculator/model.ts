/**
 * Display helpers of the 325 calculator page, moved unchanged out of
 * CalculatorPage.tsx: lookups, formatting, equipment ordering, labels,
 * result normalization, clipboard and the copied text. No search logic.
 */
import type { TFunction } from "i18next";
import { gameData } from "../../calculator/data.ts";
import { localizedName, type MessageText } from "../../i18n";
import {
  ATTRIBUTE_NAMES,
  DEFAULT_REQUEST,
  type Character,
  type Equipment,
  type Evaluation,
  type GearSelection,
  type Modifier,
  type SearchResult,
  type Solution,
  type Weapon,
} from "../../calculator/types.ts";

export const TARGET = DEFAULT_REQUEST.target;
export const POTENTIAL_CHOICES: (number | "any")[] = [0, 1, 2, 3, 4, 5, "any"];
export const REFINE_CHOICES = (max: number) => Array.from({ length: max + 1 }, (_, value) => value);
/** Display order of the four stats; the domain keeps ATTRIBUTE_NAMES untouched. */
export const ATTRIBUTE_KEYS = ["strength", "agility", "intellect", "will"] as const;

export const characterById = new Map(gameData.characters.map((item) => [item.id, item]));
export const weaponById = new Map(gameData.weapons.map((item) => [item.id, item]));
const equipmentById = new Map(gameData.equipment.map((item) => [item.id, item]));
const setById = new Map(gameData.sets.map((item) => [item.id, item]));
export const DEFAULT_CHARACTER: Character | undefined =
  characterById.get(DEFAULT_REQUEST.characterId) ??
  (gameData.characters.length > 0 ? gameData.characters[0] : undefined);

export type AdvancedLimits = {
  maxGearRefine: number;
  maxWeaponRefine: number;
  maxGemFirst: number;
  maxGemPassive: number;
};
export type CopyNotice = { solutionIndex: number; ok: boolean; message: MessageText } | null;
export type EquipmentEntry = { slot: number; accessory: number; gear: GearSelection; item: Equipment | undefined };

export function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

export function formatValue(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

export function formatCount(value: unknown, fallback = "?"): string {
  return typeof value === "number" && Number.isFinite(value) ? String(Math.trunc(value)) : fallback;
}

export function formatDuration(milliseconds: unknown, t: TFunction): string {
  if (typeof milliseconds !== "number" || !Number.isFinite(milliseconds) || milliseconds < 0) return "—";
  if (milliseconds < 1000) return t("duration.milliseconds", { value: Math.round(milliseconds) });
  return t("duration.seconds", { value: (milliseconds / 1000).toFixed(1) });
}

export function readVector(vector: unknown, index: number): number | null {
  if (!Array.isArray(vector)) return null;
  const value: unknown = vector[index];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function matchedSet(evaluation: Evaluation): Set<number> {
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
export function orderEquipment(equipment: GearSelection[]): EquipmentEntry[] {
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
export function slotLabel(entry: EquipmentEntry, t: TFunction): string {
  if (entry.slot === 0) return t("slot.armor");
  if (entry.slot === 1) return t("slot.gauntlet");
  if (entry.slot === 2) return t("slot.accessory", { index: entry.accessory });
  return t("slot.equipment", { index: entry.slot + 1 });
}

export function characterDisplayName(character: Character): string {
  return localizedName("characters", character.id, character.name);
}

export function weaponDisplayName(weapon: Weapon | undefined, t: TFunction): string {
  return weapon ? localizedName("weapons", weapon.id, weapon.name) : t("solution.unknownWeapon");
}

/** data.sets only holds the four resident four-axis sets; other equipment sets are left unlabelled.
 * Never fall back to the raw suit_* id in the UI or in copied text. */
export function equipmentSetName(item: Equipment | undefined): string {
  if (!item?.set) return "";
  return localizedName("sets", item.set, setById.get(item.set)?.name ?? "");
}

/** Unknown non-empty ids may be reported as missing data, but the technical id is never a display name. */
export function equipmentDisplayName(gear: GearSelection, item: Equipment | undefined, t: TFunction): string {
  if (!gear.id) return t("slot.unequipped");
  return item ? localizedName("equipment", item.id, item.name) : t("slot.unknownItem");
}

/** evaluate.ts only emits ids present in data.sets; an unexpected id still must not leak as raw text. */
export function activeSetLabels(activeSets: unknown): { names: string[]; unknown: number } {
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

export function attributeName(index: number, t: TFunction): string {
  const key = ATTRIBUTE_KEYS[index];
  return key ? t(`attributes.${key}`) : "";
}

/** The base gem affix uses the weapon's own attribute; -1 means the character's main attribute. */
export function gemAttributeName(weapon: Weapon | undefined, character: Character, t: TFunction): string {
  if (!weapon) return "";
  const axis = weapon.attribute === -1 ? character.main : weapon.attribute;
  return attributeName(axis, t);
}

export function modifierLabel(modifier: Modifier, character: Character, t: TFunction): string {
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
export function modifierRefinement(gear: GearSelection, slot: number): number {
  const list: unknown = gear.refinements;
  if (!Array.isArray(list)) return 0;
  const value: unknown = list[slot];
  return typeof value === "number" && Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0;
}

export function modifierValue(modifier: Modifier, refinement: number): string {
  const values: unknown = modifier.values;
  if (!Array.isArray(values)) return "—";
  const value: unknown = values[refinement];
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return modifier.stage === "percent" ? `${formatValue(value * 100)}%` : formatValue(value);
}

export function isSolution(value: unknown): value is Solution {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<Solution>;
  return Boolean(candidate.build) && Boolean(candidate.evaluation) &&
    Array.isArray(candidate.build?.equipment) && Array.isArray(candidate.evaluation?.display) &&
    Array.isArray(candidate.evaluation?.matched);
}

/** Worker output is untrusted input too: normalize it so a malformed message cannot crash the page. */
export function normalizeResult(value: unknown): { result: SearchResult | null; dropped: boolean } {
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
export function describeError(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "";
}

export async function writeClipboard(text: string): Promise<boolean> {
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
export function solutionCopyText(solution: Solution, index: number, character: Character, t: TFunction): string {
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
