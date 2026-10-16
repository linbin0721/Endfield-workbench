import { useRef, type KeyboardEvent, type PointerEvent } from "react";
import { clampCrop, type Crop } from "./useImageSource";
import s from "./workbench.module.css";

type Corner = "nw" | "ne" | "sw" | "se";
type Drag = { mode: "move" | Corner; x: number; y: number; start: Crop };
const MIN = 3;

function resize(start: Crop, corner: Corner, dx: number, dy: number): Crop {
  let { left, top, width, height } = start;
  if (corner === "nw" || corner === "sw") {
    const nextLeft = Math.min(Math.max(0, left + dx), left + width - MIN);
    width += left - nextLeft; left = nextLeft;
  } else {
    width = Math.max(MIN, Math.min(100 - left, width + dx));
  }
  if (corner === "nw" || corner === "ne") {
    const nextTop = Math.min(Math.max(0, top + dy), top + height - MIN);
    height += top - nextTop; top = nextTop;
  } else {
    height = Math.max(MIN, Math.min(100 - top, height + dy));
  }
  return { left, top, width, height };
}

function move(start: Crop, dx: number, dy: number): Crop {
  return {
    ...start,
    left: Math.max(0, Math.min(100 - start.width, start.left + dx)),
    top: Math.max(0, Math.min(100 - start.height, start.top + dy)),
  };
}

const ARROWS: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };

/**
 * Crop rectangle over the image: drag inside to move, drag a corner to
 * resize. With the keyboard, arrows move the box or the focused corner by 1%
 * (Shift: 5%). Values are percentages of the original image.
 */
export function CropBox({ crop, onChange, boxLabel, cornerLabels }: {
  crop: Crop;
  onChange: (crop: Crop) => void;
  boxLabel: string;
  cornerLabels: Record<Corner, string>;
}) {
  const layer = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);

  const begin = (mode: Drag["mode"]) => (event: PointerEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { mode, x: event.clientX, y: event.clientY, start: crop };
  };
  const update = (event: PointerEvent<HTMLElement>) => {
    const current = drag.current;
    const box = layer.current?.getBoundingClientRect();
    if (!current || !box || box.width === 0 || box.height === 0) return;
    const dx = ((event.clientX - current.x) / box.width) * 100;
    const dy = ((event.clientY - current.y) / box.height) * 100;
    onChange(clampCrop(current.mode === "move" ? move(current.start, dx, dy) : resize(current.start, current.mode, dx, dy)));
  };
  const end = () => { drag.current = null; };
  const keys = (mode: Drag["mode"]) => (event: KeyboardEvent<HTMLElement>) => {
    const arrow = ARROWS[event.key];
    if (!arrow) return;
    event.preventDefault();
    event.stopPropagation();
    const step = event.shiftKey ? 5 : 1;
    const [dx, dy] = [arrow[0] * step, arrow[1] * step];
    onChange(clampCrop(mode === "move" ? move(crop, dx, dy) : resize(crop, mode, dx, dy)));
  };

  return <div ref={layer} className={s.cropLayer}>
    <div className={s.cropBox} tabIndex={0} role="group" aria-label={boxLabel}
      style={{ left: `${crop.left}%`, top: `${crop.top}%`, width: `${crop.width}%`, height: `${crop.height}%` }}
      onPointerDown={begin("move")} onPointerMove={update} onPointerUp={end} onPointerCancel={end} onKeyDown={keys("move")}>
      {(["nw", "ne", "sw", "se"] as const).map((corner) => <span key={corner} className={s.handle} data-corner={corner}
        tabIndex={0} role="button" aria-label={cornerLabels[corner]}
        onPointerDown={begin(corner)} onPointerMove={update} onPointerUp={end} onPointerCancel={end} onKeyDown={keys(corner)} />)}
    </div>
  </div>;
}
