import { Route, Routes } from "react-router-dom";
import BalloonPage from "./BalloonPage";
import CircuitPage from "./CircuitPage";
import HomePage from "./HomePage";
import NotFoundPage from "./NotFoundPage";
import SiteLayout from "./SiteLayout";

export default function App() {
  return <Routes>
    <Route element={<SiteLayout />}>
      <Route index element={<HomePage />} />
      <Route path="balloon" element={<BalloonPage />} />
      <Route path="circuit" element={<CircuitPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Route>
  </Routes>;
}
