/** Domain contracts independent of React, the OCR API and a particular search strategy. */
export type Vector = [number, number, number, number];
export interface Modifier {
  attribute: number;
  scope: number; // 0: explicit, 1: main, 2: sub, 3: all
  stage: "flat" | "percent";
  values: number[];
  index: number;
}
export interface Character {
  id: string; name: string; weaponType: number; main: number; sub: number; maxLevel: number;
  levels: {level: number; breakStage: number; base: Vector}[];
  nodes: {breakStage: number; modifiers: Modifier[]}[];
  passives: {breakStage: number; index: number; level: number; modifiers: Modifier[]}[];
  potentials: {level: number; modifiers: Modifier[]}[];
  tiers: {breakStage: number; tier: number}[];
}
export interface Equipment {
  id: string; name: string; slot: number; minLevel: number; tier: number; set: string; modifiers: Modifier[];
}
export interface Bound { lowerBound: number; upperBound: number }
export interface Weapon {
  id: string; name: string; type: number; rarity: number; level: number; attribute: number;
  first: {level: number; value: number}[]; bounds: Bound[];
  passiveScope: number; passive: {level: number; value: number}[];
  refine: {talentLv: number; skillLevelExtraBounds: Bound[]}[];
}
export interface StatSet { id: string; name: string; pieces: number; modifiers: Modifier[] }
export interface GameData {
  schemaVersion: number; rulesVersion: string; version: string; source: string; sourceUpdatedAt: string;
  characters: Character[]; equipment: Equipment[]; weapons: Weapon[]; sets: StatSet[];
}
export interface CharacterState { characterId: string; level: number; potential: number }
export interface GearSelection { id: string; refinements: number[] }
export interface WeaponSelection { id: string; refinement: number; gemFirst: number; gemPassive: number }
export interface Build extends CharacterState { weapon: WeaponSelection; equipment: GearSelection[] }
export interface Evaluation {
  raw: Vector; display: Vector; matched: number[]; activeSets: string[];
}
export interface Solution { build: Build; evaluation: Evaluation; cost: number }
export interface SearchRequest {
  characterId: string; level: number; potential: number | "any";
  target: number; required: number[]; maxGearRefine: number; maxWeaponRefine: number;
  maxGemFirst: number; maxGemPassive: number; budgetMs: number; limit: number;
}
export interface SearchResult {
  results: Solution[]; elapsedMs: number; candidates: number; complete: boolean; notes: string[];
}
export type WorkerRequest = {type: "search"; request: SearchRequest};
export type WorkerResponse = {type: "progress"; phase: string} |
  {type: "done"; result: SearchResult} | {type: "error"; message: string};
export const ATTRIBUTE_NAMES = ["力量", "敏捷", "智识", "意志"] as const;
export const DEFAULT_REQUEST: SearchRequest = {
  characterId: "chr_0034_typhoea", level: 90, potential: 0, target: 325, required: [],
  maxGearRefine: 3, maxWeaponRefine: 5, maxGemFirst: 6, maxGemPassive: 3,
  budgetMs: 10000, limit: 5,
};
