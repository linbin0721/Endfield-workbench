import type { ReactNode } from "react";
import { Button } from "../../ui/Button/Button";
import { Panel } from "../../ui/Panel/Panel";
import { SectionTitle } from "../../ui/SectionTitle/SectionTitle";
import { RefreshIcon } from "../../ui/icons";
import s from "./puzzles.module.css";

/** Joins class names, skipping empty ones. */
export const cx = (...names: Array<string | false | null | undefined>) => names.filter(Boolean).join(" ");

export type ModeOption<T extends string> = {
  mode: T;
  title: string;
  note: string;
  icon: ReactNode;
  /** Id of the flow this entry reveals. */
  controls: string;
};

/**
 * The two entries of a puzzle page. Nothing is selected at first; choosing the
 * other entry is handled by the page (it cancels the running task and clears).
 */
export function ModeSwitch<T extends string>({ label, value, options, onSelect }: {
  label: string;
  value: T | null;
  options: ModeOption<T>[];
  onSelect: (mode: T) => void;
}) {
  return <div className={s.modes} role="group" aria-label={label}>
    {options.map((option) => <button key={option.mode} type="button" className={s.mode}
      aria-expanded={value === option.mode} aria-controls={option.controls} onClick={() => onSelect(option.mode)}>
      <span className={s.modeIcon} aria-hidden="true">{option.icon}</span>
      <span className={s.modeTitle}>{option.title}</span>
      <span className={s.modeNote}>{option.note}</span>
    </button>)}
  </div>;
}

/** Connection state of the solving service, with a retry after a failure. */
export function ServiceStatus({ state, text, retryLabel, onRetry, hint = false }: {
  /** "missing": the service answered but does not offer this puzzle. */
  state: "loading" | "ready" | "error" | "missing";
  text: ReactNode;
  retryLabel: string;
  onRetry: () => void;
  /** Second copy next to the main action while the connection is unresolved. */
  hint?: boolean;
}) {
  return <div className={s.service} role="status" aria-live="polite" data-service={state}
    data-service-hint={hint ? state : undefined}>
    <span className={s.serviceDot} aria-hidden="true" />
    <span className={s.serviceText}>{text}</span>
    {state === "error"
      ? <Button variant="ghost" size="sm" onClick={onRetry} icon={<RefreshIcon />}>{retryLabel}</Button>
      : null}
  </div>;
}

/** Small eyebrow label above a yellow-bar section title, with an optional badge. */
export function SectionHead({ eyebrow, title, id, badge }: {
  eyebrow?: ReactNode;
  title: ReactNode;
  id?: string;
  badge?: ReactNode;
}) {
  return <div className={s.head}>
    {eyebrow ? <p className={s.eyebrow}>{eyebrow}</p> : null}
    <SectionTitle id={id} aside={badge ? <span className={s.badge}>{badge}</span> : undefined}>{title}</SectionTitle>
  </div>;
}

export function TaskStatus({ status, children }: { status: string; children: ReactNode }) {
  return <p className={s.taskStatus} role="status" aria-live="polite" data-task-status={status}>{children}</p>;
}

/**
 * Answer area. Before an answer exists it shows an empty board frame, so the
 * layout does not jump; the frame and the board follow the site theme.
 */
export function AnswerPanel({ label, eyebrow, title, source, waiting, sourceKey, children }: {
  label: string;
  eyebrow?: ReactNode;
  title: ReactNode;
  source?: ReactNode;
  waiting: ReactNode;
  /** Stable answer-source id for diagnostics (data-answer-source). */
  sourceKey?: string;
  children?: ReactNode;
}) {
  return <Panel as="section" corners aria-label={label} data-answer-panel="" data-answer-source={sourceKey}>
    <SectionHead eyebrow={eyebrow} title={title} />
    <div className={s.answer}>
      {children
        ? <>{source ? <p className={s.answerSource}>{source}</p> : null}{children}</>
        : <div className={s.waiting}><p className={s.waitingText}>{waiting}</p></div>}
    </div>
  </Panel>;
}
