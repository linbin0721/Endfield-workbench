/**
 * Where each panel value comes from, for display only. It re-reads the build
 * with the calculator's own exported functions and replays evaluateBuild's
 * accumulation order, so the total it reaches can be compared bit for bit
 * with the evaluation's `raw`. An axis whose replay differs (or a build that
 * cannot be replayed) gets no breakdown; nothing here feeds the search.
 */
import { axes, characterState, weaponStats } from "../../calculator/evaluate.ts";
import type { Build, Evaluation, GameData, Modifier, Vector } from "../../calculator/types.ts";

export type SourceKind = "operator" | "weapon" | "gear" | "sets";
export const SOURCE_KINDS: SourceKind[] = ["operator", "weapon", "gear", "sets"];

/** One source's share of one attribute. */
export type SourcePart = { kind: SourceKind; flat: number; percent: number; value: number };

export type AxisBreakdown = {
  /** Sum of the flat values. */
  flat: number;
  /** Sum of the percent bonuses (0.085 = 8.5%). */
  percent: number;
  /** flat × (1 + percent), identical to evaluation.raw for this axis. */
  raw: number;
  /** flat_i + flat × percent_i per source; the parts add up to raw. */
  parts: SourcePart[];
};

const zero = (): Vector => [0, 0, 0, 0];
const EQUIPMENT_SLOTS = [0, 1, 2, 2];

/** Breakdown per axis, or null for an axis whose replay does not reproduce `raw` exactly. */
export function breakdownBuild(data: GameData, build: Build, evaluation: Evaluation): (AxisBreakdown | null)[] {
  const none = [null, null, null, null];
  try {
    const state = characterState(data, build);
    const weapon = data.weapons.find((item) => item.id === build.weapon.id);
    if (!weapon || build.equipment.length !== 4) return none;
    const weaponValues = weaponStats(weapon, build.weapon, state.character);
    const sources: Record<SourceKind, { flat: Vector; percent: Vector }> = {
      operator: { flat: [...state.flat] as Vector, percent: [...state.percent] as Vector },
      weapon: { flat: [...weaponValues.flat] as Vector, percent: [...weaponValues.percent] as Vector },
      gear: { flat: zero(), percent: zero() },
      sets: { flat: zero(), percent: zero() },
    };
    // Same order as evaluateBuild: operator + weapon, then each slot, then sets.
    const flat = state.flat.map((value, axis) => value + weaponValues.flat[axis]) as Vector;
    const percent = state.percent.map((value, axis) => value + weaponValues.percent[axis]) as Vector;
    const apply = (modifier: Modifier, rank: number, kind: SourceKind) => {
      const value = modifier.values[rank];
      if (typeof value !== "number") throw new Error("rank");
      for (const axis of axes(modifier, state.character)) {
        if (modifier.stage === "flat") { flat[axis] += value; sources[kind].flat[axis] += value; }
        else { percent[axis] += value; sources[kind].percent[axis] += value; }
      }
    };
    const suitCounts = new Map<string, number>();
    build.equipment.forEach((selection, slot) => {
      if (!selection.id) return;
      const item = data.equipment.find((entry) => entry.id === selection.id);
      if (!item || item.slot !== EQUIPMENT_SLOTS[slot] || selection.refinements.length !== item.modifiers.length) throw new Error("slot");
      item.modifiers.forEach((modifier, index) => apply(modifier, selection.refinements[index], "gear"));
      suitCounts.set(item.set, (suitCounts.get(item.set) ?? 0) + 1);
    });
    for (const suit of data.sets) if ((suitCounts.get(suit.id) ?? 0) >= suit.pieces) {
      for (const modifier of suit.modifiers) apply(modifier, 0, "sets");
    }
    return flat.map((total, axis) => {
      const raw = total * (1 + percent[axis]);
      if (raw !== evaluation.raw[axis]) return null;
      const parts = SOURCE_KINDS.map((kind) => {
        const part = { flat: sources[kind].flat[axis], percent: sources[kind].percent[axis] };
        return { kind, ...part, value: part.flat + total * part.percent };
      });
      return { flat: total, percent: percent[axis], raw, parts };
    });
  } catch {
    return none;
  }
}
