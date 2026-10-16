import { useCallback, useEffect, useRef, useState } from "react";
import { getCapabilities, type Capability } from "../../api";
import type { MessageText } from "../../i18n";

export type ServiceState = "loading" | "ready" | "error";

/**
 * Loads the solving service's capability list on mount and on demand. The
 * page decides what a capability means; `explain` turns failures into a
 * message reference so a language switch re-translates it.
 */
export function useServiceCapabilities(explain: (error: unknown) => MessageText) {
  const [state, setState] = useState<ServiceState>("loading");
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [error, setError] = useState<MessageText>("");
  const mounted = useRef(true);
  const explainRef = useRef(explain);
  explainRef.current = explain;

  const refresh = useCallback(async (signal?: AbortSignal) => {
    setState("loading");
    setError("");
    try {
      const list = await getCapabilities(signal);
      if (signal?.aborted || !mounted.current) return;
      setCapabilities(list);
      setState("ready");
    } catch (caught) {
      if (signal?.aborted || !mounted.current) return;
      setCapabilities([]);
      setState("error");
      setError(explainRef.current(caught));
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => { mounted.current = false; controller.abort(); };
  }, [refresh]);

  return { state, capabilities, error, refresh };
}
