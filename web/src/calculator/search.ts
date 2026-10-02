import { axes, characterState, evaluateBuild, weaponStats, zero } from "./evaluate.ts";
import type { Character, GameData, GearSelection, SearchRequest, SearchResult, Solution, Vector, WeaponSelection } from "./types.ts";

interface GearVariant { selection: GearSelection; flat: Vector; percent: Vector; suit: string; cost: number }
interface Pair { items: [GearVariant, GearVariant]; flat: Vector; percent: Vector; suits: string[]; cost: number }
interface Bucket { percent: Vector; suits: string[]; values: Map<string, Pair> }
const sum = (a: Vector, b: Vector) => a.map((v, i) => v + b[i]) as Vector;
const project = (v: Vector, mask: number[]) => mask.map(a => v[a]).join(",");
const includes = (mask: number[], required: number[]) => required.every(a => mask.includes(a));
const count = (suits: string[], id: string) => suits.filter(s => s === id).length;

function gearVariants(data: GameData, character: Character, request: SearchRequest, mask: number[], flatOnly: boolean) {
  const state = characterState(data, {...request, potential: 0});
  const importantSets = new Set(data.sets.filter(s => s.modifiers.some(m => axes(m, character).some(a => mask.includes(a)))).map(s => s.id));
  const slots: GearVariant[][] = [];
  for (let slot = 0; slot < 3; slot++) {
    const dedup = new Map<string, GearVariant>();
    dedup.set("empty", {selection: {id: "", refinements: []}, flat: zero(), percent: zero(), suit: "", cost: 0});
    for (const item of data.equipment) {
      if (item.slot !== slot || item.minLevel > request.level || item.tier > state.tier) continue;
      const ranks = item.modifiers.map(m => {
        if (!axes(m, character).some(a => mask.includes(a))) return [0];
        const seen = new Set<number>();
        return m.values.flatMap((value, rank) => {
          if (rank > request.maxGearRefine || seen.has(value)) return [];
          seen.add(value); return [rank];
        });
      });
      const expand = (i: number, selected: number[]) => {
        if (i < ranks.length) { for (const rank of ranks[i]) expand(i + 1, [...selected, rank]); return; }
        const flat = zero(), percent = zero();
        item.modifiers.forEach((m, index) => {
          for (const a of axes(m, character)) (m.stage === "flat" ? flat : percent)[a] += m.values[selected[index]];
        });
        if (flatOnly && mask.some(a => percent[a] !== 0)) return;
        const suit = importantSets.has(item.set) ? item.set : "";
        const cost = selected.reduce((a, b) => a + b, 0);
        const key = [project(flat, mask), project(percent, mask), suit].join("|");
        if (!dedup.has(key) || dedup.get(key)!.cost > cost) {
          dedup.set(key, {selection: {id: item.id, refinements: selected}, flat, percent, suit, cost});
        }
      };
      expand(0, []);
    }
    slots.push([...dedup.values()].sort((a, b) => a.cost - b.cost));
  }
  return slots;
}

function weaponVariants(data: GameData, character: Character, request: SearchRequest) {
  const dedup = new Map<string, {selection: WeaponSelection; flat: Vector; percent: Vector; cost: number}>();
  for (const weapon of data.weapons) if (weapon.type === character.weaponType) {
    for (let refinement = 0; refinement <= request.maxWeaponRefine; refinement++) {
      for (let gemFirst = 0; gemFirst <= request.maxGemFirst; gemFirst++) {
        for (let gemPassive = 0; gemPassive <= (weapon.passiveScope ? request.maxGemPassive : 0); gemPassive++) {
          const selection = {id: weapon.id, refinement, gemFirst, gemPassive};
          const {flat, percent} = weaponStats(weapon, selection, character);
          const cost = refinement * 10 + gemFirst + gemPassive;
          const key = [weapon.id, flat.join(","), percent.join(",")].join("|");
          if (!dedup.has(key) || dedup.get(key)!.cost > cost) dedup.set(key, {selection, flat, percent, cost});
        }
      }
    }
  }
  return [...dedup.values()].sort((a, b) => a.cost - b.cost);
}

function makePair(a: GearVariant, b: GearVariant): Pair {
  return {items: [a, b], flat: sum(a.flat, b.flat), percent: sum(a.percent, b.percent),
    suits: [a.suit, b.suit].filter(Boolean).sort(), cost: a.cost + b.cost};
}

function masks(request: SearchRequest): number[][] {
  return Array.from({length: 15}, (_, i) => [0, 1, 2, 3].filter(a => (i + 1) & (1 << a)))
    .filter(mask => includes(mask, request.required)).sort((a, b) => b.length - a.length);
}

export function validateRequest(data: GameData, request: SearchRequest): void {
  characterState(data, {...request, potential: request.potential === "any" ? 0 : request.potential});
  for (const [value, min, max] of [[request.target, 1, 10000], [request.maxGearRefine, 0, 3],
    [request.maxWeaponRefine, 0, 5], [request.maxGemFirst, 0, 6], [request.maxGemPassive, 0, 3],
    [request.budgetMs, 100, 30000], [request.limit, 1, 20]]) {
    if (!Number.isInteger(value) || value < min || value > max) throw new Error("搜索参数超出范围");
  }
  if (new Set(request.required).size !== request.required.length || request.required.some(a => !Number.isInteger(a) || a < 0 || a > 3)) {
    throw new Error("属性选择无效");
  }
}

