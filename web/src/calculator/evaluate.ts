import type { Build, Character, CharacterState, Evaluation, GameData, Modifier, Vector, Weapon, WeaponSelection } from "./types.ts";

export function zero(): Vector { return [0, 0, 0, 0]; }
export function axes(modifier: Pick<Modifier, "scope" | "attribute">, character: Character): number[] {
  if (modifier.scope === 1) return [character.main];
  if (modifier.scope === 2) return [character.sub];
  if (modifier.scope === 3) return [0, 1, 2, 3];
  if (modifier.attribute >= 0 && modifier.attribute < 4) return [modifier.attribute];
  throw new Error("不支持的能力修饰项");
}
function integer(value: number, min: number, max: number, name: string): void {
  if (!Number.isInteger(value) || value < min || value > max) throw new Error(`${name}超出范围`);
}
export function characterState(data: GameData, state: CharacterState) {
  const character = data.characters.find(c => c.id === state.characterId);
  if (!character) throw new Error("干员不存在");
  integer(state.level, 1, character.maxLevel, "等级");
  integer(state.potential, 0, 5, "潜能");
  const row = character.levels.find(r => r.level === state.level);
  if (!row) throw new Error("缺少此等级的属性数据");
  const flat: Vector = [...row.base];
  const percent = zero();
  const add = (mods: Modifier[]) => {
    for (const mod of mods) for (const axis of axes(mod, character)) {
      (mod.stage === "flat" ? flat : percent)[axis] += mod.values[0];
    }
  };
  for (const node of character.nodes) if (node.breakStage <= row.breakStage) add(node.modifiers);
  const passives = new Map<number, (typeof character.passives)[number]>();
  for (const node of character.passives) if (node.breakStage <= row.breakStage &&
    (passives.get(node.index)?.level ?? -1) < node.level) passives.set(node.index, node);
  for (const node of passives.values()) add(node.modifiers);
  for (const potential of character.potentials) if (potential.level <= state.potential) add(potential.modifiers);
  const tier = Math.max(2, ...character.tiers.filter(t => t.breakStage <= row.breakStage).map(t => t.tier));
  return { character, flat, percent, tier, breakStage: row.breakStage };
}

export function weaponStats(weapon: Weapon, selection: WeaponSelection, character: Character) {
  integer(selection.refinement, 0, 5, "武器精炼");
  integer(selection.gemFirst, 0, 6, "基质基础词条");
  integer(selection.gemPassive, 0, 3, "基质技能词条");
  if (weapon.type !== character.weaponType) throw new Error("武器类型不适配此干员");
  const extras = weapon.refine.find(r => r.talentLv === selection.refinement)?.skillLevelExtraBounds;
  const firstRank = Math.min(weapon.bounds[0].upperBound + (extras?.[0].upperBound ?? 0),
    weapon.bounds[0].lowerBound + (extras?.[0].lowerBound ?? 0) + selection.gemFirst);
  const first = weapon.first.find(r => r.level === firstRank);
  if (!first) throw new Error("缺少武器词条等级");
  const flat = zero(), percent = zero();
  flat[weapon.attribute === -1 ? character.main : weapon.attribute] = first.value;
  if (weapon.passiveScope) {
    const bound = weapon.bounds[2];
    const rank = Math.min(bound.upperBound + (extras?.[2].upperBound ?? 0),
      bound.lowerBound + (extras?.[2].lowerBound ?? 0) + selection.gemPassive);
    const passive = weapon.passive.find(r => r.level === rank);
    if (!passive) throw new Error("缺少武器常驻能力加成等级");
    for (const axis of axes({scope: weapon.passiveScope, attribute: -1}, character)) percent[axis] += passive.value;
  }
  return {flat, percent};
}

/** Independent verification: resolve the original item IDs and affix ranks anew.
 * Search caches/sums are deliberately not accepted by this function. */
export function evaluateBuild(data: GameData, build: Build, target = 325): Evaluation {
  const state = characterState(data, build);
  const weapon = data.weapons.find(w => w.id === build.weapon.id);
  if (!weapon) throw new Error("武器不存在");
  const weaponValues = weaponStats(weapon, build.weapon, state.character);
  const flat: Vector = state.flat.map((v, i) => v + weaponValues.flat[i]) as Vector;
  const percent: Vector = state.percent.map((v, i) => v + weaponValues.percent[i]) as Vector;
  if (build.equipment.length !== 4) throw new Error("必须指定四个装备位置");
  const suitCounts = new Map<string, number>();
  const apply = (mod: Modifier, rank: number) => {
    integer(rank, 0, Math.min(3, mod.values.length - 1), "装备锤炼");
    for (const axis of axes(mod, state.character)) (mod.stage === "flat" ? flat : percent)[axis] += mod.values[rank];
  };
  build.equipment.forEach((selection, slot) => {
    if (!selection.id) {
      if (selection.refinements.length) throw new Error("空装备不能有锤炼");
      return;
    }
    const item = data.equipment.find(e => e.id === selection.id);
    if (!item || item.slot !== [0, 1, 2, 2][slot]) throw new Error("装备位置不匹配");
    if (item.minLevel > build.level || item.tier > state.tier) throw new Error("装备养成阶段尚未解锁");
    if (selection.refinements.length !== item.modifiers.length) throw new Error("装备锤炼项不完整");
    item.modifiers.forEach((m, i) => apply(m, selection.refinements[i]));
    suitCounts.set(item.set, (suitCounts.get(item.set) ?? 0) + 1);
  });
  const activeSets: string[] = [];
  for (const suit of data.sets) if ((suitCounts.get(suit.id) ?? 0) >= suit.pieces) {
    activeSets.push(suit.id);
    for (const mod of suit.modifiers) apply(mod, 0);
  }
  // Retain source precision; round only the final displayed panel, never each affix.
  const raw = flat.map((value, axis) => value * (1 + percent[axis])) as Vector;
  const display = raw.map(value => Math.floor(value)) as Vector;
  return {raw, display, matched: display.flatMap((value, axis) => value === target ? [axis] : []), activeSets};
}
