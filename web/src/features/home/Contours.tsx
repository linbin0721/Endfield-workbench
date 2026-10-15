/**
 * Decorative topographic lines, generated once from a fixed seed so every
 * visit draws the same map. Smoothed closed loops around two summits.
 */

const WIDTH = 1200;
const HEIGHT = 560;

function random(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function ring(cx: number, cy: number, radius: number, stretch: number, next: () => number): string {
  const count = 18;
  const phases = [next() * Math.PI * 2, next() * Math.PI * 2, next() * Math.PI * 2];
  const points = Array.from({ length: count }, (_, index) => {
    const angle = (index / count) * Math.PI * 2;
    const wobble = 1
      + 0.13 * Math.sin(angle * 2 + phases[0])
      + 0.08 * Math.sin(angle * 3 + phases[1])
      + 0.05 * Math.sin(angle * 5 + phases[2]);
    return [cx + Math.cos(angle) * radius * stretch * wobble, cy + Math.sin(angle) * radius * wobble] as const;
  });
  // Quadratic segments through the midpoints give a smooth closed curve.
  const mid = (a: readonly [number, number], b: readonly [number, number]) =>
    `${Math.round((a[0] + b[0]) / 2)} ${Math.round((a[1] + b[1]) / 2)}`;
  let path = `M${mid(points[count - 1], points[0])}`;
  points.forEach((point, index) => {
    path += `Q${Math.round(point[0])} ${Math.round(point[1])} ${mid(point, points[(index + 1) % count])}`;
  });
  return `${path}Z`;
}

function buildPaths(): string[] {
  const next = random(20261015);
  const paths: string[] = [];
  for (let level = 0; level < 9; level += 1) paths.push(ring(860, 250, 46 + level * 38, 1.35, next));
  for (let level = 0; level < 5; level += 1) paths.push(ring(300, 470, 40 + level * 34, 1.6, next));
  return paths;
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
