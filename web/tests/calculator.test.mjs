import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { characterState, evaluateBuild, weaponStats } from "../src/calculator/evaluate.ts";
import { searchBuilds } from "../src/calculator/search.ts";
import { DEFAULT_REQUEST } from "../src/calculator/types.ts";

const data = JSON.parse(fs.readFileSync(new URL("../src/calculator/data.json", import.meta.url)));
const ember = "chr_0009_azrila";
const gear = (id, refs = {}) => ({id, refinements: data.equipment.find(e => e.id === id).modifiers.map(m => refs[m.attribute] ?? 0)});
const fixture = {
  characterId: ember, level: 90, potential: 0,
  weapon: {id: "wpn_claym_0004", refinement: 0, gemFirst: 1, gemPassive: 0},
  equipment: [gear("item_equip_t4_suit_criti01_body_04"), gear("item_equip_t4_suit_atk02_hand_02"),
    gear("item_equip_t4_suit_criti01_edc_01"), gear("item_equip_t4_suit_atk02_edc_04")],
};
const triple = {...fixture, potential: 2,
  weapon: {id: "wpn_claym_0009", refinement: 0, gemFirst: 5, gemPassive: 0},
  equipment: [gear("item_equip_t4_suit_atk02_body_02", {0: 2, 1: 3}),
    gear("item_equip_t4_suit_atk02_hand_02", {3: 1, 1: 3}),
    gear("item_equip_t4_suit_criti01_edc_06", {1: 2}), gear("item_equip_t4_suit_atk02_edc_04", {3: 1, 1: 1})],
};

test("prior independently researched Ember P0 double-325 baseline", () => {
  const result = evaluateBuild(data, fixture);
  assert.deepEqual(result.display, [325, 218, 86, 325]);
  assert.deepEqual(result.matched, [0, 3]);
  assert.ok(Math.abs(result.raw[0] - 325.4117399537139) < 1e-10);
});
test("prior Ember P2 triple-325 baseline; each affix refines independently", () => {
  const result = evaluateBuild(data, triple);
  assert.deepEqual(result.display, [325, 325, 107, 325]);
  assert.deepEqual(result.matched, [0, 1, 3]);
  assert.deepEqual(result.activeSets, []); // 应龙 only changes ATK/damage.
});
test("all 33 operators have every legal level and cumulative potentials", () => {
  assert.equal(data.characters.length, 33);
  assert.equal(data.weapons.length, 80);
  assert.equal(data.equipment.length, 258);
  for (const character of data.characters) {
    for (let level = 1; level <= character.maxLevel; level++) for (const potential of [0, 5]) {
      const state = characterState(data, {characterId: character.id, level, potential});
      assert.ok(state.flat.every(Number.isFinite));
      assert.ok(state.tier >= 2 && state.tier <= 5);
    }
  }
  assert.equal(characterState(data, {...fixture, potential: 1}).flat[0], characterState(data, fixture).flat[0]);
  assert.ok(Math.abs(characterState(data, {...fixture, potential: 2}).flat[0] - characterState(data, fixture).flat[0] - 20) < 1e-10);
});
test("boundary breakthroughs and legal node/tier limits", () => {
  for (const [level, stage, tier] of [[19, 0, 2], [20, 1, 3], [39, 1, 3], [40, 2, 4], [60, 3, 5], [80, 4, 5]]) {
    const state = characterState(data, {...fixture, level});
    assert.equal(state.breakStage, stage); assert.equal(state.tier, tier);
  }
  assert.throws(() => evaluateBuild(data, {...fixture, level: 19}), /尚未解锁/);
  assert.throws(() => characterState(data, {...fixture, level: 99}), /等级/);
});
test("reject wrong weapon, slots, potential and affix ranks", () => {
  assert.throws(() => evaluateBuild(data, {...fixture, potential: 6}), /潜能/);
  assert.throws(() => evaluateBuild(data, {...fixture, weapon: {...fixture.weapon, id: "wpn_funnel_0008"}}), /类型/);
  assert.throws(() => evaluateBuild(data, {...fixture, equipment: [fixture.equipment[1], ...fixture.equipment.slice(1)]}), /位置/);
  assert.throws(() => evaluateBuild(data, {...fixture, equipment: [{...fixture.equipment[0], refinements: [4, 0]}, ...fixture.equipment.slice(1)]}), /锤炼/);
});
test("max-level first skill starts at 3, essence raises it without weapon refinement", () => {
  const character = data.characters.find(c => c.id === ember);
  const weapon = data.weapons.find(w => w.id === fixture.weapon.id);
  assert.equal(weapon.bounds[0].lowerBound, 3);
  const first = weaponStats(weapon, fixture.weapon, character);
  assert.equal(first.flat[0], 57);
});
test("布道自由 all_attr_up key means MAIN ability; 负山 conditional buff excluded", () => {
  const preaching = data.weapons.find(w => w.id === "wpn_funnel_0012");
  const mountain = data.weapons.find(w => w.id === "wpn_lance_0012");
  assert.equal(preaching.passiveScope, 1);
  assert.equal(preaching.passive.at(-1).value, 0.14);
  assert.equal(mountain.passiveScope, 0);
});
test("percentage applies after all flat contributions, not each rounded item", () => {
  const copy = structuredClone(data);
  const w = copy.weapons.find(w => w.id === fixture.weapon.id);
  w.passiveScope = 1; w.passive = Array.from({length: 9}, (_, i) => ({level: i + 1, value: 0.1}));
  const result = evaluateBuild(copy, fixture);
  assert.ok(Math.abs(result.raw[0] - (236.4117399537139 + 57 + 32) * 1.1) < 1e-9);
  assert.equal(result.display[0], 357);
});
test("three-piece permanent +50 set effect included once and multiplied with gear percentage", () => {
  const copy = structuredClone(data);
  const suit = copy.sets.find(s => s.id === "suit_str01");
  const selection = structuredClone(fixture);
  for (const g of selection.equipment.slice(0, 3)) copy.equipment.find(e => e.id === g.id).set = suit.id;
  const firstGear = copy.equipment.find(e => e.id === selection.equipment[0].id);
  firstGear.modifiers.push({scope: 0, attribute: 0, stage: "percent", values: [0.2], index: 3});
  selection.equipment[0].refinements.push(0);
  const result = evaluateBuild(copy, selection);
  assert.deepEqual(result.activeSets, [suit.id]);
  assert.ok(Math.abs(result.raw[0] - (325.4117399537139 + 50) * 1.2) < 1e-9);
});
test("raw interval [325,326) is checked without an epsilon or per-item rounding", () => {
  const copy = structuredClone(data);
  const c = copy.characters.find(c => c.id === ember);
  c.nodes = []; c.potentials = []; c.passives = [];
  const row = c.levels.find(r => r.level === 90);
  const b = {...fixture, equipment: Array.from({length: 4}, () => ({id: "", refinements: []}))};
  row.base = [268, 325.9999999999, 326, 324.9999999999];
  assert.deepEqual(evaluateBuild(copy, b).matched, [0, 1]);
});
test("identical accessories are legal and count twice for sets", () => {
  const b = {...fixture, equipment: [...fixture.equipment.slice(0, 3), fixture.equipment[2]]};
  assert.doesNotThrow(() => evaluateBuild(data, b));
});
test("invalid search request rejected before large allocations", () => {
  assert.throws(() => searchBuilds(data, {...DEFAULT_REQUEST, maxGearRefine: 4}), /范围/);
  assert.throws(() => searchBuilds(data, {...DEFAULT_REQUEST, required: [1, 1]}), /无效/);
  assert.throws(() => searchBuilds(data, {...DEFAULT_REQUEST, budgetMs: Infinity}), /范围/);
});

