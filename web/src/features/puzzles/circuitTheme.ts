import type { CircuitDisplayColor } from "../../circuitDisplay";
import type { SurfaceName } from "../../ui/surface";

/**
 * Display colours of a circuit channel for the active theme. The dark theme
 * uses circuitDisplay.ts unchanged. On light boards the deep end of each piece
 * gradient and its outline are lifted, so pieces do not read as near-black
 * blocks on white cells. Hue, channel and colour name never change, and the
 * result is display-only (the API palette and the solver are untouched).
 */
export function circuitColorOnSurface(color: CircuitDisplayColor, surface: SurfaceName): CircuitDisplayColor {
  if (surface === "dark") return color;
  const hue = color.hueDegrees;
  return {
    ...color,
    fill: `hsl(${hue} 72% 52%)`,
    softFill: `hsl(${hue} 52% 37%)`,
    edge: `hsl(${hue} 70% 22%)`,
    highlight: `hsl(${hue} 92% 84%)`,
  };
}
