import React from "react";
import ReactDOM from "react-dom/client";
import "../src/ui/styles";
import { ThemeProvider } from "../src/ui/theme";
import { DesignPreview } from "./DesignPreview";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <DesignPreview />
    </ThemeProvider>
  </React.StrictMode>,
);
