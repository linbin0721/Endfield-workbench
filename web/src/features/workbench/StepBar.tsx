import { CheckIcon } from "../../ui/icons";
import s from "./workbench.module.css";

export type Step = { key: string; label: string };

/** Progress through import → puzzle → answer; the current step is marked for assistive tech too. */
export function StepBar({ steps, current, label }: { steps: Step[]; current: number; label: string }) {
  return <ol className={s.steps} aria-label={label}>
    {steps.map((step, index) => {
      const state = index < current ? "done" : index === current ? "current" : "todo";
      return <li key={step.key} className={s.step} data-state={state} aria-current={state === "current" ? "step" : undefined}>
        <span className={s.stepIndex} aria-hidden="true">{state === "done" ? <CheckIcon /> : String(index + 1).padStart(2, "0")}</span>
        <span className={s.stepLabel}>{step.label}</span>
      </li>;
    })}
  </ol>;
}
