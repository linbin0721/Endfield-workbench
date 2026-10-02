import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import BalloonPage from "./BalloonPage";
import CircuitPage from "./CircuitPage";
import HomePage from "./HomePage";
import NotFoundPage from "./NotFoundPage";
import SiteLayout from "./SiteLayout";

/** Only the /325 route pulls in the calculator page, its data.json bundle and calculator.css. */
const CalculatorPage = lazy(() => import("./CalculatorPage"));

export default function App() {
  return <Routes>
    <Route element={<SiteLayout />}>
      <Route index element={<HomePage />} />
      <Route path="balloon" element={<BalloonPage />} />
      <Route path="circuit" element={<CircuitPage />} />
      <Route path="325" element={
        <Suspense fallback={<p className="notice" role="status">加载中…</p>}><CalculatorPage /></Suspense>
      } />
      <Route path="*" element={<NotFoundPage />} />
    </Route>
  </Routes>;
}
