import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { Navigate, Outlet, Route, Routes, useLocation, useParams } from "react-router-dom";
import BalloonPage from "./BalloonPage";
import CircuitPage from "./CircuitPage";
import HomePage from "./HomePage";
import NotFoundPage from "./NotFoundPage";
import SiteLayout from "./SiteLayout";
import {
  localizePath,
  loadNamespaces,
  matchLocaleSegment,
  stripLocalePrefix,
  useAppTranslation,
  useLocale,
  type Namespace,
} from "./i18n";

/** Only the /325 route pulls in the calculator page, its data.json bundle and calculator.css. */
const CalculatorPage = lazy(() => import("./CalculatorPage"));

/** Wait on entry to a tool; never replace a mounted tool during a switch. */
function ToolResources({ namespaces, children }: { namespaces: Namespace[]; children: ReactNode }) {
  const { locale } = useLocale();
  const { t } = useAppTranslation("common");
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const namespaceKey = namespaces.join(",");
  useEffect(() => {
    let active = true;
    void loadNamespaces(locale, namespaceKey.split(",") as Namespace[]).then(() => {
      if (active) { setReady(true); setFailed(false); }
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [locale, namespaceKey, retry]);
  if (ready) return children;
  return <p className="notice" role={failed ? "alert" : "status"}>
    {failed ? t("language.error") : t("loading")}
    {failed && <button type="button" className="text-button" onClick={() => { setFailed(false); setRetry(value => value + 1); }}>{t("language.retry")}</button>}
  </p>;
}

/**
 * Guards the /:locale prefix. The same route element is reused for every
 * language, so changing the prefix only changes params and never remounts the
 * pages (screenshots, crops, tasks and workers keep running).
 */
function LocaleRoute() {
  const { locale } = useParams();
  if (!matchLocaleSegment(locale)) return <NotFoundPage />;
  return <Outlet />;
}

/** Old unprefixed URLs replace to the same page in the selected language. */
function LegacyRedirect() {
  const location = useLocation();
  const { locale } = useLocale();
  return (
    <Navigate
      replace
      to={{
        pathname: localizePath(stripLocalePrefix(location.pathname), locale),
        search: location.search,
        hash: location.hash,
      }}
    />
  );
}

export default function App() {
  const { t } = useAppTranslation("common");
  return <Routes>
    <Route element={<SiteLayout />}>
      <Route index element={<LegacyRedirect />} />
      <Route path="balloon" element={<LegacyRedirect />} />
      <Route path="circuit" element={<LegacyRedirect />} />
      <Route path="325" element={<LegacyRedirect />} />
      <Route path=":locale" element={<LocaleRoute />}>
        <Route index element={<HomePage />} />
        <Route path="balloon" element={<ToolResources key="balloon" namespaces={["balloon", "messages"]}><BalloonPage /></ToolResources>} />
        <Route path="circuit" element={<ToolResources key="circuit" namespaces={["circuit", "messages"]}><CircuitPage /></ToolResources>} />
        <Route path="325" element={
          <ToolResources key="325" namespaces={["calculator", "messages", "names"]}><Suspense fallback={<p className="notice" role="status">{t("loading")}</p>}><CalculatorPage /></Suspense></ToolResources>
        } />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Route>
  </Routes>;
}
