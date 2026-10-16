import type { CSSProperties, KeyboardEvent } from "react";
import { IconButton } from "../../ui/IconButton/IconButton";
import { MinusIcon, PlusIcon } from "../../ui/icons";
import s from "./calculator.module.css";

type LevelControlProps = {
  id: string;
  label: string;
  /** Text in the number box; it may be temporarily invalid while typing. */
  text: string;
  /** Valid level shown by the slider (the clamped value of `text`). */
  level: number;
  max: number;
  valid: boolean;
  invalidText: string;
  decreaseLabel: string;
  increaseLabel: string;
  sliderLabel: string;
  onText: (text: string) => void;
  onBlur: () => void;
};

/**
 * Level as a slider with -1 / +1 buttons, keeping the number box. Arrows move
 * by 1, PageUp / PageDown by 10, Home / End jump to 1 / max. Every change goes
 * through `onText`, exactly as typing the number would.
 */
export function LevelControl({ id, label, text, level, max, valid, invalidText,
  decreaseLabel, increaseLabel, sliderLabel, onText, onBlur }: LevelControlProps) {
  const set = (value: number) => onText(String(Math.min(max, Math.max(1, value))));
  const onSliderKey = (event: KeyboardEvent<HTMLInputElement>) => {
    const jump: Record<string, number> = { PageUp: level + 10, PageDown: level - 10, Home: 1, End: max };
    if (event.key in jump) {
      event.preventDefault();
      set(jump[event.key]);
    }
  };
  const fill = max > 1 ? ((level - 1) / (max - 1)) * 100 : 100;
  return <div className={s.field}>
    <label className={s.label} htmlFor={id}>{label}</label>
    <div className={s.level}>
      <IconButton className={s.stepper} label={decreaseLabel} icon={<MinusIcon />} disabled={level <= 1} onClick={() => set(level - 1)} />
      <input className={s.range} type="range" min={1} max={max} step={1} value={level} aria-label={sliderLabel}
        style={{ "--fill": `${fill}%` } as CSSProperties}
        onChange={(event) => set(Number(event.target.value))} onKeyDown={onSliderKey} />
      <IconButton className={s.stepper} label={increaseLabel} icon={<PlusIcon />} disabled={level >= max} onClick={() => set(level + 1)} />
      <input id={id} className={`${s.input} ${s.levelInput}`} type="number" inputMode="numeric" min={1} max={max} step={1}
        value={text} onChange={(event) => onText(event.target.value)} onBlur={onBlur} />
    </div>
    {!valid && <span className={s.errorText}>{invalidText}</span>}
  </div>;
}
