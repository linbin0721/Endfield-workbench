// Design tokens first: base.css declares the cascade layer order for every later stylesheet.
import "./ui/styles";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { I18nProvider, detectPreferredLocale, initializeI18n } from "./i18n";
import bootstrapMessages from "./i18n/bootstrap-messages.json";
import { renderBootError } from "./shell/bootError";
import { ThemeProvider } from "./ui/theme";

const container = document.getElementById("root")!;

// Load the first language before mounting so no raw translation key flashes.
void initializeI18n().then(() => {
  ReactDOM.createRoot(container).render(
    <React.StrictMode>
      <BrowserRouter>
        <ThemeProvider>
          <I18nProvider>
            <App />
          </I18nProvider>
        </ThemeProvider>
      </BrowserRouter>
    </React.StrictMode>,
  );
}).catch(() => {
  const locale = detectPreferredLocale();
  const messages = bootstrapMessages[locale];
  document.documentElement.lang = locale;
  document.title = messages.error;
  renderBootError(container, messages);
});
