import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { I18nProvider, detectPreferredLocale, initializeI18n } from "./i18n";
import bootstrapMessages from "./i18n/bootstrap-messages.json";
import "./styles.css";

const container = document.getElementById("root")!;

// Load the first language before mounting so no raw translation key flashes.
void initializeI18n().then(() => {
  ReactDOM.createRoot(container).render(
    <React.StrictMode>
      <BrowserRouter>
        <I18nProvider>
          <App />
        </I18nProvider>
      </BrowserRouter>
    </React.StrictMode>,
  );
}).catch(() => {
  const locale = detectPreferredLocale();
  const messages = bootstrapMessages[locale];
  document.documentElement.lang = locale;
  document.title = messages.error;
  const notice = document.createElement("section");
  notice.className = "notice warning";
  notice.setAttribute("role", "alert");
  const text = document.createElement("p");
  text.textContent = messages.error;
  const retry = document.createElement("button");
  retry.className = "button primary";
  retry.textContent = messages.retry;
  retry.onclick = () => window.location.reload();
  notice.append(text, retry);
  container.replaceChildren(notice);
});
