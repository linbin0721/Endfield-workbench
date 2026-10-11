import { useMemo } from "react";
import { i18n } from "./core";
import { DEFAULT_LOCALE, type Locale } from "./locale";
import {
  createMessageRenderer,
  isLocalizedText,
  msg,
  type LocalizedText,
  type MessageKind,
  type MessageRenderer,
  type MessageText,
} from "./messageTemplates";
import { useAppTranslation } from "./useAppTranslation";

export { isLocalizedText, msg };
export type { LocalizedText, MessageKind, MessageRenderer, MessageText };

/**
 * Central display bridge for runtime messages, bound to the active language.
 * The resolution rules live in `messageTemplates.ts` so they stay unit-testable
 * without React or Vite; this hook only wires them to i18next.
 */
export function useMessages(): MessageRenderer {
  const { t, locale } = useAppTranslation("messages");
  // Rebuilt whenever the canonical bundle is (re)loaded.
  const canonical: unknown = i18n.getResourceBundle(DEFAULT_LOCALE, "messages");

  return useMemo<MessageRenderer>(() => createMessageRenderer({
    locale,
    defaultLocale: DEFAULT_LOCALE as Locale,
    canonical,
    translate: (key, options) => t(key, options),
    // exists() includes fallbackLng, which can silently return Chinese here.
    exists: (key, namespace) => typeof i18n.getResource(locale, namespace, key) === "string",
  }), [canonical, locale, t]);
}
