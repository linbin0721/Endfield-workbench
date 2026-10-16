import { useMemo } from "react";
import type { TFunction } from "i18next";
import { circuitPaletteForChannels, type CircuitDisplayColor } from "../../circuitDisplay";
import { useSurface } from "../../ui/surface";
import { circuitColorOnSurface } from "./circuitTheme";

/**
 * Circuit color names come from circuitDisplay.ts as canonical Chinese strings.
 * They are normalized here, at the display boundary, so the calculation palette
 * and its channel mapping stay untouched.
 */
const colorKeys: Record<string, string> = {
  "红色": "colors.red",
  "橙色": "colors.orange",
  "黄色": "colors.yellow",
  "绿色": "colors.green",
  "青色": "colors.cyan",
  "蓝色": "colors.blue",
  "紫色": "colors.purple",
  "品红色": "colors.magenta",
  "未知颜色": "colors.unknown",
};

export function colorName(t: TFunction, color: CircuitDisplayColor): string {
  return t(colorKeys[color.name] ?? "colors.unknown");
}

/** Channel colours for the active theme; an invalid palette falls back as a whole. */
export function useCircuitColors(channelCount: number, palette: unknown) {
  const surface = useSurface();
  return useMemo(() => {
    const resolved = circuitPaletteForChannels(channelCount, palette);
    return { colors: resolved.colors.map((color) => circuitColorOnSurface(color, surface)), usedFallback: resolved.usedFallback };
  }, [channelCount, palette, surface]);
}
