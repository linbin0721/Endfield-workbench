import { lazy, Suspense, type ComponentType } from "react";
import { Navigate, Outlet, Route, Routes, useLocation, useParams } from "react-router-dom";
import HomePage from "./features/home/HomePage";
import { localizePath, matchLocaleSegment, stripLocalePrefix, useLocale } from "./i18n";
import { LegacyFrame } from "./shell/LegacyFrame";
import { LoadingState } from "./shell/LoadingState";
import NotFoundPage from "./shell/NotFoundPage";
import SiteLayout from "./shell/SiteLayout";
import { ToolResources } from "./shell/ToolResources";
import { TOOLS, type ToolEntry, type ToolId } from "./tools/registry";

/**
 * Each tool page is its own chunk, so the home page loads none of them; the
 * 325 chunk also carries its data and calculator.css. ToolResources starts the
 * download together with the language bundles.
 */
const PAGE_LOADERS: Record<ToolId, () => Promise<{ default: ComponentType }>> = {
  balloon: () => import("./BalloonPage"),
  circuit: () => import("./CircuitPage"),
  calculator: () => import("./CalculatorPage"),
};

/** Created once at module level, so a language switch never remounts a page. */
const TOOL_PAGES: Record<ToolId, ComponentType> = {
  balloon: lazy(PAGE_LOADERS.balloon),
  circuit: lazy(PAGE_LOADERS.circuit),
  calculator: lazy(PAGE_LOADERS.calculator),
};

/** Pages that are not migrated yet keep the old styles inside a LegacyFrame. */
function ToolRoute({ tool }: { tool: ToolEntry }) {
  const Page = TOOL_PAGES[tool.id];
  return <ToolResources key={tool.id} namespaces={tool.namespaces} preload={PAGE_LOADERS[tool.id]}>
    <Suspense fallback={<LoadingState />}><LegacyFrame><Page /></LegacyFrame></Suspense>
  </ToolResources>;
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
  return <Routes>
    <Route element={<SiteLayout />}>
      <Route index element={<LegacyRedirect />} />
      {TOOLS.map((tool) => <Route key={tool.id} path={tool.segment} element={<LegacyRedirect />} />)}
      <Route path=":locale" element={<LocaleRoute />}>
        <Route index element={<HomePage />} />
        {TOOLS.map((tool) => <Route key={tool.id} path={tool.segment} element={<ToolRoute tool={tool} />} />)}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Route>
  </Routes>;
}
