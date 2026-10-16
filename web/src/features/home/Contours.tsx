/**
 * Decorative topographic lines, generated once from a fixed seed so every
 * visit draws the same map: nested loops around one summit. All lines share
 * one outline scaled by their radius, plus a small wobble of their own that
 * stays well below the line spacing, so no two lines ever touch.
 */

const WIDTH = 1200;
const HEIGHT = 560;
const CENTER_X = 860;
const CENTER_Y = 250;
const STRETCH = 1.35;
const LEVELS = 10;
const FIRST_RADIUS = 46;
const SPACING = 38;
/** Per-line wobble in px; the shared outline keeps neighbours >= 0.74 x SPACING apart. */
const DETAIL = 6;
const SAMPLES = 18;

type Point = readonly [number, number];

function random(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function ring(radius: number, outline: readonly number[], detail: readonly number[]): string {
  const points = Array.from({ length: SAMPLES }, (_, index): Point => {
    const angle = (index / SAMPLES) * Math.PI * 2;
    const shape = 1
      + 0.13 * Math.sin(angle * 2 + outline[0])
      + 0.08 * Math.sin(angle * 3 + outline[1])
      + 0.05 * Math.sin(angle * 5 + outline[2]);
    const r = radius * shape + DETAIL * Math.sin(angle * 4 + detail[0]) * Math.sin(angle * 3 + detail[1]);
    return [CENTER_X + Math.cos(angle) * r * STRETCH, CENTER_Y + Math.sin(angle) * r];
  });
  // Quadratic segments through the midpoints give a smooth closed curve.
  const mid = (a: Point, b: Point) => `${Math.round((a[0] + b[0]) / 2)} ${Math.round((a[1] + b[1]) / 2)}`;
  let path = `M${mid(points[SAMPLES - 1], points[0])}`;
  points.forEach((point, index) => {
    path += `Q${Math.round(point[0])} ${Math.round(point[1])} ${mid(point, points[(index + 1) % SAMPLES])}`;
  });
  return `${path}Z`;
}

function buildPaths(): string[] {
  const next = random(20261015);
  const turn = () => next() * Math.PI * 2;
  const outline = [turn(), turn(), turn()];
  return Array.from({ length: LEVELS }, (_, level) => ring(FIRST_RADIUS + level * SPACING, outline, [turn(), turn()]));
}

const PATHS = buildPaths();
/** Index of the line that carries the moving highlight. */
const PULSE_LINE = 4;

export function Contours({ className, lineClassName, pulseClassName }: {
  className?: string;
  lineClassName?: string;
  pulseClassName?: string;
}) {
  return <svg className={className} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="xMaxYMid slice" aria-hidden="true" focusable="false">
    <g fill="none">
      {PATHS.map((d, index) => <path key={index} className={lineClassName} d={d} />)}
      <path className={pulseClassName} d={PATHS[PULSE_LINE]} pathLength={1000} />
    </g>
  </svg>;
}
