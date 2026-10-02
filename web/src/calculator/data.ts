import snapshot from "./data.json";
import type { GameData } from "./types.ts";

export const gameData = snapshot as unknown as GameData;
