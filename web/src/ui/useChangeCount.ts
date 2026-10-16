import { useRef } from "react";

/**
 * Counts how often `value` changed identity. A new solve result gets a new
 * number (replaying the success animation); re-renders such as a language
 * switch keep the same number, so nothing replays.
 */
export function useChangeCount(value: unknown): number {
  const state = useRef<{ value: unknown; count: number }>({ value: undefined, count: 0 });
  if (state.current.value !== value) state.current = { value, count: state.current.count + 1 };
  return state.current.count;
}