// Small real-item catalog keeps exhaustive search tests fast and deterministic.
function fixtureData() {
  const ids = new Set([...fixture.equipment, ...triple.equipment].map(g => g.id));
  return {...data, characters: data.characters.filter(c => c.id === ember),
    equipment: data.equipment.filter(e => ids.has(e.id)),
    weapons: data.weapons.filter(w => [fixture.weapon.id, triple.weapon.id].includes(w.id))};
}
test("MITM finds triple-325 with any potential, ranks ahead of double, independent recheck", () => {
  const reduced = fixtureData();
  const request = {...DEFAULT_REQUEST, characterId: ember, potential: "any", budgetMs: 3000};
  const r = searchBuilds(reduced, request);
  assert.ok(r.results.length > 0);
  assert.equal(r.results[0].evaluation.matched.length, 3);
  assert.equal(r.results[0].build.potential, 2);
  for (const s of r.results) assert.deepEqual(evaluateBuild(reduced, s.build), s.evaluation);
  assert.ok(r.results.every((s, i) => i === 0 || r.results[i - 1].evaluation.matched.length >= s.evaluation.matched.length));
});
test("explicit required attributes and cultivation limits enforced on returned builds", () => {
  const reduced = fixtureData();
  const r = searchBuilds(reduced, {...DEFAULT_REQUEST, characterId: ember, required: [0, 3], maxGearRefine: 0, maxWeaponRefine: 0, budgetMs: 2000});
  assert.ok(r.results.length);
  for (const s of r.results) {
    assert.deepEqual(s.evaluation.matched, [0, 3]);
    assert.equal(s.build.potential, 0); assert.equal(s.build.weapon.refinement, 0);
    assert.ok(s.build.equipment.every(g => g.refinements.every(v => v === 0)));
  }
});
test("search includes percentage weapon and equipment as well as permanent set bonuses", () => {
  const reduced = fixtureData();
  const copy = structuredClone(reduced);
  const c = copy.characters[0]; c.nodes = []; c.passives = []; c.potentials = [];
  c.levels.find(r => r.level === 90).base = [150.3, 60, 60, 60];
  copy.equipment = copy.equipment.slice(0, 1);
  copy.equipment[0].modifiers = [{attribute: 0, scope: 0, stage: "flat", values: [70], index: 1},
    {attribute: 0, scope: 0, stage: "percent", values: [0.174], index: 3}];
  copy.equipment[0].set = "";
  copy.weapons = copy.weapons.slice(0, 1);
  copy.weapons[0].first = [{level: 3, value: 57}];
  copy.weapons[0].bounds[0] = {lowerBound: 3, upperBound: 3};
  const r = searchBuilds(copy, {...DEFAULT_REQUEST, characterId: ember, required: [0], budgetMs: 1000, maxGemFirst: 0});
  assert.ok(r.results.length); assert.equal(r.results[0].evaluation.display[0], 325);
});
