import { useEffect, useRef, useState, type ReactNode } from "react";
import { loadNamespaces, useAppTranslation, useLocale, type Namespace } from "../i18n";
import { LoadingState } from "./LoadingState";

type ToolResourcesProps = {
  namespaces: readonly Namespace[];
  /** Loads the page code in parallel with the language bundles. */
  preload: () => Promise<unknown>;
  children: ReactNode;
};

/** Wait on entry to a tool; never replace a mounted tool during a switch. */
export function ToolResources({ namespaces, preload, children }: ToolResourcesProps) {
  const { locale } = useLocale();
  const { t } = useAppTranslation("common");
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  // Browsers keep a failed dynamic import cached, so only a reload retries the code.
  const codeFailed = useRef(false);
  const namespaceKey = namespaces.join(",");
  useEffect(() => {
    let active = true;
    const code = preload().catch((error: unknown) => { codeFailed.current = true; throw error; });
    void Promise.all([loadNamespaces(locale, namespaceKey.split(",") as Namespace[]), code]).then(() => {
      if (active) { setReady(true); setFailed(false); }
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [locale, namespaceKey, preload, retry]);
  if (ready) return children;
  return <LoadingState
    failed={failed}
    message={codeFailed.current ? t("loadError") : t("language.error")}
    onRetry={() => {
      if (codeFailed.current) { window.location.reload(); return; }
      setFailed(false);
      setRetry((value) => value + 1);
    }}
  />;
}
