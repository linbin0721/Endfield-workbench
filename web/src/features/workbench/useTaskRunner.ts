import { useCallback, useEffect, useRef, useState } from "react";
import { cancelTask, getTask, type Task } from "../../api";

export type TaskKind = "recognition" | "solve";

/** What the runner is doing now; `task` is the latest server view once it exists. */
export type RunnerState = {
  kind: TaskKind;
  phase: "submitting" | "polling" | "done";
  task: Task | null;
} | null;

/** A run either finishes (any terminal status) or is superseded by a newer run, stop or unmount. */
export type RunOutcome = { finished: true; task: Task } | { finished: false };

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);
const POLL_MS = 700;

function pause(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const stop = () => { window.clearTimeout(timer); resolve(); };
    const timer = window.setTimeout(() => { signal.removeEventListener("abort", stop); resolve(); }, milliseconds);
    signal.addEventListener("abort", stop, { once: true });
  });
}

/**
 * One server task at a time: submit, poll until a terminal status, report it.
 * Starting a new run, `stop()` or unmounting supersedes the current run and
 * asks the server to cancel it; superseded runs never update state. Errors of
 * the current run are thrown to the caller, errors of superseded runs are
 * swallowed. Language switches re-render the owner without touching this.
 */
export function useTaskRunner() {
  const generation = useRef(0);
  const activeId = useRef<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const [state, setState] = useState<RunnerState>(null);

  const release = useCallback((notifyServer: boolean) => {
    generation.current += 1;
    controller.current?.abort();
    controller.current = null;
    if (notifyServer && activeId.current) void cancelTask(activeId.current).catch(() => {});
    activeId.current = null;
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; release(true); };
  }, [release]);

  /** Supersedes the current run (the server is told to cancel it) and clears the state. */
  const stop = useCallback(() => {
    release(true);
    setState(null);
  }, [release]);

  const run = useCallback(async (kind: TaskKind, submit: () => Promise<Task>): Promise<RunOutcome> => {
    release(true);
    const version = generation.current;
    const current = () => mounted.current && generation.current === version;
    setState({ kind, phase: "submitting", task: null });
    let task: Task;
    try {
      task = await submit();
    } catch (error) {
      if (!current()) return { finished: false };
      setState(null);
      throw error;
    }
    if (!current()) {
      void cancelTask(task.id).catch(() => {});
      return { finished: false };
    }
    activeId.current = task.id;
    const abort = new AbortController();
    controller.current = abort;
    setState({ kind, phase: "polling", task });
    try {
      for (;;) {
        task = await getTask(task.id, abort.signal);
        if (!current() || abort.signal.aborted) return { finished: false };
        if (TERMINAL.has(task.status)) break;
        setState({ kind, phase: "polling", task });
        await pause(POLL_MS, abort.signal);
        if (!current() || abort.signal.aborted) return { finished: false };
      }
    } catch (error) {
      if (!current() || abort.signal.aborted) return { finished: false };
      activeId.current = null;
      controller.current = null;
      setState(null);
      throw error;
    }
    activeId.current = null;
    controller.current = null;
    setState({ kind, phase: "done", task });
    return { finished: true, task };
  }, [release]);

  const busy = state !== null && state.phase !== "done";
  return { state, busy, run, stop };
}