/** Bounded meet-in-the-middle search. Strategy is replaceable behind this interface.
 * Index accessory pairs by integer flat contribution and group by percentages/sets.
 * Larger target subsets get a dedicated budget before falling back to smaller subsets.
 * Pruning equivalent target contributions means this is a feasible-build search,
 * never a claim that the cheapest build or every build has been enumerated. */
export function searchBuilds(data: GameData, request: SearchRequest, progress: (phase: string) => void = () => {}): SearchResult {
  validateRequest(data, request);
  const start = performance.now();
  const deadline = start + request.budgetMs;
  const character = data.characters.find(c => c.id === request.characterId)!;
  const weapons = weaponVariants(data, character, request);
  const potentials = request.potential === "any" ? [0, 1, 2, 3, 4, 5] : [request.potential];
  // Potentials with the same permanent stats are equivalent; retain the lowest one.
  const states = potentials.map(potential => ({potential, ...characterState(data, {...request, potential})}))
    .filter((state, index, all) => all.findIndex(other => other.flat.join(",") === state.flat.join(",") &&
      other.percent.join(",") === state.percent.join(",")) === index);
  const results = new Map<string, Solution>();
  let candidates = 0, truncated = false;
  // Keep an inexpensive feasible baseline for slower devices before expanding affix ranks.
  // Recursion stops immediately because the seed request has zero gear refinement.
  if (request.maxGearRefine > 0 && request.budgetMs >= 2000) {
    progress("先寻找低锤炼基础方案");
    const seed = searchBuilds(data, {...request, maxGearRefine: 0,
      budgetMs: Math.min(1000, Math.floor(request.budgetMs * 0.1))});
    candidates += seed.candidates;
    for (const result of seed.results) results.set([result.build.potential, result.build.weapon.id,
      ...result.build.equipment.map(e => e.id)].join("|"), result);
  }
  let iterations = 0;
  const expired = (limit: number) => (++iterations & 511) === 0 && performance.now() >= limit;
  const ranked = () => [...results.values()].sort((a, b) => b.evaluation.matched.length - a.evaluation.matched.length ||
    a.cost - b.cost || a.build.potential - b.build.potential);
  for (const size of [4, 3, 2, 1]) {
    const groups = masks(request).filter(m => m.length === size);
    if (!groups.length) continue;
    if (ranked().filter(r => r.evaluation.matched.length >= size).length >= request.limit) { truncated = true; break; }
    // Reserve fallback time so an impossible four-way target cannot starve simpler solutions.
    const fraction = size === 4 ? 0.08 : size === 3 ? 0.54 : size === 2 ? 0.25 : 1;
    const sizeDeadline = size === 1 || request.required.length === size ? deadline : Math.min(deadline, performance.now() + request.budgetMs * fraction);
    progress(`正在寻找 ${size} 项属性同时 ${request.target} 的方案`);
    for (const [maskIndex, mask] of groups.entries()) {
      const maskDeadline = Math.min(sizeDeadline, performance.now() + Math.max(20, (sizeDeadline - performance.now()) / (groups.length - maskIndex)));
      if (performance.now() >= maskDeadline) { truncated = true; break; }
      // The flat plane usually contains many feasible builds. Search it first,
      // then expand to percentage equipment if the same target still needs results.
      for (const flatOnly of [true, false]) {
        if (performance.now() >= maskDeadline) { truncated = true; break; }
        const planeDeadline = flatOnly ? Math.min(maskDeadline, performance.now() + (maskDeadline - performance.now()) * 0.7) : maskDeadline;
        const slots = gearVariants(data, character, request, mask, flatOnly);
        const buckets = new Map<string, Bucket>();
        let entries = 0;
        outerIndex: for (let i = 0; i < slots[2].length; i++) for (let j = i; j < slots[2].length; j++) {
          if (expired(planeDeadline) || entries >= 120000) { truncated = true; break outerIndex; }
          const pair = makePair(slots[2][i], slots[2][j]);
          const key = project(pair.percent, mask) + "|" + pair.suits.join(",");
          let bucket = buckets.get(key);
          if (!bucket) { bucket = {percent: pair.percent, suits: pair.suits, values: new Map()}; buckets.set(key, bucket); }
          const flatKey = project(pair.flat, mask);
          const existing = bucket.values.get(flatKey);
          if (!existing || existing.cost > pair.cost) {
            if (!existing) entries++;
            bucket.values.set(flatKey, pair);
          }
        }
        // Zero-percent combinations first, then lower-cost combinations. All groups remain eligible.
        const orderedBuckets = [...buckets.values()].sort((a, b) => mask.reduce((s, axis) => s + a.percent[axis] - b.percent[axis], 0));
        const leftPairs: Pair[] = [];
        const maxLeftPairs = size === 4 ? 20000 : 80000;
        // Build in cost layers so the memory cap does not select an arbitrary first armor.
        const maxPairCost = Math.max(...slots[0].map(item => item.cost)) + Math.max(...slots[1].map(item => item.cost));
        outerLeft: for (let cost = 0; cost <= maxPairCost; cost++) {
          for (const armor of slots[0]) for (const glove of slots[1]) {
            if (armor.cost + glove.cost !== cost) continue;
            if (expired(planeDeadline) || leftPairs.length >= maxLeftPairs) { truncated = true; break outerLeft; }
            leftPairs.push(makePair(armor, glove));
          }
        }
        outerSearch: for (const weapon of weapons) for (const state of states) {
          const baseline = sum(state.flat, weapon.flat), baselinePercent = sum(state.percent, weapon.percent);
          if (mask.some(a => baseline[a] * (1 + baselinePercent[a]) >= request.target + 1)) continue;
          for (const bucket of orderedBuckets) {
            const fixedRanges = flatOnly ? mask.map(a => {
              const multiplier = 1 + baselinePercent[a];
              return [Math.ceil(request.target / multiplier - baseline[a] - 1e-9),
                Math.ceil((request.target + 1) / multiplier - baseline[a] + 1e-9) - 1];
            }) : null;
            if (fixedRanges?.some(([low, high]) => high < low)) continue;
            const relevantSets = data.sets.filter(s => bucket.suits.includes(s.id));
            for (const left of leftPairs) {
              if (expired(planeDeadline)) { truncated = true; break outerSearch; }
              const setBonus = zero();
              for (const suit of relevantSets) if (count(left.suits, suit.id) + count(bucket.suits, suit.id) >= suit.pieces) {
                for (const mod of suit.modifiers) for (const axis of axes(mod, character)) setBonus[axis] += mod.values[0];
              }
              const choices: number[][] = [];
              for (let m = 0; m < mask.length; m++) {
                const axis = mask[m];
                const multiplier = 1 + baselinePercent[axis] + left.percent[axis] + bucket.percent[axis];
                const prefix = baseline[axis] + left.flat[axis] + setBonus[axis];
                // Conservative lookup bounds; the independent verifier applies the exact interval.
                const lower = fixedRanges ? fixedRanges[m][0] - left.flat[axis] - setBonus[axis] :
                  Math.ceil(request.target / multiplier - prefix - 1e-9);
                const upper = fixedRanges ? fixedRanges[m][1] - left.flat[axis] - setBonus[axis] :
                  Math.ceil((request.target + 1) / multiplier - prefix + 1e-9) - 1;
                if (upper < lower || upper < 0) break;
                choices.push(Array.from({length: upper - lower + 1}, (_, i) => lower + i));
              }
              if (choices.length !== mask.length) continue;
              const lookup = (index: number, values: number[]) => {
                if (index < choices.length) { for (const value of choices[index]) lookup(index + 1, [...values, value]); return; }
                const right = bucket.values.get(values.join(","));
                if (!right) return;
                candidates++;
                const equipment = [...left.items, ...right.items].map(item => item.selection);
                const build = {characterId: request.characterId, level: request.level, potential: state.potential,
                  weapon: weapon.selection, equipment};
                const evaluation = evaluateBuild(data, build, request.target);
                if (!includes(evaluation.matched, mask) || !includes(evaluation.matched, request.required)) return;
                const cost = left.cost + right.cost + weapon.cost;
                const identity = [build.potential, weapon.selection.id, ...equipment.map(item => item.id)].join("|");
                const previous = results.get(identity);
                if (!previous || previous.evaluation.matched.length < evaluation.matched.length ||
                  (previous.evaluation.matched.length === evaluation.matched.length && previous.cost > cost)) {
                  results.set(identity, {build, evaluation, cost});
                }
                if (results.size > 100) {
                  const keep = ranked().slice(0, 50);
                  results.clear();
                  for (const result of keep) results.set([result.build.potential, result.build.weapon.id,
                    ...result.build.equipment.map(e => e.id)].join("|"), result);
                }
              };
              if (choices.every(c => c.length === 1)) lookup(choices.length, choices.map(c => c[0]));
              else lookup(0, []);
            }
          }
        }
        if (ranked().filter(r => includes(r.evaluation.matched, mask)).length >= request.limit) { truncated = true; break; }
      }
    }
    // Once enough larger-subset solutions exist, smaller subsets cannot improve the primary objective.
    if (ranked().filter(r => r.evaluation.matched.length >= size).length >= request.limit) { truncated = true; break; }
    if (performance.now() >= deadline) { truncated = true; break; }
  }
  const notes = ["按常驻面板计算：当前等级下可解锁的突破、能力节点全满；武器满级；不计队友、食物与战斗触发效果。",
    "搜索会合并属性贡献相同的装备组合，优先展示已找到的多属性方案，不保证全局最低养成成本。"];
  if (truncated) notes.push("本轮未穷尽所有组合；未找到方案不代表无解。可缩小指定属性或调整养成限制后重试。");
  return {results: ranked().slice(0, request.limit), elapsedMs: performance.now() - start, candidates,
    complete: !truncated, notes};
}
