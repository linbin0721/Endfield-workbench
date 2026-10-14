import React from "react";
import ReactDOM from "react-dom/client";
import "../src/ui/styles";
import { DesignPreview } from "./DesignPreview";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <DesignPreview />
  </React.StrictMode>,
);
